#!/usr/bin/env python
"""
Migration script: Invalidate all refresh tokens to force re-login.

Run this during Phase 7 rollout to force all users to re-authenticate with new JWTs.
"""

import os
import sys

# Must set env BEFORE any imports that use crypto
os.environ.setdefault("FLASK_ENV", "production")
os.environ.setdefault("ENCRYPTION_KEY", "phase0-test-encryption-key-32-chr!")
os.environ.setdefault("SECRET_KEY", "phase0-test-secret-key-32-chars-min!")
os.environ.setdefault("DATABASE_URL", "sqlite:///phase0.db")
os.environ.setdefault("OTP_BACKEND", "memory")
os.environ.pop("REDIS_URL", None)
os.environ.pop("CELERY_BROKER_URL", None)

# Now import after env is set
from app import create_app
from auths.models import db, RefreshToken


def invalidate_refresh_tokens():
    """Mark all refresh tokens as revoked to force re-login."""
    app = create_app()
    
    with app.app_context():
        # Ensure tables exist
        db.create_all()
        
        tokens = RefreshToken.query.filter_by(revoked=False).all()
        print(f"Found {len(tokens)} active refresh tokens to revoke")
        
        for token in tokens:
            token.revoked = True
        
        db.session.commit()
        print(f"Revoked {len(tokens)} refresh tokens. All users must re-login.")


if __name__ == "__main__":
    invalidate_refresh_tokens()