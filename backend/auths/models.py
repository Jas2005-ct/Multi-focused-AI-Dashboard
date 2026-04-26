from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    google_id = db.Column(db.String(255), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
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
    name = db.Column(db.String(100))  # "Production DB", "Test DB"
    db_type = db.Column(db.String(50))  # postgresql, mysql, sqlite
    host = db.Column(db.String(255))
    port = db.Column(db.Integer)
    database = db.Column(db.String(100))
    username = db.Column(db.String(100))
    password = db.Column(db.String(255))  # Encrypt this!
    connection_string = db.Column(db.Text,nullable=True)  # OR full connection URI
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_used = db.Column(db.DateTime)