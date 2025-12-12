from flask import Blueprint, request, g
from app.utils.decorators import admin_required
from app.utils.helpers import success_response, error_response, serialize_document
from app.services import Database
from bson import ObjectId
from datetime import datetime

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')

@admin_bp.route('/stats', methods=['GET'])
@admin_required
def get_stats():
    """Get admin dashboard stats"""
    db = Database()
    
    stats = {
        'total_users': db.count('users', {}),
        'total_groups': db.count('groups', {}),
        'total_channels': db.count('channels', {}),
        'total_messages': db.count('messages', {}),
        'active_users_24h': db.count('users', {
            'last_login': {'$gte': datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)} # Approximation
        })
    }
    
    return success_response(stats)

@admin_bp.route('/users', methods=['GET'])
@admin_required
def get_users():
    """Get all users with pagination"""
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 20))
    search = request.args.get('search', '')
    
    query = {}
    if search:
        query['$or'] = [
            {'username': {'$regex': search, '$options': 'i'}},
            {'email': {'$regex': search, '$options': 'i'}},
            {'full_name': {'$regex': search, '$options': 'i'}}
        ]
    
    db = Database()
    users = db.find('users', query, skip=(page-1)*limit, limit=limit, sort=[('created_at', -1)])
    total = db.count('users', query)
    
    # Remove sensitive data
    for user in users:
        if 'password_hash' in user:
            del user['password_hash']
            
    return success_response({
        'users': serialize_document(users),
        'total': total,
        'page': page,
        'pages': (total + limit - 1) // limit
    })

@admin_bp.route('/users/<user_id>/ban', methods=['POST'])
@admin_required
def ban_user(user_id):
    """Ban a user"""
    db = Database()
    
    # Prevent banning self
    if user_id == g.user_id:
        return error_response('Cannot ban yourself', 400)
        
    result = db.update_one('users', {'_id': ObjectId(user_id)}, {'is_active': False})
    
    if result:
        return success_response(message='User banned successfully')
    return error_response('User not found or already banned', 404)

@admin_bp.route('/users/<user_id>/unban', methods=['POST'])
@admin_required
def unban_user(user_id):
    """Unban a user"""
    db = Database()
    
    result = db.update_one('users', {'_id': ObjectId(user_id)}, {'is_active': True})
    
    if result:
        return success_response(message='User unbanned successfully')
    return error_response('User not found or already active', 404)

@admin_bp.route('/groups', methods=['GET'])
@admin_required
def get_groups():
    """Get all groups with pagination"""
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 20))
    search = request.args.get('search', '')
    
    query = {}
    if search:
        query['name'] = {'$regex': search, '$options': 'i'}
    
    db = Database()
    groups = db.find('groups', query, skip=(page-1)*limit, limit=limit, sort=[('created_at', -1)])
    total = db.count('groups', query)
    
    return success_response({
        'groups': serialize_document(groups),
        'total': total,
        'page': page,
        'pages': (total + limit - 1) // limit
    })

@admin_bp.route('/groups/<group_id>', methods=['DELETE'])
@admin_required
def delete_group(group_id):
    """Delete a group"""
    db = Database()
    
    # Also delete associated messages, files, etc?
    # For now just delete the group document
    result = db.delete_one('groups', {'_id': ObjectId(group_id)})
    
    if result:
        # Clean up messages
        db.delete_many('messages', {'group_id': ObjectId(group_id)})
        return success_response(message='Group deleted successfully')
    return error_response('Group not found', 404)

@admin_bp.route('/channels', methods=['GET'])
@admin_required
def get_channels():
    """Get all channels"""
    db = Database()
    channels = db.find('channels', {}, sort=[('name', 1)])
    return success_response(serialize_document(channels))

@admin_bp.route('/channels/<channel_id>', methods=['DELETE'])
@admin_required
def delete_channel(channel_id):
    """Delete a channel"""
    db = Database()
    
    # Check if channel has groups
    if db.count('groups', {'channel_id': ObjectId(channel_id)}) > 0:
        return error_response('Cannot delete channel with existing groups', 400)
        
    result = db.delete_one('channels', {'_id': ObjectId(channel_id)})
    
    if result:
        return success_response(message='Channel deleted successfully')
    return error_response('Channel not found', 404)
