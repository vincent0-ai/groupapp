from flask import Blueprint, request, g
from app.utils import success_response, error_response, serialize_document
from app.services import Database
from app.models import User
from bson import ObjectId
from functools import wraps
import jwt
from flask import current_app
from datetime import datetime

users_bp = Blueprint('users', __name__, url_prefix='/api/users')

def require_auth(f):
    """Decorator to require authentication"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            return error_response('Missing or invalid authorization', 401)
        
        token = auth_header.split(' ')[1]
        
        try:
            payload = jwt.decode(
                token,
                current_app.config['JWT_SECRET_KEY'],
                algorithms=[current_app.config['JWT_ALGORITHM']]
            )
            g.user_id = payload['user_id']
        except jwt.ExpiredSignatureError:
            return error_response('Token expired', 401)
        except jwt.InvalidTokenError:
            return error_response('Invalid token', 401)
        
        return f(*args, **kwargs)
    
    return decorated

@users_bp.route('/profile', methods=['GET'])
@require_auth
def get_profile():
    """Get current user profile"""
    db = Database()
    user = db.find_one('users', {'_id': ObjectId(g.user_id)})
    
    if not user:
        return error_response('User not found', 404)
    
    del user['password_hash']
    return success_response(serialize_document(user), 'Profile retrieved successfully', 200)

@users_bp.route('/profile', methods=['PUT'])
@require_auth
def update_profile():
    """Update user profile"""
    data = request.get_json()
    
    db = Database()
    user_id_obj = ObjectId(g.user_id)
    
    update_fields = {}
    
    if 'full_name' in data:
        update_fields['full_name'] = data['full_name'].strip()
    if 'bio' in data:
        update_fields['bio'] = data['bio'].strip()
    if 'avatar_url' in data:
        update_fields['avatar_url'] = data['avatar_url'].strip()
    if 'preferences' in data:
        update_fields['preferences'] = data['preferences']
    
    if update_fields:
        update_fields['updated_at'] = datetime.utcnow()
        db.update_one('users', {'_id': user_id_obj}, update_fields)
    
    updated_user = db.find_one('users', {'_id': user_id_obj})
    del updated_user['password_hash']
    
    return success_response(serialize_document(updated_user), 'Profile updated successfully', 200)

@users_bp.route('/<user_id>', methods=['GET'])
def get_user(user_id):
    """Get user public profile"""
    try:
        user_id_obj = ObjectId(user_id)
    except:
        return error_response('Invalid user ID', 400)
    
    db = Database()
    user = db.find_one('users', {'_id': user_id_obj})
    
    if not user:
        return error_response('User not found', 404)
    
    # Remove sensitive data
    del user['password_hash']
    del user['preferences']
    
    return success_response(serialize_document(user), 'User profile retrieved successfully', 200)

@users_bp.route('/leaderboard', methods=['GET'])
def get_leaderboard():
    """Get global leaderboard"""
    db = Database()
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    skip = (page - 1) * per_page
    
    # Get users sorted by points
    users = db.find('users', {}, skip=skip, limit=per_page, sort=('points', -1))
    
    total = db.count('users')
    
    for user in users:
        del user['password_hash']
        del user['preferences']
    
    return success_response({
        'users': [serialize_document(u) for u in users],
        'total': total,
        'page': page,
        'per_page': per_page
    }, 'Leaderboard retrieved successfully', 200)

@users_bp.route('/groups', methods=['GET'])
@require_auth
def get_current_user_groups():
    """Get groups for current user"""
    db = Database()
    user = db.find_one('users', {'_id': ObjectId(g.user_id)})
    
    if not user:
        return error_response('User not found', 404)
    
    # Get groups where user is a member
    groups = list(db.find('groups', {'members': ObjectId(g.user_id)}))
    
    # Add member count to each group
    for group in groups:
        group['member_count'] = len(group.get('members', []))
        group['channels'] = list(db.find('channels', {'group_id': group['_id']}))
    
    return success_response({'groups': [serialize_document(g) for g in groups]}, 'User groups retrieved successfully', 200)

@users_bp.route('/<user_id>/groups', methods=['GET'])
@require_auth
def get_user_groups(user_id):
    """Get groups for a user"""
    try:
        user_id_obj = ObjectId(user_id)
    except:
        return error_response('Invalid user ID', 400)
    
    db = Database()
    user = db.find_one('users', {'_id': user_id_obj})
    
    if not user:
        return error_response('User not found', 404)
    
    # Get groups
    groups = db.find('groups', {'_id': {'$in': user.get('groups', [])}})
    
    return success_response([serialize_document(g) for g in groups], 'User groups retrieved successfully', 200)

@users_bp.route('/search', methods=['GET'])
def search_users():
    """Search users"""
    query = request.args.get('q', '').strip()
    
    if not query:
        return error_response('Search query is required', 400)
    
    db = Database()
    
    # Simple regex search (in production, use Meilisearch)
    users = db.find('users', {
        '$or': [
            {'username': {'$regex': query, '$options': 'i'}},
            {'full_name': {'$regex': query, '$options': 'i'}},
            {'email': {'$regex': query, '$options': 'i'}}
        ]
    }, limit=20)
    
    for user in users:
        del user['password_hash']
        del user['preferences']
    
    return success_response([serialize_document(u) for u in users], 'Users found successfully', 200)
