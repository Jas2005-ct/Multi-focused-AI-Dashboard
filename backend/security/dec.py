from flask import session, redirect, url_for
from functools import wraps

def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('auth.google_login'))
        return f(*args, **kwargs)
    return wrapper