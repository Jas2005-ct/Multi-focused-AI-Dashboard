"""Connection model (Phase 3)."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from auths.models import db


class DBConnection(db.Model):
    """Saved database connection owned by a user."""

    __tablename__ = "db_connections"
    extend_existing = True

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Display name
    name = Column(String(100), nullable=True)

    # Connection details
    db_type = Column(String(50), nullable=False)  # postgresql, mysql
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False)
    database = Column(String(100), nullable=False)
    username = Column(String(100), nullable=False)

    # Encrypted secrets (versioned Fernet)
    password = Column(Text, nullable=True)
    connection_string = Column(Text, nullable=True)

    # SSL/TLS mode for PostgreSQL
    sslmode = Column(String(20), default="require", nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used = Column(DateTime, nullable=True)

    # Relationship
    owner = relationship("User", back_populates="db_connections")

    # --- Compatibility helpers (legacy method-style API) ---
    # Service functions in connections.service do the same; these exist so
    # pre-Phase-3 callers (routes, tools, migration scripts) keep working.

    def get_decrypted_password(self) -> str:
        from connections.crypto import crypto

        return crypto.decrypt(self.password) if self.password else ""

    def get_decrypted_connection_string(self) -> str:
        from connections.crypto import crypto

        return crypto.decrypt(self.connection_string) if self.connection_string else ""

    def set_encrypted_fields(self, password: str, connection_string: str) -> None:
        from connections.crypto import crypto

        self.password = crypto.encrypt(password) if password else None
        self.connection_string = crypto.encrypt(connection_string) if connection_string else None


# Ensure User model has the backref
# (User model already has: db_connections = relationship('DBConnection', backref='owner', lazy=True, cascade='all, delete-orphan'))
