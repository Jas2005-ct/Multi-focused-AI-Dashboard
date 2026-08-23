import os
import time
import secrets
import threading
import logging
from flask import session, redirect, url_for, current_app, jsonify
from flask_openapi3 import APIBlueprint, Tag
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
from datetime import datetime, timedelta
from auths.models import User, db
from auths.schemas import (
    ValidateErrorSchema,
    UserSchema,
    ValidateSuccessSchema,
    RegisterRequest,
    LoginRequest,
    ForgotPasswordRequest,
    VerifyOtpRequest,
    ResetPasswordRequest,
    SuccessMessageSchema,
)

auth_bp = APIBlueprint('auth', __name__)
auth_tag = Tag(name='Auth', description='Authentication & OTP operations')
logger = logging.getLogger(__name__)

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", None)
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", None)
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"

# In-memory OTP store (dev): {email: (otp, expiry_timestamp, attempts)}
# Prod: replace with Redis / DB + Celery email task
_otp_store: dict = {}
_otp_lock = threading.Lock()
OTP_TTL_SECONDS = 300
OTP_MAX_ATTEMPTS = 5


def _generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


@auth_bp.get('/login', tags=[auth_tag], summary='Initiate Google OAuth login')
def google_login():
    client = current_app.oauth.google
    redirect_uri = url_for('auth.google_callback', _external=True)
    return client.authorize_redirect(redirect_uri)


@auth_bp.get('/callback', tags=[auth_tag], summary='Google OAuth callback')
def google_callback():
    client = current_app.oauth.google
    token = client.authorize_access_token()
    user_info = token.get('userinfo')

    user = User.query.filter_by(google_id=user_info['sub']).first()
    if not user:
        user = User.query.filter_by(email=user_info['email']).first()
        if user:
            user.google_id = user_info['sub']
            user.picture = user_info.get('picture') or user.picture
            db.session.commit()
        else:
            user = User(
                google_id=user_info['sub'],
                email=user_info['email'],
                name=user_info.get('name'),
                picture=user_info.get('picture')
            )
            db.session.add(user)
            db.session.commit()

    jwt_token = jwt.encode({
        'user_id': user.id,
        'email': user.email,
        'exp': datetime.utcnow() + timedelta(hours=24)
    }, current_app.secret_key, algorithm='HS256')

    frontend_url = os.environ.get('FRONTEND_URL', 'http://localhost:5173')
    import json, urllib.parse
    user_data = {'id': user.id, 'email': user.email, 'name': user.name or ''}
    user_json = urllib.parse.quote(json.dumps(user_data))
    return redirect(f"{frontend_url}/dashboard?token={jwt_token}&user={user_json}")


@auth_bp.post('/login', tags=[auth_tag], summary='Email login',
              responses={200: ValidateSuccessSchema, 400: ValidateErrorSchema, 401: ValidateErrorSchema})
def email_login(body: LoginRequest):
    user = User.query.filter_by(email=body.email).first()
    if not user or not user.password or not check_password_hash(user.password, body.password):
        return jsonify(ValidateErrorSchema(
            error="Invalid Credentials",
            message="The email or password you entered is incorrect"
        ).model_dump()), 401

    token = jwt.encode({
        'user_id': user.id,
        'email': user.email,
        'exp': datetime.utcnow() + timedelta(hours=24)
    }, current_app.secret_key, algorithm='HS256')

    return jsonify(ValidateSuccessSchema(
        token=token,
        user=UserSchema(id=user.id, email=user.email, name=user.name)
    ).model_dump()), 200


@auth_bp.post('/logout', tags=[auth_tag], summary='Logout and clear session',
              responses={200: SuccessMessageSchema})
def logout():
    session.clear()
    return jsonify(SuccessMessageSchema(success=True, message="Logged out").model_dump()), 200


@auth_bp.post('/register', tags=[auth_tag], summary='Register new user',
              responses={201: ValidateSuccessSchema, 400: ValidateErrorSchema, 409: ValidateErrorSchema})
def register(body: RegisterRequest):
    existing_user = User.query.filter_by(email=body.email).first()
    if existing_user:
        if existing_user.google_id:
            return jsonify(ValidateErrorSchema(
                error="Email already exists",
                message="This email is linked to a Google account. Please sign in with Google."
            ).model_dump()), 409
        return jsonify(ValidateErrorSchema(
            error="Email already exists",
            message="An account with this email already exists. Please login instead."
        ).model_dump()), 409

    hashed_password = generate_password_hash(body.password)
    new_user = User(email=body.email, password=hashed_password, name=body.name or '')
    db.session.add(new_user)
    db.session.commit()

    token = jwt.encode({
        'user_id': new_user.id,
        'email': new_user.email,
        'exp': datetime.utcnow() + timedelta(hours=24)
    }, current_app.secret_key, algorithm='HS256')

    return jsonify(ValidateSuccessSchema(
        token=token,
        user=UserSchema(id=new_user.id, email=new_user.email, name=new_user.name)
    ).model_dump()), 201


@auth_bp.post('/forgot-password', tags=[auth_tag], summary='Generate OTP for password reset',
              responses={200: SuccessMessageSchema, 400: ValidateErrorSchema, 404: ValidateErrorSchema})
def forgot_password(body: ForgotPasswordRequest):
    """Step 1: generate OTP, print to terminal (dev), store with TTL."""
    user = User.query.filter_by(email=body.email).first()
    if not user:
        return jsonify(ValidateErrorSchema(error="Not Found", message="No account with this email").model_dump()), 404
    if not user.password and user.google_id:
        return jsonify(ValidateErrorSchema(error="Google Account", message="This email uses Google sign-in. Please sign in with Google.").model_dump()), 400

    otp = _generate_otp()
    expiry = time.time() + OTP_TTL_SECONDS
    with _otp_lock:
        _otp_store[body.email] = (otp, expiry, 0)

    print(f"\n{'='*50}\n[FORGOT-PASSWORD] OTP for {body.email}: {otp} (valid 5 min)\n{'='*50}\n")
    logger.info(f"OTP for {body.email}: {otp} (expires in {OTP_TTL_SECONDS}s)")

    return jsonify(SuccessMessageSchema(success=True, message="OTP sent — check terminal (dev) / email (prod)").model_dump()), 200


@auth_bp.post('/verify-otp', tags=[auth_tag], summary='Verify OTP',
              responses={200: SuccessMessageSchema, 400: ValidateErrorSchema, 429: ValidateErrorSchema})
def verify_otp(body: VerifyOtpRequest):
    """Step 2: verify OTP without consuming it (so reset can still use it)."""
    with _otp_lock:
        entry = _otp_store.get(body.email)
    if not entry:
        return jsonify(ValidateErrorSchema(error="Invalid OTP", message="No OTP found. Request a new one.").model_dump()), 400

    stored_otp, expiry, attempts = entry
    if time.time() > expiry:
        with _otp_lock:
            _otp_store.pop(body.email, None)
        return jsonify(ValidateErrorSchema(error="Expired", message="OTP expired. Request a new one.").model_dump()), 400
    if attempts >= OTP_MAX_ATTEMPTS:
        with _otp_lock:
            _otp_store.pop(body.email, None)
        return jsonify(ValidateErrorSchema(error="Too Many Attempts", message="Too many failed attempts. Request a new OTP.").model_dump()), 429
    if stored_otp != body.otp:
        with _otp_lock:
            _otp_store[body.email] = (stored_otp, expiry, attempts + 1)
        return jsonify(ValidateErrorSchema(error="Invalid OTP", message="Incorrect OTP").model_dump()), 400

    return jsonify(SuccessMessageSchema(success=True, message="OTP verified").model_dump()), 200


@auth_bp.post('/reset-password', tags=[auth_tag], summary='Reset password with OTP',
              responses={200: SuccessMessageSchema, 400: ValidateErrorSchema, 404: ValidateErrorSchema, 429: ValidateErrorSchema})
def reset_password(body: ResetPasswordRequest):
    """Step 3: verify OTP and set new password (consumes OTP)."""
    with _otp_lock:
        entry = _otp_store.get(body.email)
    if not entry:
        return jsonify(ValidateErrorSchema(error="Invalid OTP", message="No OTP found. Request a new one.").model_dump()), 400

    stored_otp, expiry, attempts = entry
    if time.time() > expiry:
        with _otp_lock:
            _otp_store.pop(body.email, None)
        return jsonify(ValidateErrorSchema(error="Expired", message="OTP expired. Request a new one.").model_dump()), 400
    if attempts >= OTP_MAX_ATTEMPTS:
        with _otp_lock:
            _otp_store.pop(body.email, None)
        return jsonify(ValidateErrorSchema(error="Too Many Attempts", message="Too many failed attempts. Request a new OTP.").model_dump()), 429
    if stored_otp != body.otp:
        with _otp_lock:
            _otp_store[body.email] = (stored_otp, expiry, attempts + 1)
        return jsonify(ValidateErrorSchema(error="Invalid OTP", message="Incorrect OTP").model_dump()), 400
    print(body.new_password)
    user = User.query.filter_by(email=body.email).first()
    if not user:
        return jsonify(ValidateErrorSchema(error="Not Found", message="No account with this email").model_dump()), 404

    user.password = generate_password_hash(body.new_password)
    db.session.commit()
    with _otp_lock:
        _otp_store.pop(body.email, None)

    logger.info(f"Password reset for {body.email}")
    return jsonify(SuccessMessageSchema(success=True, message="Password changed successfully").model_dump()), 200
