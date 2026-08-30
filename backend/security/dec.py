import jwt
from flask import session, redirect, url_for, request, jsonify, current_app, g
from functools import wraps


def require_auth(f):
    """Authenticate via JWT Bearer token first, then Flask session fallback."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        user_id = None
        email = None

        # Prefer JWT Bearer token (source of truth for API)
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
                email = payload.get('email')
            except jwt.ExpiredSignatureError:
                return jsonify({"error": "Token expired"}), 401
            except jwt.InvalidTokenError:
                return jsonify({"error": "Invalid token"}), 401

        # Fallback to Flask session (Google OAuth browser flow)
        if not user_id:
            user_id = session.get('user_id')
            email = session.get('email')

        if not user_id:
            if request.is_json or request.headers.get('Accept') == 'application/json':
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for('auth.google_login'))

        g.user_id = user_id
        g.email = email
        return f(*args, **kwargs)
    return wrapper