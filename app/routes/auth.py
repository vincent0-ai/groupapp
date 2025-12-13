from flask import Blueprint, request, redirect, url_for, session, current_app
from flask_oauthlib.client import OAuth
from app.utils import (
    hash_password, verify_password, generate_token, 
    success_response, error_response, validate_email, serialize_document
)
from app.services import Database
from app.models import User
from bson import ObjectId

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

# Google OAuth setup
oauth = OAuth()
google = oauth.remote_app(
    'google',
    consumer_key=current_app.config.get('GOOGLE_CLIENT_ID', ''),
    consumer_secret=current_app.config.get('GOOGLE_CLIENT_SECRET', ''),
    request_token_params={
        'scope': 'email profile'
    },
    base_url='https://www.googleapis.com/oauth2/v1/',
    request_token_url=None,
    access_token_method='POST',
    access_token_url='https://accounts.google.com/o/oauth2/token',
    authorize_url='https://accounts.google.com/o/oauth2/auth',
)
oauth.init_app(current_app)

@auth_bp.route('/signup', methods=['POST'])
def signup():
    """User signup endpoint"""
    data = request.get_json()
    
    # Validation
    if not data or not all(k in data for k in ['email', 'password', 'username']):
        return error_response('Missing required fields', 400)
    
    email = data.get('email', '').strip().lower()
    password = data.get('password', '').strip()
    username = data.get('username', '').strip()
    full_name = data.get('full_name', '').strip()
    
    if not validate_email(email):
        return error_response('Invalid email format', 400)
    
    if len(password) < 8:
        return error_response('Password must be at least 8 characters', 400)
    
    if len(username) < 3:
        return error_response('Username must be at least 3 characters', 400)
    
    db = Database()
    
    # Check if email exists
    if db.find_one('users', {'email': email}):
        return error_response('Email already registered', 400)
    
    # Check if username exists
    if db.find_one('users', {'username': username}):
        return error_response('Username already taken', 400)
    
    # Create user
    password_hash = hash_password(password)
    user_doc = User.create_user_doc(email, username, password_hash, full_name)
    
    user_id = db.insert_one('users', user_doc)
    
    if not user_id:
        return error_response('Failed to create user', 500)
    
    # Generate token
    token = generate_token(user_id)
    
    user_doc['_id'] = user_id
    del user_doc['password_hash']
    
    return success_response({
        'user': serialize_document(user_doc),
        'token': token
    }, 'User created successfully', 201)

@auth_bp.route('/login', methods=['POST'])
def login():
    """User login endpoint"""
    data = request.get_json()
    
    if not data or not all(k in data for k in ['email', 'password']):
        return error_response('Missing email or password', 400)
    
    email = data.get('email', '').strip().lower()
    password = data.get('password', '').strip()
    
    db = Database()
    user = db.find_one('users', {'email': email})
    
    if not user or not verify_password(password, user['password_hash']):
        return error_response('Invalid email or password', 401)
    
    if not user.get('is_active'):
        return error_response('Account is inactive', 403)
    
    # Update last login
    from datetime import datetime
    db.update_one('users', {'_id': user['_id']}, {'last_login': datetime.utcnow()})
    
    # Generate token
    token = generate_token(str(user['_id']))
    
    # Remove sensitive data
    del user['password_hash']
    user = serialize_document(user)
    
    return success_response({
        'user': user,
        'token': token
    }, 'Login successful', 200)

@auth_bp.route('/verify-email', methods=['POST'])
def verify_email():
    """Verify email token endpoint (placeholder for email verification)"""
    data = request.get_json()
    
    if not data or 'token' not in data:
        return error_response('Missing token', 400)
    
    # In production, verify email token and mark user as verified
    return success_response(None, 'Email verified successfully', 200)

@auth_bp.route('/refresh-token', methods=['POST'])
def refresh_token():
    """Refresh JWT token"""
    data = request.get_json()
    
    if not data or 'refresh_token' not in data:
        return error_response('Missing refresh token', 400)
    
    # In production, decode refresh token and generate new access token
    return success_response({'token': 'new_token'}, 'Token refreshed', 200)

@auth_bp.route('/logout', methods=['POST'])
def logout():
    """User logout endpoint"""
    # In production, invalidate token in Redis
    return success_response(None, 'Logged out successfully', 200)

@auth_bp.route('/google')
def google_login():
    callback=url_for('auth.google_authorized', _external=True)
    return google.authorize(callback=callback)

@auth_bp.route('/google/callback')
def google_authorized():
    resp = google.authorized_response()
    if resp is None or resp.get('access_token') is None:
        return redirect(url_for('auth_page', error='Google login failed'))
    session['google_token'] = (resp['access_token'], '')
    userinfo = google.get('userinfo')
    if not userinfo.data.get('email'):
        return redirect(url_for('auth_page', error='Google login failed'))
    # Find or create user
    db = Database()
    user = db.find_one('users', {'email': userinfo.data['email']})
    if not user:
        user_doc = User.create_user_doc(
            userinfo.data['email'],
            userinfo.data.get('name', userinfo.data['email'].split('@')[0]),
            '',
            userinfo.data.get('name', ''),
            userinfo.data.get('picture', '')
        )
        user_id = db.insert_one('users', user_doc)
        user = db.find_one('users', {'_id': user_id})
    # Generate token
    token = generate_token(str(user['_id']))
    # Log in user (set session or return token)
    return redirect(url_for('auth_page', token=token))

google.tokengetter(lambda: session.get('google_token'))
