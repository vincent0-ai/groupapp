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
    
    # Create a message without channel_id
    message_doc = Message.create_message_doc(
        content, g.user_id, None, group_id, attachments, reply_to
    )
    
    message_id = db.insert_one('messages', message_doc)
    
    if not message_id:
        return error_response('Failed to send message', 500)
    
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
    
    # Check if user is message author or group moderator
    user_id_obj = ObjectId(g.user_id)
    if str(message['user_id']) != g.user_id:
        group = db.find_one('groups', {'_id': message['group_id']})
        if user_id_obj not in group['moderators']:
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
