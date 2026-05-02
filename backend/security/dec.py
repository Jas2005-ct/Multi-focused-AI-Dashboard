import jwt
from flask import session, redirect, url_for, request, jsonify, current_app
from functools import wraps


def require_auth(f):
    """Authenticate via session (browser) or JWT Bearer token (API)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        # Try session first (browser users)
        user_id = session.get('user_id')
        
        # If no session, try JWT Bearer token (API/Postman)
        if not user_id:
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
                try:
                    payload = jwt.decode(
                        token, 
                        current_app.secret_key, 
                        algorithms=['HS256']
                    )
                    user_id = payload.get('user_id')
                    # Sync to session for this request
                    session['user_id'] = user_id
                    session['email'] = payload.get('email')
                except jwt.ExpiredSignatureError:
                    return jsonify({"error": "Token expired"}), 401
                except jwt.InvalidTokenError:
                    return jsonify({"error": "Invalid token"}), 401
        
        if not user_id:
            # API requests get JSON error, browser gets redirect
            if request.is_json or request.headers.get('Accept') == 'application/json':
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for('auth.google_login'))
            
        return f(*args, **kwargs)
    return wrapper