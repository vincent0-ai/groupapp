from flask import Blueprint, request
from app.utils import (
    success_response, error_response, serialize_document
)
from app.services import Database
from app.models import Group, Channel, Whiteboard
from bson import ObjectId
from functools import wraps
from flask import g
import jwt
from flask import current_app
from datetime import datetime

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

@groups_bp.route('', methods=['GET'])
@require_auth
def get_all_groups():
    """Get all groups"""
    db = Database()
    user_id_obj = ObjectId(g.user_id)
    
    # Get all groups
    groups = list(db.find('groups', {}))
    
    # Add member count and id field
    for group in groups:
        group['member_count'] = len(group.get('members', []))
        group['id'] = str(group['_id'])
        group['is_member'] = user_id_obj in group.get('members', [])
        # Check if pending
        group['is_pending'] = user_id_obj in group.get('pending_members', [])
    
    return success_response({'groups': [serialize_document(grp) for grp in groups]}, 'Groups retrieved successfully', 200)

@groups_bp.route('', methods=['POST'])
@require_auth
def create_group():
    """Create a new group"""
    data = request.get_json()
    
    if not data or 'name' not in data:
        return error_response('Group name is required', 400)
    
    name = data.get('name', '').strip()
    description = data.get('description', '').strip()
    channel_id = data.get('channel_id')
    category = data.get('category', '').strip()
    is_private = data.get('is_private', False)
    avatar_url = data.get('avatar_url', '')
    
    if len(name) < 3:
        return error_response('Group name must be at least 3 characters', 400)
    
    db = Database()

    # Resolve channel: use explicit channel_id if provided, otherwise find/create by category name
    channel_obj_id = None
    if channel_id:
        try:
            cid = ObjectId(channel_id)
            ch = db.find_one('channels', {'_id': cid})
            if not ch:
                return error_response('Channel not found', 404)
            channel_obj_id = cid
        except Exception:
            return error_response('Invalid channel ID', 400)
    else:
        if not category:
            category = 'General'
        existing_channel = db.find_one('channels', {'name': category})
        if not existing_channel:
            channel_doc = Channel.create_channel_doc(category, '')
            db.insert_one('channels', channel_doc)
            existing_channel = db.find_one('channels', {'name': category})
            if existing_channel:
                db.update_one('channels', {'_id': existing_channel['_id']}, {'group_count': 1, 'updated_at': datetime.utcnow()})
                channel_obj_id = existing_channel['_id']
        else:
            db.update_one('channels', {'_id': existing_channel['_id']}, {'group_count': (existing_channel.get('group_count', 0) + 1), 'updated_at': datetime.utcnow()})
            channel_obj_id = existing_channel['_id']

    group_doc = Group.create_group_doc(name, description, g.user_id, str(channel_obj_id) if channel_obj_id else None, is_private, avatar_url)

    # Insert returns the string ID, but the doc already has _id as ObjectId
    inserted_id = db.insert_one('groups', group_doc)
    
    if not inserted_id:
        return error_response('Failed to create group', 500)

    # Award points
    try:
        points = current_app.config['POINTS_CONFIG']['CREATE_GROUP']
        db.increment('users', {'_id': ObjectId(g.user_id)}, 'points', points)
    except Exception as e:
        print(f"Error awarding points: {e}")

    # Fetch the created group to return complete document
    created_group = db.find_one('groups', {'_id': group_doc['_id']})
    created_group['id'] = str(created_group['_id'])
    if created_group.get('channel_id'):
        ch = db.find_one('channels', {'_id': created_group['channel_id']})
        created_group['channel'] = serialize_document(ch) if ch else None
    return success_response(serialize_document(created_group), 'Group created successfully', 201)

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
    
    # Attach channel information if present
    if group.get('channel_id'):
        ch = db.find_one('channels', {'_id': group['channel_id']})
        group['channel'] = serialize_document(ch) if ch else None
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
    
    # Delete associated messages, whiteboards, competitions, and files
    db.delete_many('messages', {'group_id': group_id_obj})
    db.delete_many('whiteboards', {'group_id': group_id_obj})
    db.delete_many('competitions', {'group_ids': group_id_obj})
    db.delete_many('files', {'group_id': group_id_obj})

    # Decrement channel group count
    channel_id = group.get('channel_id')
    if channel_id:
        ch = db.find_one('channels', {'_id': channel_id})
        if ch:
            new_count = max(0, ch.get('group_count', 1) - 1)
            db.update_one('channels', {'_id': ch['_id']}, {'group_count': new_count, 'updated_at': datetime.utcnow()})

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
    
    user_id_obj = ObjectId(g.user_id)

    if group.get('is_private'):
        # Check if already pending
        if user_id_obj in group.get('pending_members', []):
            return error_response('Join request already sent', 400)
            
        # Add to pending members
        db.push_to_array('groups', {'_id': group_id_obj}, 'pending_members', user_id_obj)
        return success_response(None, 'Join request sent successfully', 200)
    
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
    
    # Check if user is owner
    is_owner = str(group['owner_id']) == g.user_id
    members = group.get('members', [])
    
    if is_owner:
        if len(members) == 1:
            # Owner is the only member, delete the group
            db.delete_many('messages', {'group_id': group_id_obj})
            db.delete_many('whiteboards', {'group_id': group_id_obj})
            db.delete_many('competitions', {'group_ids': group_id_obj})
            db.delete_many('files', {'group_id': group_id_obj})

            # Decrement channel group count
            channel_id = group.get('channel_id')
            if channel_id:
                ch = db.find_one('channels', {'_id': channel_id})
                if ch:
                    new_count = max(0, ch.get('group_count', 1) - 1)
                    db.update_one('channels', {'_id': ch['_id']}, {'group_count': new_count, 'updated_at': datetime.utcnow()})

            db.delete_one('groups', {'_id': group_id_obj})
            db.pull_from_array('users', {'_id': user_id_obj}, 'groups', group_id_obj)
            return success_response(None, 'Left and deleted group (you were the last member)', 200)
        else:
            # Transfer ownership to another member
            new_owner = None
            for member in members:
                if member != user_id_obj:
                    new_owner = member
                    break
            
            # Update group owner
            db.update_one('groups', {'_id': group_id_obj}, {'owner_id': new_owner})
    
    # Remove user from group members
    db.pull_from_array('groups', {'_id': group_id_obj}, 'members', user_id_obj)
    db.pull_from_array('users', {'_id': user_id_obj}, 'groups', group_id_obj)
    
    if is_owner and len(members) > 1:
        return success_response(None, 'Left group successfully. Ownership transferred to another member.', 200)
    
    return success_response(None, 'Left group successfully', 200)

@groups_bp.route('/<group_id>/remove_member', methods=['POST'])
@require_auth
def remove_member(group_id):
    """Remove a member from the group (Owner/Moderator only)"""
    try:
        group_id_obj = ObjectId(group_id)
    except:
        return error_response('Invalid group ID', 400)
    
    data = request.get_json()
    target_user_id = data.get('user_id')
    if not target_user_id:
        return error_response('User ID is required', 400)
        
    try:
        target_user_id_obj = ObjectId(target_user_id)
    except:
        return error_response('Invalid user ID', 400)
    
    db = Database()
    group = db.find_one('groups', {'_id': group_id_obj})
    
    if not group:
        return error_response('Group not found', 404)
    
    # Check permissions
    user_id_obj = ObjectId(g.user_id)
    is_owner = str(group['owner_id']) == g.user_id
    is_mod = user_id_obj in group.get('moderators', [])
    
    if not (is_owner or is_mod):
        return error_response('Only owners and moderators can remove members', 403)
        
    # Cannot remove owner
    if str(group['owner_id']) == target_user_id:
        return error_response('Cannot remove the group owner', 400)
        
    # Moderators cannot remove other moderators or owner
    if is_mod and not is_owner:
        if target_user_id_obj in group.get('moderators', []) or str(group['owner_id']) == target_user_id:
            return error_response('Moderators cannot remove other moderators or the owner', 403)
            
    if target_user_id_obj not in group.get('members', []):
        return error_response('User is not a member of this group', 404)
        
    # Remove user
    db.pull_from_array('groups', {'_id': group_id_obj}, 'members', target_user_id_obj)
    db.pull_from_array('groups', {'_id': group_id_obj}, 'moderators', target_user_id_obj)
    db.pull_from_array('users', {'_id': target_user_id_obj}, 'groups', group_id_obj)
    
    return success_response(None, 'Member removed successfully', 200)

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
    members = list(db.find('users', {'_id': {'$in': group['members']}}))
    
    # Remove sensitive data and add id field
    for member in members:
        member['id'] = str(member['_id'])
        del member['password_hash']
        # Ensure avatar_url exists
        if not member.get('avatar_url'):
            member['avatar_url'] = f"https://api.dicebear.com/7.x/avataaars/svg?seed={member.get('username', member['id'])}"
    
    return success_response([serialize_document(m) for m in members], 'Members retrieved successfully', 200)

@groups_bp.route('/<group_id>/channels', methods=['GET'])
@require_auth
def get_group_channels(group_id):
    """(Deprecated) Returns the channel/category info for the group"""
    try:
        group_id_obj = ObjectId(group_id)
    except:
        return error_response('Invalid group ID', 400)
    
    db = Database()
    group = db.find_one('groups', {'_id': group_id_obj})
    
    if not group:
        return error_response('Group not found', 404)
    
    channel = None
    if group.get('channel_id'):
        channel = db.find_one('channels', {'_id': group.get('channel_id')})
    if not channel:
        return success_response([], 'No channel found for this group', 200)
    return success_response(serialize_document(channel), 'Channel retrieved successfully', 200)

@groups_bp.route('/<group_id>/channels', methods=['POST'])
@require_auth
def create_channel(group_id):
    """(Deprecated) Per-group channels are no longer supported; use /api/channels to create global categories"""
    return error_response('Per-group channels are deprecated. Use /api/channels to create a global channel (category).', 410)


# New endpoints for global channels (categories)
@groups_bp.route('/channels', methods=['GET'])
@require_auth
def list_channels():
    """List all channels (categories) and groups under each channel"""
    db = Database()
    user_id_obj = ObjectId(g.user_id)

    channels = list(db.find('channels', {}))
    result = []

    for ch in channels:
        # List all groups in the channel so users can find private ones
        groups = list(db.find('groups', {'channel_id': ch['_id']}))
        for group in groups:
            group['member_count'] = len(group.get('members', []))
            group['id'] = str(group['_id'])
            group['is_member'] = user_id_obj in group.get('members', [])
            group['is_pending'] = user_id_obj in group.get('pending_members', [])
        ch['group_count'] = len(groups)
        ch['groups'] = [serialize_document(g) for g in groups]
        ch['id'] = str(ch['_id'])
        result.append(serialize_document(ch))

    return success_response({'channels': result}, 'Channels retrieved successfully', 200)


@groups_bp.route('/<group_id>/whiteboards', methods=['POST'])
@require_auth
def create_whiteboard_session(group_id):
    """Create a new whiteboard session for a group (only owner)"""
    try:
        group_id_obj = ObjectId(group_id)
    except:
        return error_response('Invalid group ID', 400)

    db = Database()
    group = db.find_one('groups', {'_id': group_id_obj})
    if not group:
        return error_response('Group not found', 404)

    # Only owner can create a session
    if str(group['owner_id']) != g.user_id:
        return error_response('Only group owners can create whiteboard sessions', 403)

    data = request.get_json() or {}
    title = data.get('title', '').strip()

    whiteboard_doc = Whiteboard.create_whiteboard_doc(group_id, str(group.get('channel_id')) if group.get('channel_id') else None, g.user_id, title)
    inserted_id = db.insert_one('whiteboards', whiteboard_doc)
    if not inserted_id:
        return error_response('Failed to create whiteboard session', 500)

    # Add invite token (simple): use the inserted _id as token; return usable URL path
    whiteboard_doc = db.find_one('whiteboards', {'_id': whiteboard_doc['_id']})
    whiteboard_doc['id'] = str(whiteboard_doc['_id'])

    # Default permissions: all group members can draw and speak unless restricted
    member_ids = group.get('members', [])
    whiteboard_doc['can_draw'] = member_ids.copy()
    whiteboard_doc['can_speak'] = member_ids.copy()
    db.update_one('whiteboards', {'_id': whiteboard_doc['_id']}, {'can_draw': whiteboard_doc['can_draw'], 'can_speak': whiteboard_doc['can_speak']})

    # Build a simple invite URL
    invite_url = f"/whiteboard?session={whiteboard_doc['id']}"
    return success_response({'whiteboard': serialize_document(whiteboard_doc), 'invite_url': invite_url}, 'Whiteboard session created', 201)


@groups_bp.route('/<group_id>/whiteboards', methods=['GET'])
@require_auth
def list_whiteboards_for_group(group_id):
    try:
        group_id_obj = ObjectId(group_id)
    except:
        return error_response('Invalid group ID', 400)

    db = Database()
    group = db.find_one('groups', {'_id': group_id_obj})
    if not group:
        return error_response('Group not found', 404)

    user_id_obj = ObjectId(g.user_id)
    if group.get('is_private') and user_id_obj not in group.get('members', []):
        return error_response('Access denied', 403)

    # Treat missing is_active as True
    whiteboards = list(db.find('whiteboards', {'group_id': group_id_obj, 'is_active': {'$ne': False}}))
    for wb in whiteboards:
        wb['id'] = str(wb['_id'])
    return success_response({'whiteboards': [serialize_document(wb) for wb in whiteboards]}, 'Whiteboards retrieved', 200)


@groups_bp.route('/channels', methods=['POST'])
@require_auth
def create_channel_api():
    """Create a new channel (category)"""
    data = request.get_json()
    if not data or 'name' not in data:
        return error_response('Channel name is required', 400)

    name = data.get('name', '').strip()
    description = data.get('description', '').strip()
    is_private = data.get('is_private', False)

    if len(name) < 2:
        return error_response('Channel name must be at least 2 characters', 400)

    db = Database()
    existing = db.find_one('channels', {'name': name})
    if existing:
        return error_response('Channel with this name already exists', 400)

    channel_doc = Channel.create_channel_doc(name, description, is_private)
    created_id = db.insert_one('channels', channel_doc)
    if not created_id:
        return error_response('Failed to create channel', 500)

    channel_doc = db.find_one('channels', {'_id': channel_doc['_id']})
    channel_doc['id'] = str(channel_doc['_id'])
    return success_response(serialize_document(channel_doc), 'Channel created successfully', 201)

@groups_bp.route('/<group_id>/requests', methods=['GET'])
@require_auth
def get_group_requests(group_id):
    """Get pending join requests for a group"""
    try:
        group_id_obj = ObjectId(group_id)
    except:
        return error_response('Invalid group ID', 400)
    
    db = Database()
    group = db.find_one('groups', {'_id': group_id_obj})
    
    if not group:
        return error_response('Group not found', 404)
    
    # Check if user is moderator
    user_id_obj = ObjectId(g.user_id)
    if user_id_obj not in group.get('moderators', []):
        return error_response('Only moderators can view requests', 403)
        
    pending_ids = group.get('pending_members', [])
    if not pending_ids:
        return success_response([], 'No pending requests', 200)
        
    users = list(db.find('users', {'_id': {'$in': pending_ids}}))
    
    # Remove sensitive data and add 'id' field
    for user in users:
        user['id'] = str(user['_id'])
        del user['password_hash']
        
    return success_response([serialize_document(u) for u in users], 'Requests retrieved successfully', 200)

@groups_bp.route('/<group_id>/requests/<user_id>/approve', methods=['POST'])
@require_auth
def approve_request(group_id, user_id):
    """Approve a join request"""
    try:
        group_id_obj = ObjectId(group_id)
        target_user_id_obj = ObjectId(user_id)
    except:
        return error_response('Invalid ID', 400)
        
    db = Database()
    group = db.find_one('groups', {'_id': group_id_obj})
    
    if not group:
        return error_response('Group not found', 404)
        
    # Check if user is moderator
    user_id_obj = ObjectId(g.user_id)
    if user_id_obj not in group.get('moderators', []):
        return error_response('Only moderators can approve requests', 403)
        
    if target_user_id_obj not in group.get('pending_members', []):
        return error_response('Request not found', 404)
        
    # Add to members, remove from pending
    db.push_to_array('groups', {'_id': group_id_obj}, 'members', target_user_id_obj)
    db.pull_from_array('groups', {'_id': group_id_obj}, 'pending_members', target_user_id_obj)
    db.push_to_array('users', {'_id': target_user_id_obj}, 'groups', group_id_obj)
    
    return success_response(None, 'Request approved', 200)

@groups_bp.route('/<group_id>/requests/<user_id>/reject', methods=['POST'])
@require_auth
def reject_request(group_id, user_id):
    """Reject a join request"""
    try:
        group_id_obj = ObjectId(group_id)
        target_user_id_obj = ObjectId(user_id)
    except:
        return error_response('Invalid ID', 400)
        
    db = Database()
    group = db.find_one('groups', {'_id': group_id_obj})
    
    if not group:
        return error_response('Group not found', 404)
        
    # Check if user is moderator
    user_id_obj = ObjectId(g.user_id)
    if user_id_obj not in group.get('moderators', []):
        return error_response('Only moderators can reject requests', 403)
        
    if target_user_id_obj not in group.get('pending_members', []):
        return error_response('Request not found', 404)
        
    # Remove from pending
    db.pull_from_array('groups', {'_id': group_id_obj}, 'pending_members', target_user_id_obj)
    
    return success_response(None, 'Request rejected', 200)
