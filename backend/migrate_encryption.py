#!/usr/bin/env python
"""
Migration script: Re-encrypt all DB connections with new ENCRYPTION_KEY version.

Run this during Phase 7 rollout to upgrade stored credentials to the new key version.
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
from auths.models import db
from connections.model import DBConnection
from connections.crypto import crypto


def migrate_encryption():
    """Re-encrypt all stored DB connections with current ENCRYPTION_KEY."""
    app = create_app()
    
    with app.app_context():
        # Ensure tables exist
        db.create_all()
        
        connections = DBConnection.query.all()
        print(f"Found {len(connections)} connections to migrate")
        
        migrated = 0
        failed = 0
        
        for conn in connections:
            try:
                # Decrypt with old key (crypto.decrypt handles version automatically)
                password = crypto.decrypt(conn.password) if conn.password else ""
                conn_str = crypto.decrypt(conn.connection_string) if conn.connection_string else ""
                
                # Re-encrypt with current key version
                conn.set_encrypted_fields(password, conn_str)
                db.session.add(conn)
                migrated += 1
                
            except Exception as e:
                print(f"Failed to migrate connection {conn.id}: {e}")
                failed += 1
        
        db.session.commit()
        print(f"Migration complete: {migrated} migrated, {failed} failed")
        
        if failed > 0:
            sys.exit(1)


if __name__ == "__main__":
    migrate_encryption()