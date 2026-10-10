from functools import wraps

import jwt
from flask import current_app, g, jsonify, request

from auths.jwt_service import decode_access


def require_auth(f):
    """Authenticate API calls via JWT Bearer access tokens only.

    No session fallback (removed Phase 2): every /api and protected /auth
    route answers 401 JSON, never a browser redirect. Expired access tokens
    return code TOKEN_EXPIRED so the frontend can rotate exactly once via
    POST /auth/refresh before logging out.
    """

    @wraps(f)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify({"error": "Authentication required", "code": "MISSING_TOKEN"}), 401
        try:
            payload = decode_access(header[7:], current_app.secret_key)
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired", "code": "TOKEN_EXPIRED"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token", "code": "INVALID_TOKEN"}), 401

        g.user_id = payload.get("user_id")
        g.email = payload.get("email")
        if not g.user_id:
            return jsonify({"error": "Invalid token", "code": "INVALID_TOKEN"}), 401
        return f(*args, **kwargs)

    return wrapper
