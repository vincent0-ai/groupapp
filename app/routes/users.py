from flask import Blueprint, request, g
from app.utils import success_response, error_response, serialize_document
from app.services import Database
from app.models import User
from bson import ObjectId
from functools import wraps
import jwt
from flask import current_app
from datetime import datetime
from app.utils.decorators import require_auth

users_bp = Blueprint('users', __name__, url_prefix='/api/users')
@users_bp.route('/search', methods=['GET'])
@require_auth
def search_users():
    """Search users"""
    query = request.args.get('q', '').strip()
    
    db = Database()
    
    if not query or len(query) < 2:
        # Return some suggested users (most recently active users, excluding current user)
        users = list(db.find('users', 
            {'_id': {'$ne': ObjectId(g.user_id)}},
            limit=10, 
            sort=('updated_at', -1)
        ))
    else:
        # Search by username and full_name
        users = list(db.find('users', {
            '$and': [
                {'_id': {'$ne': ObjectId(g.user_id)}},
                {'$or': [
                    {
                    'username': {'$regex': __import__('re').escape(query), '$options': 'i'}
                },
                    {'full_name': {'$regex': __import__('re').escape(query), '$options': 'i'}}
                ]}
            ]
        }, limit=20))
    
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
            'badges': user.get('badges', []),
            'groups_count': groups_count
        })
    
    return success_response(public_users, 'Users found successfully', 200)


@users_bp.route('/profile', methods=['GET'])
@require_auth
def get_profile():
    """Get current user profile"""
    db = Database()
    user = db.find_one('users', {'_id': ObjectId(g.user_id)})
    
    if not user:
        return error_response('User not found', 404)
    
    # Remove sensitive and deprecated fields
    del user['password_hash']
    user.pop('points', None)  # Points have been removed
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
        'badges': user.get('badges', []),
        'groups_count': groups_count,
        'created_at': user.get('created_at').isoformat() if user.get('created_at') else None,
        'is_admin': user.get('is_admin', False),
        'role': user.get('role', 'user')
    }
    
    return success_response(public_profile, 'User profile retrieved successfully', 200)



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


@users_bp.route('/activity', methods=['GET'])
@require_auth
def get_user_activity():
    """Get recent activity for the current user"""
    db = Database()
    user_id = g.user_id
    user_id_obj = ObjectId(user_id)
    
    activities = []
    
    # Get recent groups joined
    user = db.find_one('users', {'_id': user_id_obj})
    if user:
        user_groups = user.get('groups', [])
        groups = list(db.find('groups', {'members': user_id_obj}, limit=5, sort=('updated_at', -1)))
        for g_item in groups:
            activities.append({
                'type': 'group_join',
                'message': f"Joined group '{g_item.get('name', 'Unknown')}'",
                'created_at': g_item.get('updated_at', g_item.get('created_at')).isoformat() if g_item.get('updated_at') or g_item.get('created_at') else None,
                'related_id': str(g_item['_id'])
            })
    
    # Get recent DM activity
    dm_messages = list(db.db.dm_messages.find(
        {'sender_id': user_id_obj}
    ).sort('created_at', -1).limit(5))
    
    for msg in dm_messages:
        activities.append({
            'type': 'dm_sent',
            'message': 'Sent a direct message',
            'created_at': msg.get('created_at').isoformat() if msg.get('created_at') else None,
            'related_id': str(msg['_id'])
        })
    
    # Get recent file uploads
    files = list(db.find('files', {'uploaded_by': user_id_obj}, limit=5, sort=('created_at', -1)))
    for f in files:
        activities.append({
            'type': 'file_upload',
            'message': f"Uploaded file '{f.get('filename', 'Unknown')}'",
            'created_at': f.get('created_at').isoformat() if f.get('created_at') else None,
            'related_id': str(f['_id'])
        })
    
    # Get competition participations
    competitions = list(db.find('competitions', {'participants': user_id_obj}, limit=5, sort=('updated_at', -1)))
    for c in competitions:
        activities.append({
            'type': 'competition_join',
            'message': f"Participated in '{c.get('title', 'Unknown')}'",
            'created_at': c.get('updated_at', c.get('created_at')).isoformat() if c.get('updated_at') or c.get('created_at') else None,
            'related_id': str(c['_id'])
        })
    
    # Get login activity if last_login exists
    if user and user.get('last_login'):
        activities.append({
            'type': 'login',
            'message': 'Logged in',
            'created_at': user.get('last_login').isoformat(),
            'related_id': None
        })
    
    # Sort all activities by date
    activities.sort(key=lambda x: x.get('created_at') or '', reverse=True)
    
    # Limit to 10 most recent
    activities = activities[:10]
    
    return success_response(activities, 'Activity retrieved successfully', 200)


# search_users moved to top of file to avoid route conflict with /<user_id>
