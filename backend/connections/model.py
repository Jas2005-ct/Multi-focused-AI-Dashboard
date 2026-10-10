"""Connection model (Phase 3)."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship

from auths.models import db


class DBConnection(db.Model):
    """Saved database connection owned by a user."""

    __tablename__ = "db_connections"
    extend_existing = True
    """Saved database connection owned by a user."""

    __tablename__ = "db_connections"

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


# Ensure User model has the backref
# (User model already has: db_connections = relationship('DBConnection', backref='owner', lazy=True, cascade='all, delete-orphan'))