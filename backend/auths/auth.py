
from flask import Blueprint
import os
from auths.models import User,db
from flask import session, redirect, url_for, current_app
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
    
    # Check if user exists, create if not
    user = User.query.filter_by(google_id=user_info['sub']).first()
    if not user:
        user = User(
            google_id=user_info['sub'],
            email=user_info['email'],
            name=user_info.get('name'),
            picture=user_info.get('picture')
        )
        db.session.add(user)
        db.session.commit()
    
    # Store in session
    session['user_id'] = user.id
    session['email'] = user.email
    
    return redirect(url_for('services.hello'))
