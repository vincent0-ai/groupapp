import bcrypt
from datetime import datetime, timedelta
import jwt
import os
from flask import current_app, request
from app.services import Database
from bson import ObjectId

def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    rounds = current_app.config.get('BCRYPT_ROUNDS', 12)
    salt = bcrypt.gensalt(rounds=rounds)
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash"""
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))

def generate_token(user_id: str, expires_in: int = 3600) -> str:
    """Generate a JWT token for a user"""
    payload = {
        'user_id': str(user_id),
        'exp': datetime.utcnow() + timedelta(seconds=expires_in),
        'iat': datetime.utcnow()
    }
    token = jwt.encode(
        payload,
        current_app.config['JWT_SECRET_KEY'],
        algorithm=current_app.config['JWT_ALGORITHM']
    )
    return token

def verify_token(token: str) -> dict:
    """Verify and decode a JWT token"""
    try:
        payload = jwt.decode(
            token,
            current_app.config['JWT_SECRET_KEY'],
            algorithms=[current_app.config['JWT_ALGORITHM']]
        )
        return payload
    except jwt.ExpiredSignatureError:
        return {'error': 'Token expired'}
    except jwt.InvalidTokenError:
        return {'error': 'Invalid token'}

def generate_refresh_token(user_id: str, expires_in: int = 604800) -> str:
    """Generate a refresh token (valid for 7 days)"""
    payload = {
        'user_id': str(user_id),
        'type': 'refresh',
        'exp': datetime.utcnow() + timedelta(seconds=expires_in),
        'iat': datetime.utcnow()
    }
    token = jwt.encode(
        payload,
        current_app.config['JWT_SECRET_KEY'],
        algorithm=current_app.config['JWT_ALGORITHM']
    )
    return token

def get_current_user():
    """Get the current user from the JWT token in the request header"""
    token = None
    if 'Authorization' in request.headers and request.headers['Authorization'].startswith('Bearer '):
        token = request.headers['Authorization'].split(' ')[1]

    # Do not accept tokens from cookies (CSRF risk). API should use Authorization header bearer tokens.
    if not token:
        return None

    payload = verify_token(token)
    if 'error' in payload or 'user_id' not in payload:
        return None

    user_id = payload['user_id']
    try:
        db = Database()
        user = db.find_one('users', {'_id': ObjectId(user_id)})
        return user
    except Exception:
        return None