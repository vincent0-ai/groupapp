from flask import Blueprint, request, g
from app.utils import success_response, error_response, serialize_document
from app.services import Database
from app.models import Whiteboard
from bson import ObjectId
from functools import wraps
import jwt
from flask import current_app
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from app.utils import MinioClient
from app.models import File

ALLOWED_AUDIO = {'wav', 'mp3', 'ogg', 'webm'}

whiteboards_bp = Blueprint('whiteboards', __name__, url_prefix='/api/whiteboards')

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return error_response('Missing or invalid authorization', 401)
        token = auth_header.split(' ')[1]
        try:
            payload = jwt.decode(token, current_app.config['JWT_SECRET_KEY'], algorithms=[current_app.config['JWT_ALGORITHM']])
            g.user_id = payload['user_id']
        except jwt.ExpiredSignatureError:
            return error_response('Token expired', 401)
        except jwt.InvalidTokenError:
            return error_response('Invalid token', 401)
        return f(*args, **kwargs)
    return decorated


@whiteboards_bp.route('/mine', methods=['GET'])
@require_auth
def get_my_whiteboards():
    """Get active whiteboards created by the current user"""
    db = Database()
    try:
        user_id_obj = ObjectId(g.user_id)
        # Find active whiteboards created by user (treat missing is_active as True)
        whiteboards = list(db.find('whiteboards', {
            'created_by': user_id_obj,
            'is_active': {'$ne': False}
        }, sort=[('created_at', -1)]))
        
        # Enrich with group name
        for wb in whiteboards:
            wb['id'] = str(wb['_id'])
            if wb.get('group_id'):
                group = db.find_one('groups', {'_id': wb['group_id']})
                wb['group_name'] = group.get('name', 'Unknown Group') if group else 'Unknown Group'
            else:
                wb['group_name'] = 'No Group'
                
        return success_response({'whiteboards': [serialize_document(wb) for wb in whiteboards]}, 'Whiteboards retrieved', 200)
    except Exception as e:
        print(f"Error fetching my whiteboards: {e}")
        return error_response('Failed to fetch whiteboards', 500)


@whiteboards_bp.route('/<wb_id>', methods=['DELETE'])
@require_auth
def end_whiteboard(wb_id):
    """End (soft delete) a whiteboard session"""
    try:
        wb_obj_id = ObjectId(wb_id)
    except:
        return error_response('Invalid whiteboard id', 400)
        
    db = Database()
    wb = db.find_one('whiteboards', {'_id': wb_obj_id})
    if not wb:
        return error_response('Whiteboard not found', 404)
        
    # Only creator can end session
    if str(wb.get('created_by')) != g.user_id:
        return error_response('Only the creator can end this session', 403)
        
    # Soft delete by setting is_active to False
    db.update_one('whiteboards', {'_id': wb_obj_id}, {'is_active': False, 'ended_at': datetime.utcnow()})
    
    # Emit socket event to notify all users in the session
    try:
        from app import socketio
        room = f'whiteboard:{wb_id}'
        socketio.emit('session_ended', {'session_id': wb_id}, room=room)
    except Exception as e:
        print(f"Error emitting session_ended event: {e}")
    
    return success_response(None, 'Session ended successfully', 200)


@whiteboards_bp.route('/<wb_id>', methods=['GET'])
@require_auth
def get_whiteboard(wb_id):
    try:
        wb_obj_id = ObjectId(wb_id)
    except:
        return error_response('Invalid whiteboard id', 400)
    db = Database()
    wb = db.find_one('whiteboards', {'_id': wb_obj_id})
    if not wb:
        return error_response('Whiteboard not found', 404)
        
    if not wb.get('is_active', True):
        return error_response('This session has ended', 410)

    # Only group members or public groups allowed
    # Resolve participants to include public profile info
    participants = []
    for pid in wb.get('participants', []):
        u = db.find_one('users', {'_id': pid})
        if u:
            # remove sensitive data
            u.pop('password_hash', None)
            u.pop('preferences', None)
            u['id'] = str(u['_id'])
            participants.append({'id': u['id'], 'full_name': u.get('full_name', ''), 'avatar_url': u.get('avatar_url', ''), 'username': u.get('username', '')})
    wb['participants'] = participants

    # Populate audio files associated (if any)
    audio_files = list(db.find('files', {'group_id': wb.get('group_id'), 'whiteboard_id': wb.get('_id')})) if wb.get('group_id') else []
    for f in audio_files:
        f['id'] = str(f['_id'])
    wb['audio_files'] = [serialize_document(f) for f in audio_files]

    return success_response(serialize_document(wb), 'Whiteboard retrieved', 200)


@whiteboards_bp.route('/<wb_id>/permissions', methods=['POST'])
@require_auth
def update_permissions(wb_id):
    try:
        wb_obj_id = ObjectId(wb_id)
    except:
        return error_response('Invalid whiteboard id', 400)
    data = request.get_json() or {}
    db = Database()
    wb = db.find_one('whiteboards', {'_id': wb_obj_id})
    if not wb:
        return error_response('Whiteboard not found', 404)
    # Only creator can update permissions (owner/moderator)
    creator_id = str(wb.get('created_by'))
    if creator_id != g.user_id:
        return error_response('Only whiteboard creator can update permissions', 403)
    can_draw = data.get('can_draw')
    can_speak = data.get('can_speak')
    update = {}
    if can_draw is not None:
        # Expect list of user IDs
        update['can_draw'] = [ObjectId(uid) for uid in can_draw]
    if can_speak is not None:
        update['can_speak'] = [ObjectId(uid) for uid in can_speak]
    if update:
        db.update_one('whiteboards', {'_id': wb_obj_id}, update)
    wb = db.find_one('whiteboards', {'_id': wb_obj_id})
    return success_response(serialize_document(wb), 'Whiteboard permissions updated', 200)


@whiteboards_bp.route('/<wb_id>/upload_audio', methods=['POST'])
@require_auth
def upload_audio(wb_id):
    try:
        wb_obj_id = ObjectId(wb_id)
    except:
        return error_response('Invalid whiteboard id', 400)
    if 'file' not in request.files:
        return error_response('No file provided', 400)
    f = request.files['file']
    if f.filename == '':
        return error_response('No file selected', 400)
    ext = f.filename.rsplit('.', 1)[1].lower() if '.' in f.filename else ''
    if ext not in ALLOWED_AUDIO:
        return error_response('Audio format not supported', 400)
    db = Database()
    wb = db.find_one('whiteboards', {'_id': wb_obj_id})
    if not wb:
        return error_response('Whiteboard not found', 404)
    # Verify user is in group
    group_id = wb.get('group_id')
    group = db.find_one('groups', {'_id': group_id}) if group_id else None
    if group and ObjectId(g.user_id) not in group.get('members', []):
        return error_response('You are not a member of this group', 403)
    filename = secure_filename(f.filename)
    temp_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
    os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)
    f.save(temp_path)
    minio_path = f"whiteboards/{wb_id}/audio/{filename}"
    minio_client = MinioClient()
    success = minio_client.upload_file(temp_path, minio_path, content_type=f.content_type or 'audio/webm')
    os.remove(temp_path)
    if not success:
        return error_response('Failed to upload audio', 500)
    # Create file doc
    file_doc = File.create_file_doc(filename, ext, g.user_id, str(group_id) if group_id else None, minio_path=minio_path)
    file_id = db.insert_one('files', file_doc)
    if not file_id:
        return error_response('Failed to save audio metadata', 500)
    # Link to whiteboard
    db.update_one('files', {'_id': ObjectId(file_id)}, {'whiteboard_id': wb_obj_id})
    db.push_to_array('whiteboards', {'_id': wb_obj_id}, 'audio_files', ObjectId(file_id))
    return success_response({'file_id': str(file_id)}, 'Audio uploaded', 201)


from app.services.livekit_service import LiveKitService
from livekit.api import VideoGrant
import asyncio

@whiteboards_bp.route('/<wb_id>/livekit-token', methods=['POST'])
@require_auth
async def get_livekit_token(wb_id):
    """Generate a LiveKit access token for a user joining a whiteboard."""
    try:
        wb_obj_id = ObjectId(wb_id)
    except Exception:
        return error_response('Invalid whiteboard ID format', 400)

    db = Database()
    wb = db.find_one('whiteboards', {'_id': wb_obj_id})
    if not wb:
        return error_response('Whiteboard session not found', 404)

    if not wb.get('is_active', True):
        return error_response('This session has already ended', 410)

    user_id = g.user_id
    user = db.find_one('users', {'_id': ObjectId(user_id)})
    if not user:
        return error_response('User not found', 404)
        
    # Enforce participant limit
    try:
        livekit_service = LiveKitService()
        room_name = f'whiteboard:{wb_id}'
        participants = await livekit_service.lkapi.room.list_participants(room=room_name)
        max_participants = current_app.config['MAX_PARTICIPANTS_PER_ROOM']
        
        # Check if the user is already in the room before checking the limit
        is_already_in_room = any(p.identity == user_id for p in participants)
        
        if not is_already_in_room and len(participants) >= max_participants:
            return error_response(f'This session is full (max {max_participants} participants).', 429)

    except Exception as e:
        # If the room doesn't exist on LiveKit server, list_participants will fail.
        # This is fine, it just means the room is not full.
        print(f"Could not check participant list (room may not exist yet): {e}")


    # Determine permissions from the whiteboard document
    is_creator = str(wb.get('created_by')) == user_id
    can_speak = is_creator or user_id in [str(uid) for uid in wb.get('can_speak', [])]
    can_share_screen = is_creator or user_id in [str(uid) for uid in wb.get('can_share_screen', [])]

    # Define LiveKit permissions based on app logic
    # can_publish allows audio/video, can_publish_data for things like chat
    lk_permissions = VideoGrant(
        room_join=True,
        room=f'whiteboard:{wb_id}',
        can_publish=can_speak or can_share_screen,
        can_publish_data=True,
        can_subscribe=True # Always allow users to subscribe to others
    )

    try:
        # Re-instance service in case of previous error
        livekit_service = LiveKitService()
        token = livekit_service.create_access_token(
            user_id=user_id,
            user_name=user.get('full_name', 'Anonymous'),
            room_name=f'whiteboard:{wb_id}',
            permissions=lk_permissions
        )
        return success_response({'token': token, 'url': current_app.config['LIVEKIT_URL']}, 'LiveKit token generated', 200)
    except ValueError as e:
        # This catches the API key/secret not being set
        print(f"LiveKit config error: {e}")
        return error_response('Media server is not configured', 503)
    except Exception as e:
        print(f"Error generating LiveKit token: {e}")
        return error_response('Failed to connect to media server', 500)

