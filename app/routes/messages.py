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

@messages_bp.route('/channel/<channel_id>', methods=['GET'])
@require_auth
def get_channel_messages(channel_id):
    """Get messages from a channel"""
    try:
        channel_id_obj = ObjectId(channel_id)
    except:
        return error_response('Invalid channel ID', 400)
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    db = Database()
    
    # Get channel
    channel = db.find_one('channels', {'_id': channel_id_obj})
    if not channel:
        return error_response('Channel not found', 404)
    
    # Get messages with pagination
    skip = (page - 1) * per_page
    messages = db.find(
        'messages',
        {'channel_id': channel_id_obj},
        skip=skip,
        limit=per_page,
        sort=('created_at', -1)
    )
    
    # Reverse to get chronological order
    messages = list(reversed(messages))
    
    total = db.count('messages', {'channel_id': channel_id_obj})
    
    return success_response({
        'messages': [serialize_document(m) for m in messages],
        'total': total,
        'page': page,
        'per_page': per_page
    }, 'Messages retrieved successfully', 200)

@messages_bp.route('', methods=['POST'])
@require_auth
def send_message():
    """Send a message to a channel"""
    data = request.get_json()
    
    if not data or 'content' not in data or 'channel_id' not in data:
        return error_response('Missing required fields', 400)
    
    content = data.get('content', '').strip()
    channel_id = data.get('channel_id')
    group_id = data.get('group_id')
    attachments = data.get('attachments', [])
    reply_to = data.get('reply_to')
    
    if not content:
        return error_response('Message content cannot be empty', 400)
    
    try:
        channel_id_obj = ObjectId(channel_id)
        group_id_obj = ObjectId(group_id)
    except:
        return error_response('Invalid channel or group ID', 400)
    
    db = Database()
    
    # Verify user is in group
    group = db.find_one('groups', {'_id': group_id_obj})
    if not group:
        return error_response('Group not found', 404)
    
    user_id_obj = ObjectId(g.user_id)
    if user_id_obj not in group['members']:
        return error_response('You are not a member of this group', 403)
    
    message_doc = Message.create_message_doc(
        content, g.user_id, channel_id, group_id, attachments, reply_to
    )
    
    message_id = db.insert_one('messages', message_doc)
    
    if not message_id:
        return error_response('Failed to send message', 500)
    
    message_doc['_id'] = message_id
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
    return success_response(serialize_document(updated_message), 'Message unpinned successfully', 200)
