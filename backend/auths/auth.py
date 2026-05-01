
from flask import Blueprint, request, jsonify
import os
from auths.models import User,db
from flask import session, redirect, url_for, current_app
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
from datetime import datetime, timedelta
auth_bp = Blueprint('auth', __name__)

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", None)
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", None)
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"

@auth_bp.route('/login')
def google_login():
    client = current_app.oauth.google
    redirect_uri = url_for('auth.google_callback', _external=True)
    return client.authorize_redirect(redirect_uri)


@auth_bp.route('/callback')
def google_callback():
    client = current_app.oauth.google
    token = client.authorize_access_token()
    user_info = token.get('userinfo')
    
    # Check if user exists by google_id
    user = User.query.filter_by(google_id=user_info['sub']).first()
    
    if not user:
        # Check if user exists by email (link accounts)
        user = User.query.filter_by(email=user_info['email']).first()
        if user:
            # Link Google account to existing user
            user.google_id = user_info['sub']
            user.picture = user_info.get('picture') or user.picture
            db.session.commit()
        else:
            # Create new user
            user = User(
                google_id=user_info['sub'],
                email=user_info['email'],
                name=user_info.get('name'),
                picture=user_info.get('picture')
            )
            db.session.add(user)
            db.session.commit()
    
    # Generate JWT token (same as email login)
    jwt_token = jwt.encode({
        'user_id': user.id,
        'email': user.email,
        'exp': datetime.utcnow() + timedelta(hours=24)
    }, current_app.secret_key, algorithm='HS256')
    
    # Redirect to frontend dashboard with token
    return redirect(f"http://localhost:5173/dashboard?token={jwt_token}")


@auth_bp.route('/login', methods=['POST'])
def email_login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400
    
    user = User.query.filter_by(email=email).first()
    
    if not user or not user.password or not check_password_hash(user.password, password):
        return jsonify({'error': 'Invalid credentials'}), 401
    
    token = jwt.encode({
        'user_id': user.id,
        'email': user.email,
        'exp': datetime.utcnow() + timedelta(hours=24)
    }, current_app.secret_key, algorithm='HS256')
    
    return jsonify({'token': token, 'user': {'id': user.id, 'email': user.email, 'name': user.name}})


@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    name = data.get('name', '')
    
    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400
    
    if User.query.filter_by(email=email).first():
        if User.query.filter_by(email=email).first().google_id:
            return jsonify({
                'error': 'Email already exists',
                'message': 'Please login with Google'
            }), 400
    
    hashed_password = generate_password_hash(password)
    user = User(
        email=email,
        password=hashed_password,
        name=name
    )
    db.session.add(user)
    db.session.commit()
    
    token = jwt.encode({
        'user_id': user.id,
        'email': user.email,
        'exp': datetime.utcnow() + timedelta(hours=24)
    }, current_app.secret_key, algorithm='HS256')
    
    return jsonify({'token': token, 'user': {'id': user.id, 'email': user.email, 'name': user.name}}), 201
