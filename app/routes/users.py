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
    """Get user public profile (restricted data)"""
    try:
        user_id_obj = ObjectId(user_id)
    except:
        return error_response('Invalid user ID', 400)
    
    db = Database()
    user = db.find_one('users', {'_id': user_id_obj})
    
    if not user:
        return error_response('User not found', 404)
    
    # Count groups user is a member of
    groups_count = db.count('groups', {'members': user_id_obj})
    
    # Return only public fields - exclude email and other sensitive data
    public_profile = {
        'id': str(user['_id']),
        'username': user.get('username', ''),
        'full_name': user.get('full_name', ''),
        'avatar_url': user.get('avatar_url') or f"https://api.dicebear.com/7.x/avataaars/svg?seed={user.get('username', '')}",
        'bio': user.get('bio', ''),
        'points': user.get('points', 0),
        'badges': user.get('badges', []),
        'groups_count': groups_count,
        'created_at': user.get('created_at').isoformat() if user.get('created_at') else None,
        'is_admin': user.get('is_admin', False),
        'role': user.get('role', 'user')
    }
    
    return success_response(public_profile, 'User profile retrieved successfully', 200)

@users_bp.route('/leaderboard', methods=['GET'])
def get_leaderboard():
    """Get global leaderboard"""
    db = Database()
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    skip = (page - 1) * per_page
    
    # Get users sorted by points
    users = list(db.find('users', {}, skip=skip, limit=per_page, sort=('points', -1)))
    
    total = db.count('users')
    
    # Build public profile data for each user
    leaderboard_users = []
    for user in users:
        user_id_obj = user['_id']
        groups_count = db.count('groups', {'members': user_id_obj})
        leaderboard_users.append({
            'id': str(user['_id']),
            '_id': str(user['_id']),
            'username': user.get('username', ''),
            'full_name': user.get('full_name', ''),
            'avatar_url': user.get('avatar_url') or f"https://api.dicebear.com/7.x/avataaars/svg?seed={user.get('username', '')}",
            'points': user.get('points', 0),
            'badges': user.get('badges', []),
            'groups_count': groups_count
        })
    
    return success_response({
        'leaderboard': leaderboard_users,
        'users': leaderboard_users,  # Keep for backward compatibility
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
    
    # Add member count and id field to each group
    for group in groups:
        group['member_count'] = len(group.get('members', []))
        channel_doc = None
        if group.get('channel_id'):
            channel_doc = db.find_one('channels', {'_id': group.get('channel_id')})
        if channel_doc:
            channel_doc['id'] = str(channel_doc['_id'])
            group['channel'] = serialize_document(channel_doc)
        else:
            group['channel'] = None
        group['id'] = str(group['_id'])  # Add 'id' field for frontend
    
    return success_response({'groups': [serialize_document(grp) for grp in groups]}, 'User groups retrieved successfully', 200)

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


@users_bp.route('/push-subscription', methods=['POST'])
@require_auth
def save_push_subscription():
    """Save push notification subscription for the user"""
    data = request.get_json()
    
    if not data or 'subscription' not in data:
        return error_response('Subscription data required', 400)
    
    db = Database()
    
    # Store the subscription
    db.update_one('users', {'_id': ObjectId(g.user_id)}, {
        'push_subscription': data['subscription'],
        'push_subscribed_at': datetime.utcnow()
    })
    
    return success_response(None, 'Push subscription saved', 200)


@users_bp.route('/push-subscription', methods=['DELETE'])
@require_auth
def remove_push_subscription():
    """Remove push notification subscription for the user"""
    db = Database()
    
    db.db.users.update_one(
        {'_id': ObjectId(g.user_id)},
        {'$unset': {'push_subscription': '', 'push_subscribed_at': ''}}
    )
    
    return success_response(None, 'Push subscription removed', 200)


@users_bp.route('/search', methods=['GET'])
def search_users():
    """Search users"""
    query = request.args.get('q', '').strip()
    
    if not query:
        return error_response('Search query is required', 400)
    
    db = Database()
    
    # Simple regex search on username and full_name only (not email for privacy)
    users = db.find('users', {
        '$or': [
            {'username': {'$regex': query, '$options': 'i'}},
            {'full_name': {'$regex': query, '$options': 'i'}}
        ]
    }, limit=20)
    
    # Return only public fields
    public_users = []
    for user in users:
        user_id_obj = user['_id']
        groups_count = db.count('groups', {'members': user_id_obj})
        public_users.append({
            '_id': str(user['_id']),
            'id': str(user['_id']),
            'username': user.get('username', ''),
            'full_name': user.get('full_name', ''),
            'avatar_url': user.get('avatar_url') or f"https://api.dicebear.com/7.x/avataaars/svg?seed={user.get('username', '')}",
            'points': user.get('points', 0),
            'badges': user.get('badges', []),
            'groups_count': groups_count
        })
    
    return success_response(public_users, 'Users found successfully', 200)
