from flask import Blueprint, request, g
from app.utils import success_response, error_response, serialize_document
from app.services import Database
from app.models import Message
from bson import ObjectId
from functools import wraps
import jwt
from flask import current_app
from datetime import datetime

messages_bp = Blueprint('messages', __name__, url_prefix='/api/messages')

def _attach_user_first_name(db: Database, msg: dict):
    """Attach a `user_first_name` field to a message dict (best-effort)."""
    try:
        uid = msg.get('user_id')
        if not uid:
            msg['user_first_name'] = 'Unknown'
            return
        user = db.find_one('users', {'_id': uid})
        if not user:
            msg['user_first_name'] = f'User {str(uid)[-4:]}'
            return
        full_name = (user.get('full_name') or '').strip()
        if full_name:
            msg['user_first_name'] = full_name.split()[0]
        else:
            msg['user_first_name'] = user.get('username') or f'User {str(uid)[-4:]}'
    except Exception:
        msg['user_first_name'] = f'User {str(msg.get("user_id"))[-4:]}'

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

@messages_bp.route('/group/<group_id>', methods=['GET'])
@require_auth
def get_group_messages(group_id):
    """Get messages from a group (single chat stream)"""
    try:
        group_id_obj = ObjectId(group_id)
    except:
        return error_response('Invalid group ID', 400)
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    db = Database()
    
    # Get group
    group = db.find_one('groups', {'_id': group_id_obj})
    if not group:
        return error_response('Group not found', 404)
    
    # Verify membership (public groups may be readable by everyone)
    user_id_obj = ObjectId(g.user_id)
    if group.get('is_private') and user_id_obj not in group.get('members', []):
        return error_response('Access denied', 403)
    
    # Get messages with pagination
    skip = (page - 1) * per_page
    messages = db.find(
        'messages',
        {'group_id': group_id_obj},
        skip=skip,
        limit=per_page,
        sort=('created_at', -1)
    )
    
    # Reverse to get chronological order
    messages = list(reversed(messages))
    # Attach the sender's first name (from user's full_name) to each message
    try:
        user_ids = list({m.get('user_id') for m in messages if m.get('user_id')})
        users = db.find('users', {'_id': {'$in': user_ids}}) if user_ids else []
        user_map = {u['_id']: u for u in users}

        for m in messages:
            uid = m.get('user_id')
            u = user_map.get(uid)
            if u:
                full_name = (u.get('full_name') or '').strip()
                if full_name:
                    first_name = full_name.split()[0]
                else:
                    first_name = u.get('username') or f'User {str(uid)[-4:]}'
            else:
                first_name = f'User {str(uid)[-4:]}' if uid else 'Unknown'

            m['user_first_name'] = first_name
    except Exception:
        # Best-effort: if anything goes wrong, continue without failing
        pass
    
    total = db.count('messages', {'group_id': group_id_obj})
    
    return success_response({
        'messages': [serialize_document(m) for m in messages],
        'total': total,
        'page': page,
        'per_page': per_page
    }, 'Messages retrieved successfully', 200)

@messages_bp.route('/group/<group_id>', methods=['DELETE'])
@require_auth
def clear_group_messages(group_id):
    """Clear all messages in a group (Owner only)"""
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
        return error_response('Only group owner can clear chat', 403)
    
    result = db.delete_many('messages', {'group_id': group_id_obj})
    
    return success_response({'deleted_count': result}, 'Chat cleared successfully', 200)

@messages_bp.route('', methods=['POST'])
@require_auth
def send_message():
    """Send a message to a group"""
    data = request.get_json()
    
    if not data or 'content' not in data or 'group_id' not in data:
        return error_response('Missing required fields', 400)
    
    content = data.get('content', '').strip()
    group_id = data.get('group_id')
    attachments = data.get('attachments', [])
    reply_to = data.get('reply_to')
    is_announcement = data.get('is_announcement', False)
    
    if not content:
        return error_response('Message content cannot be empty', 400)
    
    try:
        group_id_obj = ObjectId(group_id)
    except:
        return error_response('Invalid group ID', 400)
    
    db = Database()
    
    # Verify user is in group
    group = db.find_one('groups', {'_id': group_id_obj})
    if not group:
        return error_response('Group not found', 404)
    
    user_id_obj = ObjectId(g.user_id)
    if user_id_obj not in group['members']:
        return error_response('You are not a member of this group', 403)
    
    # Only moderators and owners can post announcements
    if is_announcement:
        is_owner = str(group.get('owner_id', '')) == g.user_id
        is_mod = user_id_obj in group.get('moderators', [])
        if not is_owner and not is_mod:
            return error_response('Only moderators and owners can post announcements', 403)
    
    # Create a message without channel_id
    message_doc = Message.create_message_doc(
        content, g.user_id, None, group_id, attachments, reply_to
    )
    
    # Add announcement flag if applicable
    if is_announcement:
        message_doc['is_announcement'] = True
    
    message_id = db.insert_one('messages', message_doc)
    
    if not message_id:
        return error_response('Failed to send message', 500)
    
    # Award points
    try:
        points = current_app.config['POINTS_CONFIG']['SEND_MESSAGE']
        db.increment('users', {'_id': ObjectId(g.user_id)}, 'points', points)
    except Exception as e:
        print(f"Error awarding points: {e}")
    
    message_doc['_id'] = message_id
    # Add sender's first name for immediate response and broadcast
    try:
        user = db.find_one('users', {'_id': ObjectId(g.user_id)})
        full_name = (user.get('full_name') or '').strip() if user else ''
        if full_name:
            message_doc['user_first_name'] = full_name.split()[0]
        else:
            message_doc['user_first_name'] = (user.get('username') if user else f'User {str(g.user_id)[-4:]}')
    except Exception:
        message_doc['user_first_name'] = f'User {str(g.user_id)[-4:]}'

    # Broadcast to room so connected clients receive the update in real-time
    try:
        current_app.socketio.emit('new_message', {
            'room': str(group_id),
            'message': serialize_document(message_doc)
        }, room=str(group_id))
    except Exception:
        # If socketio not available for any reason, we continue without failing
        pass

    return success_response(serialize_document(message_doc), 'Message sent successfully', 201)

@messages_bp.route('/<message_id>', methods=['PUT'])
@require_auth
def edit_message(message_id):
    """Edit a message"""
    try:
        message_id_obj = ObjectId(message_id)
    except:
        return error_response('Invalid message ID', 400)
    
    data = request.get_json()
    
    if not data or 'content' not in data:
        return error_response('Message content is required', 400)
    
    db = Database()
    message = db.find_one('messages', {'_id': message_id_obj})
    
    if not message:
        return error_response('Message not found', 404)
    
    # Check if user is message author
    if str(message['user_id']) != g.user_id:
        return error_response('You can only edit your own messages', 403)
    
    content = data.get('content', '').strip()
    
    if not content:
        return error_response('Message content cannot be empty', 400)
    
    db.update_one('messages', {'_id': message_id_obj}, {
        'content': content,
        'is_edited': True,
        'updated_at': datetime.utcnow()
    })
    
    updated_message = db.find_one('messages', {'_id': message_id_obj})
    # Attach display name
    _attach_user_first_name(db, updated_message)
    return success_response(serialize_document(updated_message), 'Message updated successfully', 200)

@messages_bp.route('/<message_id>', methods=['DELETE'])
@require_auth
def delete_message(message_id):
    """Delete a message"""
    try:
        message_id_obj = ObjectId(message_id)
    except:
        return error_response('Invalid message ID', 400)
    
    db = Database()
    message = db.find_one('messages', {'_id': message_id_obj})
    
    if not message:
        return error_response('Message not found', 404)
    
    # Check if user is message author, group owner, or group moderator
    user_id_obj = ObjectId(g.user_id)
    if str(message['user_id']) != g.user_id:
        group = db.find_one('groups', {'_id': message['group_id']})
        is_owner = str(group.get('owner_id', '')) == g.user_id
        is_mod = user_id_obj in group.get('moderators', [])
        if not is_owner and not is_mod:
            return error_response('You can only delete your own messages', 403)
    
    db.delete_one('messages', {'_id': message_id_obj})
    return success_response(None, 'Message deleted successfully', 200)

@messages_bp.route('/<message_id>/react', methods=['POST'])
@require_auth
def react_to_message(message_id):
    """Add a reaction to a message"""
    try:
        message_id_obj = ObjectId(message_id)
    except:
        return error_response('Invalid message ID', 400)
    
    data = request.get_json()
    
    if not data or 'emoji' not in data:
        return error_response('Emoji is required', 400)
    
    emoji = data.get('emoji')
    
    db = Database()
    message = db.find_one('messages', {'_id': message_id_obj})
    
    if not message:
        return error_response('Message not found', 404)
    
    # Update reaction
    reactions = message.get('reactions', {})
    if emoji not in reactions:
        reactions[emoji] = []
    
    user_id = g.user_id
    if user_id not in reactions[emoji]:
        reactions[emoji].append(user_id)
    
    db.update_one('messages', {'_id': message_id_obj}, {'reactions': reactions})
    
    updated_message = db.find_one('messages', {'_id': message_id_obj})
    # Attach display name
    _attach_user_first_name(db, updated_message)
    return success_response(serialize_document(updated_message), 'Reaction added successfully', 200)


@messages_bp.route('/<message_id>/unreact', methods=['POST'])
@require_auth
def unreact_to_message(message_id):
    """Remove a reaction from a message"""
    try:
        message_id_obj = ObjectId(message_id)
    except:
        return error_response('Invalid message ID', 400)
    
    data = request.get_json()
    
    if not data or 'emoji' not in data:
        return error_response('Emoji is required', 400)
    
    emoji = data.get('emoji')
    
    db = Database()
    message = db.find_one('messages', {'_id': message_id_obj})
    
    if not message:
        return error_response('Message not found', 404)
    
    # Remove reaction
    reactions = message.get('reactions', {})
    user_id = g.user_id
    
    if emoji in reactions and user_id in reactions[emoji]:
        reactions[emoji].remove(user_id)
        # Clean up empty reaction lists
        if len(reactions[emoji]) == 0:
            del reactions[emoji]
    
    db.update_one('messages', {'_id': message_id_obj}, {'reactions': reactions})
    
    updated_message = db.find_one('messages', {'_id': message_id_obj})
    _attach_user_first_name(db, updated_message)
    return success_response(serialize_document(updated_message), 'Reaction removed successfully', 200)


@messages_bp.route('/<message_id>/pin', methods=['POST'])
@require_auth
def pin_message(message_id):
    """Pin a message"""
    try:
        message_id_obj = ObjectId(message_id)
    except:
        return error_response('Invalid message ID', 400)
    
    db = Database()
    message = db.find_one('messages', {'_id': message_id_obj})
    
    if not message:
        return error_response('Message not found', 404)
    
    # Check if user is group moderator
    group = db.find_one('groups', {'_id': message['group_id']})
    user_id_obj = ObjectId(g.user_id)
    
    if user_id_obj not in group['moderators']:
        return error_response('Only group moderators can pin messages', 403)
    
    db.update_one('messages', {'_id': message_id_obj}, {'is_pinned': True})
    
    updated_message = db.find_one('messages', {'_id': message_id_obj})
    # Attach display name
    _attach_user_first_name(db, updated_message)
    return success_response(serialize_document(updated_message), 'Message pinned successfully', 200)

@messages_bp.route('/<message_id>/unpin', methods=['POST'])
@require_auth
def unpin_message(message_id):
    """Unpin a message"""
    try:
        message_id_obj = ObjectId(message_id)
    except:
        return error_response('Invalid message ID', 400)
    
    db = Database()
    message = db.find_one('messages', {'_id': message_id_obj})
    
    if not message:
        return error_response('Message not found', 404)
    
    # Check if user is group moderator
    group = db.find_one('groups', {'_id': message['group_id']})
    user_id_obj = ObjectId(g.user_id)
    
    if user_id_obj not in group['moderators']:
        return error_response('Only group moderators can unpin messages', 403)
    
    db.update_one('messages', {'_id': message_id_obj}, {'is_pinned': False})
    
    updated_message = db.find_one('messages', {'_id': message_id_obj})
    # Attach display name
    _attach_user_first_name(db, updated_message)
    return success_response(serialize_document(updated_message), 'Message unpinned successfully', 200)

@messages_bp.route('/unread/count', methods=['GET'])
@require_auth
def get_unread_count():
    """Get total unread message count across all groups"""
    db = Database()
    user_id_obj = ObjectId(g.user_id)
    
    # Get user's groups
    groups = list(db.find('groups', {'members': user_id_obj}))
    
    if not groups:
        return success_response({'unread_count': 0, 'groups': []}, 'Unread count retrieved', 200)
    
    # Get or create read receipts for user
    read_receipts = db.find_one('read_receipts', {'user_id': user_id_obj})
    if not read_receipts:
        read_receipts = {'user_id': user_id_obj, 'groups': {}}
    
    total_unread = 0
    group_unreads = []
    
    for group in groups:
        group_id = group['_id']
        group_id_str = str(group_id)
        
        # Get last read timestamp for this group
        last_read = read_receipts.get('groups', {}).get(group_id_str)
        
        # Count messages after last_read
        if last_read:
            unread_count = db.count('messages', {
                'group_id': group_id,
                'created_at': {'$gt': last_read},
                'user_id': {'$ne': user_id_obj}  # Don't count own messages
            })
        else:
            # Never read - count all messages not from this user
            unread_count = db.count('messages', {
                'group_id': group_id,
                'user_id': {'$ne': user_id_obj}
            })
        
        if unread_count > 0:
            total_unread += unread_count
            group_unreads.append({
                'group_id': group_id_str,
                'group_name': group.get('name', 'Unknown'),
                'unread_count': unread_count
            })
    
    return success_response({
        'unread_count': total_unread,
        'groups': group_unreads
    }, 'Unread count retrieved', 200)

@messages_bp.route('/group/<group_id>/read', methods=['POST'])
@require_auth
def mark_group_read(group_id):
    """Mark all messages in a group as read"""
    try:
        group_id_obj = ObjectId(group_id)
    except:
        return error_response('Invalid group ID', 400)
    
    db = Database()
    user_id_obj = ObjectId(g.user_id)
    
    # Verify user is in group
    group = db.find_one('groups', {'_id': group_id_obj})
    if not group:
        return error_response('Group not found', 404)
    
    if user_id_obj not in group.get('members', []):
        return error_response('You are not a member of this group', 403)
    
    # Update or create read receipt
    now = datetime.utcnow()
    
    existing = db.find_one('read_receipts', {'user_id': user_id_obj})
    if existing:
        # Update existing
        db.update_one(
            'read_receipts',
            {'user_id': user_id_obj},
            {f'groups.{group_id}': now, 'updated_at': now}
        )
    else:
        # Create new
        db.insert_one('read_receipts', {
            'user_id': user_id_obj,
            'groups': {group_id: now},
            'created_at': now,
            'updated_at': now
        })
    
    return success_response({'marked_at': now.isoformat()}, 'Messages marked as read', 200)
