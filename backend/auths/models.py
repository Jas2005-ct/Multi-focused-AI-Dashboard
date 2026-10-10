from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    google_id = db.Column(db.String(255), unique=True, nullable=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=True)
    name = db.Column(db.String(255))
    picture = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # One-to-Many: User has many DB connections
    db_connections = db.relationship('DBConnection', back_populates='owner', lazy=True, cascade='all, delete-orphan')
    refresh_tokens = db.relationship('RefreshToken', back_populates='user', lazy=True, cascade='all, delete-orphan')


class RefreshToken(db.Model):
    """Server-side refresh-token family for rotation + reuse detection (Phase 2)."""

    __tablename__ = 'refresh_tokens'

    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    revoked = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', back_populates='refresh_tokens')