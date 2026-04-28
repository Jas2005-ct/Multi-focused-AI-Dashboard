#!/usr/bin/env python
"""
Database initialization script
Run this to create all tables and initialize the database with your models
"""

import os
from dotenv import load_dotenv
from app import create_app
from auths.models import db

# Load environment variables
load_dotenv()

def init_database():
    """Initialize the database with all models"""
    app = create_app()
    
    with app.app_context():
        print("Creating all tables...")
        db.create_all()
        print("✓ Database initialized successfully!")
        print(f"✓ Database URL: {os.getenv('DATABASE_URL')}")
        print("\nTables created:")
        print("  - users")
        print("  - db_connections")

if __name__ == '__main__':
    init_database()
