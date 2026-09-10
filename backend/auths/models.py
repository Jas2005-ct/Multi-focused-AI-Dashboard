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
    db_connections = db.relationship('DBConnection', backref='owner', lazy=True, cascade='all, delete-orphan')

class DBConnection(db.Model):
    __tablename__ = 'db_connections'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Connection details
    # name = db.Column(db.String(100))  # "Production DB", "Test DB"
    db_type = db.Column(db.String(50))  # postgresql, mysql, sqlite
    host = db.Column(db.String(255))
    port = db.Column(db.Integer)
    database = db.Column(db.String(100))
    username = db.Column(db.String(100))
    password = db.Column(db.Text)  # Fernet-encrypted
    connection_string = db.Column(db.Text, nullable=True)  # Fernet-encrypted URI

    def get_decrypted_password(self) -> str:
        from security.crypto import decrypt_value
        return decrypt_value(self.password) if self.password else ""

    def get_decrypted_connection_string(self) -> str:
        from security.crypto import decrypt_value
        return decrypt_value(self.connection_string) if self.connection_string else ""

    def set_encrypted_fields(self, password: str, connection_string: str):
        from security.crypto import encrypt_value
        self.password = encrypt_value(password) if password else None
        self.connection_string = encrypt_value(connection_string) if connection_string else None
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_used = db.Column(db.DateTime)