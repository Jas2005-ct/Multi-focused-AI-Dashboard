import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from flask import current_app, g, jsonify, redirect, session, url_for
from flask_openapi3 import APIBlueprint, Tag
from werkzeug.security import check_password_hash, generate_password_hash

from auths.jwt_service import decode_refresh, issue_pair
from auths.models import RefreshToken, User, db
from auths.otp_store import OTP_MAX_ATTEMPTS, OTP_TTL_SECONDS, generate_otp, otp_store
from auths.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SuccessMessageSchema,
    UserSchema,
    ValidateErrorSchema,
    ValidateSuccessSchema,
    VerifyOtpRequest,
)
from auths.tasks import dispatch_otp
from security.dec import require_auth

auth_bp = APIBlueprint("auth", __name__)
auth_tag = Tag(name="Auth", description="Authentication & OTP operations")
logger = logging.getLogger(__name__)

# Minimum seconds between OTP sends to the same address (Phase 2).
OTP_RESEND_COOLDOWN_SECONDS = int(os.getenv("OTP_RESEND_COOLDOWN_SECONDS", "60"))


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _build_pair(user):
    """Build a token pair without touching the DB (caller commits)."""
    return issue_pair(user, current_app.secret_key)


def _stage_pair(user, pair):
    """Stage the refresh-token row; caller commits atomically with siblings."""
    db.session.add(
        RefreshToken(
            jti=pair["jti"],
            user_id=user.id,
            expires_at=_utcnow() + timedelta(days=7),
        )
    )


def _issue_pair_response(user):
    """Persist a refresh-token row and build the login/register payload."""
    pair = _build_pair(user)
    _stage_pair(user, pair)
    db.session.commit()
    return jsonify(
        ValidateSuccessSchema(
            token=pair["token"],
            refreshToken=pair["refreshToken"],
            user=UserSchema(id=user.id, email=user.email, name=user.name),
        ).model_dump()
    )


def _otp_sent_at(entry):
    """Recover the send time from a store entry (otp, expiry, attempts)."""
    _otp, expiry, _attempts = entry
    return expiry - OTP_TTL_SECONDS


def _cooldown_remaining(email):
    entry = otp_store.get(email)
    if not entry:
        return 0
    elapsed = datetime.now().timestamp() - _otp_sent_at(entry)
    return max(0, OTP_RESEND_COOLDOWN_SECONDS - elapsed)


auth_bp = APIBlueprint("auth", __name__)
auth_tag = Tag(name="Auth", description="Authentication & OTP operations")
logger = logging.getLogger(__name__)

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", None)
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", None)
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"


@auth_bp.get("/login", tags=[auth_tag], summary="Initiate Google OAuth login")
def google_login():
    client = current_app.oauth.google
    redirect_uri = url_for("auth.google_callback", _external=True)
    return client.authorize_redirect(redirect_uri)


@auth_bp.get("/callback", tags=[auth_tag], summary="Google OAuth callback")
def google_callback():
    client = current_app.oauth.google
    token = client.authorize_access_token()
    user_info = token.get("userinfo")

    user = User.query.filter_by(google_id=user_info["sub"]).first()
    if not user:
        user = User.query.filter_by(email=user_info["email"]).first()
        if user:
            user.google_id = user_info["sub"]
            user.picture = user_info.get("picture") or user.picture
        else:
            user = User(
                google_id=user_info["sub"],
                email=user_info["email"],
                name=user_info.get("name"),
                picture=user_info.get("picture"),
            )
            db.session.add(user)
    # Single atomic commit: user row + refresh-token row together.
    db.session.flush()
    pair = _build_pair(user)
    _stage_pair(user, pair)
    db.session.commit()

    frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:5173")
    import json
    import urllib.parse

    user_data = {"id": user.id, "email": user.email, "name": user.name or ""}
    user_json = urllib.parse.quote(json.dumps(user_data))
    refresh = urllib.parse.quote(pair["refreshToken"])
    return redirect(
        f"{frontend_url}/dashboard?token={pair['token']}&refreshToken={refresh}&user={user_json}"
    )


@auth_bp.post(
    "/login",
    tags=[auth_tag],
    summary="Email login",
    responses={200: ValidateSuccessSchema, 400: ValidateErrorSchema, 401: ValidateErrorSchema},
)
def email_login(body: LoginRequest):
    user = User.query.filter_by(email=body.email).first()
    if not user or not user.password or not check_password_hash(user.password, body.password):
        return (
            jsonify(
                ValidateErrorSchema(
                    error="Invalid Credentials",
                    message="The email or password you entered is incorrect",
                ).model_dump()
            ),
            401,
        )

    return _issue_pair_response(user), 200


@auth_bp.post(
    "/logout",
    tags=[auth_tag],
    summary="Logout and clear session",
    responses={200: SuccessMessageSchema},
)
def logout():
    session.clear()
    return jsonify(SuccessMessageSchema(success=True, message="Logged out").model_dump()), 200


@auth_bp.post(
    "/register",
    tags=[auth_tag],
    summary="Register new user",
    responses={201: ValidateSuccessSchema, 400: ValidateErrorSchema, 409: ValidateErrorSchema},
)
def register(body: RegisterRequest):
    existing_user = User.query.filter_by(email=body.email).first()
    if existing_user:
        if existing_user.google_id:
            return (
                jsonify(
                    ValidateErrorSchema(
                        error="Email already exists",
                        message="This email is linked to a Google account. Please sign in with Google.",
                    ).model_dump()
                ),
                409,
            )
        return (
            jsonify(
                ValidateErrorSchema(
                    error="Email already exists",
                    message="An account with this email already exists. Please login instead.",
                ).model_dump()
            ),
            409,
        )

    hashed_password = generate_password_hash(body.password)
    new_user = User(email=body.email, password=hashed_password, name=body.name or "")
    db.session.add(new_user)
    # Single atomic commit: user row + refresh-token row together.
    db.session.flush()
    pair = _build_pair(new_user)
    _stage_pair(new_user, pair)
    db.session.commit()

    return (
        jsonify(
            ValidateSuccessSchema(
                token=pair["token"],
                refreshToken=pair["refreshToken"],
                user=UserSchema(id=new_user.id, email=new_user.email, name=new_user.name),
            ).model_dump()
        ),
        201,
    )


@auth_bp.post(
    "/forgot-password",
    tags=[auth_tag],
    summary="Generate OTP for password reset",
    responses={200: SuccessMessageSchema},
)
def forgot_password(body: ForgotPasswordRequest):
    """Step 1: generate OTP, store via env-driven backend, dispatch via Celery/print.

    Always returns success to avoid account enumeration AND activity probing:
    requests inside the resend cooldown are silently dropped (no 429), so an
    observer cannot distinguish unknown emails from recently-mailed ones.
    """
    uniform = (
        jsonify(
            SuccessMessageSchema(
                success=True, message="If an account exists for this email, an OTP was sent."
            ).model_dump()
        ),
        200,
    )

    if _cooldown_remaining(body.email) > 0:
        return uniform

    user = User.query.filter_by(email=body.email).first()
    if not user:
        return uniform
    if not user.password and user.google_id:
        return uniform

    otp = generate_otp()
    otp_store.save(body.email, otp)
    dispatch_otp(body.email, otp)
    return uniform


@auth_bp.post(
    "/resend-otp",
    tags=[auth_tag],
    summary="Resend OTP with cooldown",
    responses={200: SuccessMessageSchema},
)
def resend_otp(body: ForgotPasswordRequest):
    """Alias of forgot-password: same silent-cooldown uniform response."""
    return forgot_password(body)


@auth_bp.post(
    "/verify-otp",
    tags=[auth_tag],
    summary="Verify OTP",
    responses={200: SuccessMessageSchema, 400: ValidateErrorSchema, 429: ValidateErrorSchema},
)
def verify_otp(body: VerifyOtpRequest):
    """Step 2: verify OTP without consuming it (so reset can still use it)."""
    entry = otp_store.get(body.email)
    if not entry:
        return (
            jsonify(
                ValidateErrorSchema(
                    error="Invalid OTP", message="No OTP found. Request a new one."
                ).model_dump()
            ),
            400,
        )

    stored_otp, _expiry, attempts = entry
    # Redis store: get() already handles TTL expiry (returns None if expired)
    # Memory store: get() handles expiry internally
    if attempts >= OTP_MAX_ATTEMPTS:
        otp_store.delete(body.email)
        return (
            jsonify(
                ValidateErrorSchema(
                    error="Too Many Attempts",
                    message="Too many failed attempts. Request a new OTP.",
                ).model_dump()
            ),
            429,
        )
    if not secrets.compare_digest(stored_otp, body.otp):
        otp_store.increment_attempts(body.email)
        return (
            jsonify(ValidateErrorSchema(error="Invalid OTP", message="Incorrect OTP").model_dump()),
            400,
        )

    return jsonify(SuccessMessageSchema(success=True, message="OTP verified").model_dump()), 200


@auth_bp.post(
    "/reset-password",
    tags=[auth_tag],
    summary="Reset password with OTP",
    responses={
        200: SuccessMessageSchema,
        400: ValidateErrorSchema,
        404: ValidateErrorSchema,
        429: ValidateErrorSchema,
    },
)
def reset_password(body: ResetPasswordRequest):
    """Step 3: verify OTP and set new password (consumes OTP)."""
    entry = otp_store.get(body.email)
    if not entry:
        return (
            jsonify(
                ValidateErrorSchema(
                    error="Invalid OTP", message="No OTP found. Request a new one."
                ).model_dump()
            ),
            400,
        )

    stored_otp, _expiry, attempts = entry
    if attempts >= OTP_MAX_ATTEMPTS:
        otp_store.delete(body.email)
        return (
            jsonify(
                ValidateErrorSchema(
                    error="Too Many Attempts",
                    message="Too many failed attempts. Request a new OTP.",
                ).model_dump()
            ),
            429,
        )
    if not secrets.compare_digest(stored_otp, body.otp):
        otp_store.increment_attempts(body.email)
        return (
            jsonify(ValidateErrorSchema(error="Invalid OTP", message="Incorrect OTP").model_dump()),
            400,
        )

    user = User.query.filter_by(email=body.email).first()
    if not user:
        return (
            jsonify(
                ValidateErrorSchema(
                    error="Not Found", message="No account with this email"
                ).model_dump()
            ),
            404,
        )

    user.password = generate_password_hash(body.new_password)
    db.session.commit()
    otp_store.delete(body.email)

    logger.info(f"Password reset for {body.email}")
    return (
        jsonify(
            SuccessMessageSchema(success=True, message="Password changed successfully").model_dump()
        ),
        200,
    )


@auth_bp.post(
    "/refresh",
    tags=[auth_tag],
    summary="Rotate refresh token",
    responses={200: ValidateSuccessSchema, 401: ValidateErrorSchema},
)
def refresh(body: RefreshRequest):
    """Exchange a refresh token for a fresh pair (rotation).

    Unknown, revoked, or mismatched tokens fail closed; a revoked-but-known
    jti indicates reuse, so the whole token family is revoked.
    """
    try:
        payload = decode_refresh(body.refreshToken, current_app.secret_key)
    except jwt.ExpiredSignatureError:
        return (
            jsonify(
                ValidateErrorSchema(
                    error="Token expired", message="Refresh token expired. Please sign in again."
                ).model_dump()
            ),
            401,
        )
    except jwt.InvalidTokenError:
        return (
            jsonify(
                ValidateErrorSchema(
                    error="Invalid token", message="Refresh token is invalid."
                ).model_dump()
            ),
            401,
        )

    record = RefreshToken.query.filter_by(jti=payload.get("jti")).first()
    if not record or record.user_id != payload.get("user_id"):
        return (
            jsonify(
                ValidateErrorSchema(
                    error="Invalid token", message="Refresh token is invalid."
                ).model_dump()
            ),
            401,
        )
    if record.revoked:
        # Reuse detected: burn the family so a stolen token is useless.
        RefreshToken.query.filter_by(user_id=record.user_id).update({"revoked": True})
        db.session.commit()
        logger.warning(f"Refresh reuse detected for user_id={record.user_id}")
        return (
            jsonify(
                ValidateErrorSchema(
                    error="Invalid token",
                    message="Refresh token was already used. Please sign in again.",
                ).model_dump()
            ),
            401,
        )
    if record.expires_at < _utcnow():
        record.revoked = True
        db.session.commit()
        return (
            jsonify(
                ValidateErrorSchema(
                    error="Token expired", message="Refresh token expired. Please sign in again."
                ).model_dump()
            ),
            401,
        )

    user = User.query.get(record.user_id)
    if not user:
        return (
            jsonify(
                ValidateErrorSchema(
                    error="Invalid token", message="Account no longer exists."
                ).model_dump()
            ),
            401,
        )

    # Single atomic commit: revoke presented jti + persist rotated row.
    record.revoked = True
    pair = _build_pair(user)
    _stage_pair(user, pair)
    db.session.commit()
    return (
        jsonify(
            ValidateSuccessSchema(
                token=pair["token"],
                refreshToken=pair["refreshToken"],
                user=UserSchema(id=user.id, email=user.email, name=user.name),
            ).model_dump()
        ),
        200,
    )


@auth_bp.get("/me", tags=[auth_tag], summary="Current user")
@require_auth
def me():
    user = User.query.get(g.user_id)
    if not user:
        return (
            jsonify(
                ValidateErrorSchema(
                    error="Not Found", message="Account no longer exists."
                ).model_dump()
            ),
            404,
        )
    return jsonify(UserSchema(id=user.id, email=user.email, name=user.name).model_dump()), 200
