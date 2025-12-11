from flask import Blueprint, request
from app.utils import (
    success_response, error_response, serialize_document
)
from app.services import Database
from app.models import Group, Channel
from bson import ObjectId
from functools import wraps
from flask import g
import jwt
from flask import current_app

groups_bp = Blueprint('groups', __name__, url_prefix='/api/groups')

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

@groups_bp.route('', methods=['POST'])
@require_auth
def create_group():
    """Create a new group"""
    data = request.get_json()
    
    if not data or 'name' not in data:
        return error_response('Group name is required', 400)
    
    name = data.get('name', '').strip()
    description = data.get('description', '').strip()
    is_private = data.get('is_private', False)
    avatar_url = data.get('avatar_url', '')
    
    if len(name) < 3:
        return error_response('Group name must be at least 3 characters', 400)
    
    db = Database()
    group_doc = Group.create_group_doc(name, description, g.user_id, is_private, avatar_url)
    
    group_id = db.insert_one('groups', group_doc)
    
    if not group_id:
        return error_response('Failed to create group', 500)
    
    group_doc['_id'] = group_id
    return success_response(serialize_document(group_doc), 'Group created successfully', 201)

@groups_bp.route('/<group_id>', methods=['GET'])
@require_auth
def get_group(group_id):
    """Get group details"""
    try:
        group_id_obj = ObjectId(group_id)
    except:
        return error_response('Invalid group ID', 400)
    
    db = Database()
    group = db.find_one('groups', {'_id': group_id_obj})
    
    if not group:
        return error_response('Group not found', 404)
    
    # Check if user is member
    if group['is_private'] and ObjectId(g.user_id) not in group['members']:
        return error_response('Access denied', 403)
    
    return success_response(serialize_document(group), 'Group retrieved successfully', 200)

@groups_bp.route('/<group_id>', methods=['PUT'])
@require_auth
def update_group(group_id):
    """Update group details"""
    try:
        group_id_obj = ObjectId(group_id)
    except:
        return error_response('Invalid group ID', 400)
    
    db = Database()
    group = db.find_one('groups', {'_id': group_id_obj})
    
    if not group:
        return error_response('Group not found', 404)
    
    # Check if user is owner
    if str(group['owner_id']) != g.user_id:
        return error_response('Only group owner can update group', 403)
    
    data = request.get_json()
    
    update_fields = {}
    if 'name' in data:
        update_fields['name'] = data['name'].strip()
    if 'description' in data:
        update_fields['description'] = data['description'].strip()
    if 'is_private' in data:
        update_fields['is_private'] = data['is_private']
    if 'avatar_url' in data:
        update_fields['avatar_url'] = data['avatar_url']
    
    if update_fields:
        from datetime import datetime
        update_fields['updated_at'] = datetime.utcnow()
        db.update_one('groups', {'_id': group_id_obj}, update_fields)
    
    updated_group = db.find_one('groups', {'_id': group_id_obj})
    return success_response(serialize_document(updated_group), 'Group updated successfully', 200)

@groups_bp.route('/<group_id>', methods=['DELETE'])
@require_auth
def delete_group(group_id):
    """Delete a group"""
    try:
        group_id_obj = ObjectId(group_id)
    except:
        return error_response('Invalid group ID', 400)
    
    db = Database()
    group = db.find_one('groups', {'_id': group_id_obj})
    
    if not group:
        return error_response('Group not found', 404)
    
    # Check if user is owner
    if str(group['owner_id']) != g.user_id:
        return error_response('Only group owner can delete group', 403)
    
    # Delete associated channels and messages
    db.delete_many('channels', {'group_id': group_id_obj})
    db.delete_many('messages', {'group_id': group_id_obj})
    db.delete_many('whiteboards', {'group_id': group_id_obj})
    db.delete_many('competitions', {'group_id': group_id_obj})
    db.delete_many('files', {'group_id': group_id_obj})
    
    # Delete group
    db.delete_one('groups', {'_id': group_id_obj})
    
    return success_response(None, 'Group deleted successfully', 200)

@groups_bp.route('/<group_id>/join', methods=['POST'])
@require_auth
def join_group(group_id):
    """Join a group"""
    try:
        group_id_obj = ObjectId(group_id)
    except:
        return error_response('Invalid group ID', 400)
    
    db = Database()
    group = db.find_one('groups', {'_id': group_id_obj})
    
    if not group:
        return error_response('Group not found', 404)
    
    if group['is_private']:
        return error_response('Cannot join private group without invitation', 403)
    
    user_id_obj = ObjectId(g.user_id)
    
    if user_id_obj in group['members']:
        return error_response('Already a member of this group', 400)
    
    db.push_to_array('groups', {'_id': group_id_obj}, 'members', user_id_obj)
    db.push_to_array('users', {'_id': user_id_obj}, 'groups', group_id_obj)
    
    return success_response(None, 'Joined group successfully', 200)

@groups_bp.route('/<group_id>/leave', methods=['POST'])
@require_auth
def leave_group(group_id):
    """Leave a group"""
    try:
        group_id_obj = ObjectId(group_id)
    except:
        return error_response('Invalid group ID', 400)
    
    db = Database()
    group = db.find_one('groups', {'_id': group_id_obj})
    
    if not group:
        return error_response('Group not found', 404)
    
    user_id_obj = ObjectId(g.user_id)
    
    if user_id_obj not in group['members']:
        return error_response('Not a member of this group', 400)
    
    # Cannot leave if owner
    if str(group['owner_id']) == g.user_id:
        return error_response('Group owner cannot leave the group', 403)
    
    db.pull_from_array('groups', {'_id': group_id_obj}, 'members', user_id_obj)
    db.pull_from_array('users', {'_id': user_id_obj}, 'groups', group_id_obj)
    
    return success_response(None, 'Left group successfully', 200)

@groups_bp.route('/<group_id>/members', methods=['GET'])
@require_auth
def get_group_members(group_id):
    """Get group members"""
    try:
        group_id_obj = ObjectId(group_id)
    except:
        return error_response('Invalid group ID', 400)
    
    db = Database()
    group = db.find_one('groups', {'_id': group_id_obj})
    
    if not group:
        return error_response('Group not found', 404)
    
    # Get member details
    members = db.find('users', {'_id': {'$in': group['members']}})
    
    # Remove sensitive data
    for member in members:
        del member['password_hash']
    
    return success_response([serialize_document(m) for m in members], 'Members retrieved successfully', 200)

@groups_bp.route('/<group_id>/channels', methods=['GET'])
@require_auth
def get_group_channels(group_id):
    """Get channels in a group"""
    try:
        group_id_obj = ObjectId(group_id)
    except:
        return error_response('Invalid group ID', 400)
    
    db = Database()
    group = db.find_one('groups', {'_id': group_id_obj})
    
    if not group:
        return error_response('Group not found', 404)
    
    channels = db.find('channels', {'group_id': group_id_obj})
    return success_response([serialize_document(c) for c in channels], 'Channels retrieved successfully', 200)

@groups_bp.route('/<group_id>/channels', methods=['POST'])
@require_auth
def create_channel(group_id):
    """Create a channel in a group"""
    try:
        group_id_obj = ObjectId(group_id)
    except:
        return error_response('Invalid group ID', 400)
    
    data = request.get_json()
    
    if not data or 'name' not in data:
        return error_response('Channel name is required', 400)
    
    db = Database()
    group = db.find_one('groups', {'_id': group_id_obj})
    
    if not group:
        return error_response('Group not found', 404)
    
    # Check if user is owner or moderator
    user_id_obj = ObjectId(g.user_id)
    if user_id_obj not in group['moderators']:
        return error_response('Only group moderators can create channels', 403)
    
    name = data.get('name', '').strip()
    description = data.get('description', '').strip()
    is_private = data.get('is_private', False)
    
    if len(name) < 2:
        return error_response('Channel name must be at least 2 characters', 400)
    
    channel_doc = Channel.create_channel_doc(name, group_id, description, is_private)
    
    channel_id = db.insert_one('channels', channel_doc)
    
    if not channel_id:
        return error_response('Failed to create channel', 500)
    
    db.push_to_array('groups', {'_id': group_id_obj}, 'channels', ObjectId(channel_id))
    
    channel_doc['_id'] = channel_id
    return success_response(serialize_document(channel_doc), 'Channel created successfully', 201)
