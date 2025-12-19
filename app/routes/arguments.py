from flask import Blueprint, request, g, current_app
from app.utils import success_response, error_response, serialize_document
from app.services import Database
from app.models import Argument
from bson import ObjectId
from functools import wraps
import jwt

arguments_bp = Blueprint('arguments', __name__, url_prefix='/api/arguments')

# Lightweight auth decorator (copy of messages.require_auth pattern to avoid import cycles)
def require_auth(f):
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


@arguments_bp.route('', methods=['POST'])
@require_auth
def create_argument():
    data = request.get_json()
    required = ['node_type', 'content', 'group_id']
    if not data or not all(k in data for k in required):
        return error_response('Missing required fields', 400)

    node_type = data.get('node_type')
    content = data.get('content', '').strip()
    group_id = data.get('group_id')
    message_id = data.get('message_id')  # optional
    parent_id = data.get('parent_id')  # optional

    if not content:
        return error_response('Content cannot be empty', 400)

    if node_type not in Argument.VALID_TYPES:
        return error_response('Invalid node_type', 400)

    # Validation: evidence must reference a claim; counter must reference a parent
    db = Database()
    try:
        group_oid = ObjectId(group_id)
    except Exception:
        return error_response('Invalid group ID', 400)

    group = db.find_one('groups', {'_id': group_oid})
    if not group:
        return error_response('Group not found', 404)

    user_oid = ObjectId(g.user_id)
    # Ensure user is member of group
    if user_oid not in group.get('members', []):
        return error_response('You are not a member of this group', 403)

    # Validate parent relations
    if parent_id:
        try:
            parent_oid = ObjectId(parent_id)
        except Exception:
            return error_response('Invalid parent ID', 400)
        parent_doc = db.find_one('arguments', {'_id': parent_oid})
        if not parent_doc:
            return error_response('Parent argument not found', 404)
    else:
        parent_doc = None

    if node_type == 'evidence' and not parent_doc:
        return error_response('Evidence must reference a claim (parent)', 400)
    if node_type == 'evidence' and parent_doc and parent_doc.get('node_type') != 'claim':
        return error_response('Evidence must reference a claim node', 400)
    if node_type == 'counter' and not parent_doc:
        return error_response('Counter must reference a target node (parent)', 400)

    # If message_id provided, validate it
    if message_id:
        try:
            message_oid = ObjectId(message_id)
        except Exception:
            return error_response('Invalid message ID', 400)
        message = db.find_one('messages', {'_id': message_oid})
        if not message:
            return error_response('Message not found', 404)
    else:
        message_oid = None

    try:
        arg_doc = Argument.create_argument_doc(node_type, content, g.user_id, group_id, message_id, parent_id)
    except ValueError as e:
        return error_response(str(e), 400)

    inserted_id = db.insert_one('arguments', arg_doc)
    if not inserted_id:
        return error_response('Failed to create argument', 500)

    arg_doc['_id'] = inserted_id

    # broadcast to group room
    try:
        current_app.socketio.emit('new_argument', {
            'room': str(group_id),
            'argument': serialize_document(arg_doc)
        }, room=str(group_id))
    except Exception:
        pass

    return success_response(serialize_document(arg_doc), 'Argument created successfully', 201)


@arguments_bp.route('', methods=['GET'])
@require_auth
def list_arguments():
    # Supports filtering by group_id, message_id, parent_id
    group_id = request.args.get('group_id')
    message_id = request.args.get('message_id')
    parent_id = request.args.get('parent_id')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))

    query = {}
    try:
        if group_id:
            query['group_id'] = ObjectId(group_id)
        if message_id:
            query['message_id'] = ObjectId(message_id)
        if parent_id:
            query['parent_id'] = ObjectId(parent_id)
    except Exception:
        return error_response('Invalid IDs in query', 400)

    db = Database()
    skip = (page - 1) * per_page
    results = db.find('arguments', query, skip=skip, limit=per_page, sort=('created_at', -1))

    return success_response({
        'arguments': [serialize_document(r) for r in results],
        'page': page,
        'per_page': per_page,
        'total': db.count('arguments', query)
    }, 'Arguments retrieved', 200)


@arguments_bp.route('/<arg_id>/children', methods=['GET'])
@require_auth
def get_children(arg_id):
    try:
        arg_oid = ObjectId(arg_id)
    except Exception:
        return error_response('Invalid argument ID', 400)

    db = Database()
    children = db.find('arguments', {'parent_id': arg_oid}, sort=('created_at', -1))
    return success_response({'children': [serialize_document(c) for c in children]}, 'Children retrieved', 200)


@arguments_bp.route('/<arg_id>', methods=['PUT'])
@require_auth
def update_argument(arg_id):
    data = request.get_json() or {}
    if 'content' not in data:
        return error_response('Content is required', 400)
    try:
        arg_oid = ObjectId(arg_id)
    except Exception:
        return error_response('Invalid argument ID', 400)

    db = Database()
    arg = db.find_one('arguments', {'_id': arg_oid})
    if not arg:
        return error_response('Argument not found', 404)

    # Only author can edit
    if str(arg.get('author_id')) != g.user_id:
        return error_response('You can only edit your own argument', 403)

    content = data.get('content', '').strip()
    if not content:
        return error_response('Content cannot be empty', 400)

    db.update_one('arguments', {'_id': arg_oid}, {'content': content, 'updated_at': __import__('datetime').datetime.utcnow()})
    updated = db.find_one('arguments', {'_id': arg_oid})
    return success_response(serialize_document(updated), 'Argument updated', 200)


@arguments_bp.route('/<arg_id>', methods=['DELETE'])
@require_auth
def delete_argument(arg_id):
    try:
        arg_oid = ObjectId(arg_id)
    except Exception:
        return error_response('Invalid argument ID', 400)

    db = Database()
    arg = db.find_one('arguments', {'_id': arg_oid})
    if not arg:
        return error_response('Argument not found', 404)

    # Allow author or group owner/moderator
    user_oid = ObjectId(g.user_id)
    if str(arg.get('author_id')) != g.user_id:
        group = db.find_one('groups', {'_id': arg.get('group_id')})
        if not group:
            return error_response('Group not found', 404)
        is_owner = str(group.get('owner_id', '')) == g.user_id
        is_mod = user_oid in group.get('moderators', [])
        if not is_owner and not is_mod:
            return error_response('You can only delete your own argument', 403)

    # Delete argument and optionally its child nodes (cascade delete)
    db.delete_one('arguments', {'_id': arg_oid})
    db.delete_many('arguments', {'parent_id': arg_oid})

    return success_response(None, 'Argument deleted', 200)
