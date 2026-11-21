from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError

db = SQLAlchemy()

# Reserved identity for the shared demo account used while AUTH_REQUIRED is
# disabled. It has no password and cannot sign in.
DEMO_USER_EMAIL = "demo@example.com"
DEMO_USER_NAME = "Demo User"


def get_or_create_demo_user() -> "User":
    """Return the shared demo user, creating it on first use.

    Only used in demo mode (``AUTH_REQUIRED=false``): it gives the anonymous
    visitor a stable ``users`` row so saved connections and refresh tokens
    have an owner. The email is a reserved local address, so it can never
    collide with a real account.
    """
    user = User.query.filter_by(email=DEMO_USER_EMAIL).first()
    if user is not None:
        return user

    user = User(email=DEMO_USER_EMAIL, name=DEMO_USER_NAME)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        # A concurrent request created the row first (email is unique).
        db.session.rollback()
        user = User.query.filter_by(email=DEMO_USER_EMAIL).first()
    return user


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    google_id = db.Column(db.String(255), unique=True, nullable=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=True)
    name = db.Column(db.String(255))
    picture = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # One-to-Many: User has many DB connections
    db_connections = db.relationship(
        "DBConnection", back_populates="owner", lazy=True, cascade="all, delete-orphan"
    )
    refresh_tokens = db.relationship(
        "RefreshToken", back_populates="user", lazy=True, cascade="all, delete-orphan"
    )


class RefreshToken(db.Model):
    """Server-side refresh-token family for rotation + reuse detection (Phase 2)."""

    __tablename__ = "refresh_tokens"

    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    revoked = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", back_populates="refresh_tokens")
