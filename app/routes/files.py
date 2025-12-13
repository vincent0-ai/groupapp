from flask import Blueprint, request, g, send_file
from app.utils import (
    success_response, error_response, serialize_document,
    MinioClient
)
from app.services import Database
from app.models import File
from bson import ObjectId
from functools import wraps
import jwt
from flask import current_app
from datetime import datetime
import os
from werkzeug.utils import secure_filename

files_bp = Blueprint('files', __name__, url_prefix='/api/files')

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

ALLOWED_EXTENSIONS = {'pdf', 'txt', 'jpg', 'jpeg', 'png', 'gif', 'docx', 'doc', 'xlsx', 'xls', 'pptx', 'ppt', 'zip'}

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@files_bp.route('', methods=['GET'])
@require_auth
def get_all_files():
    """Get all files accessible by the user"""
    db = Database()
    user_id_obj = ObjectId(g.user_id)
    
    # Get current user info to check admin status
    current_user = db.find_one('users', {'_id': user_id_obj})
    is_admin = current_user.get('is_admin', False) if current_user else False
    
    if is_admin:
        # Admins can see all files
        files = list(db.find('files', {}))
    else:
        # Get user's groups
        user_groups = list(db.find('groups', {'members': user_id_obj}))
        group_ids = [grp['_id'] for grp in user_groups]
        
        # Get files from user's groups or uploaded by user
        files = list(db.find('files', {
            '$or': [
                {'group_id': {'$in': group_ids}},
                {'uploaded_by': user_id_obj}
            ]
        }))
    
    # Add id field and owner info for frontend
    for f in files:
        f['id'] = str(f['_id'])
        # Get uploader info
        uploader_id = f.get('uploaded_by')
        if uploader_id:
            uploader = db.find_one('users', {'_id': ObjectId(uploader_id) if isinstance(uploader_id, str) else uploader_id})
            if uploader:
                f['uploader_name'] = uploader.get('full_name') or uploader.get('username', 'Unknown')
                f['uploader_username'] = uploader.get('username', '')
            else:
                f['uploader_name'] = 'Unknown'
                f['uploader_username'] = ''
        else:
            f['uploader_name'] = 'Unknown'
            f['uploader_username'] = ''
        
        # Check if current user can delete this file (owner or admin)
        f['can_delete'] = str(f.get('uploaded_by', '')) == g.user_id or is_admin
    
    return success_response({'files': [serialize_document(f) for f in files]}, 'Files retrieved successfully', 200)

@files_bp.route('/upload', methods=['POST'])
@require_auth
def upload_file():
    """Upload a file to a group or channel"""
    if 'file' not in request.files:
        return error_response('No file provided', 400)
    
    file = request.files['file']
    
    if file.filename == '':
        return error_response('No file selected', 400)
    
    if not allowed_file(file.filename):
        return error_response('File type not allowed', 400)
    
    group_id = request.form.get('group_id')
    channel_id = request.form.get('channel_id')
    
    if not group_id:
        return error_response('Group ID is required', 400)
    
    try:
        group_id_obj = ObjectId(group_id)
        channel_id_obj = ObjectId(channel_id) if channel_id else None
    except:
        return error_response('Invalid group or channel ID', 400)
    
    db = Database()
    
    # Verify user is in group
    group = db.find_one('groups', {'_id': group_id_obj})
    if not group:
        return error_response('Group not found', 404)
    
    user_id_obj = ObjectId(g.user_id)
    if user_id_obj not in group['members']:
        return error_response('You are not a member of this group', 403)
    
    # Save file temporarily
    filename = secure_filename(file.filename)
    temp_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
    
    # Create upload folder if it doesn't exist
    os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    file.save(temp_path)
    
    # Get file size before any operations
    file_size = os.path.getsize(temp_path)
    
    # Upload to MinIO
    minio_path = f"groups/{group_id}/{filename}"
    minio_client = MinioClient()
    
    content_type = file.content_type or 'application/octet-stream'
    success = minio_client.upload_file(temp_path, minio_path, content_type)
    
    # Clean up temporary file
    os.remove(temp_path)
    
    if not success:
        return error_response('Failed to upload file', 500)
    
    # Create file document
    file_doc = File.create_file_doc(
        filename, file.filename.rsplit('.', 1)[1].lower(), g.user_id,
        group_id, channel_id, minio_path=minio_path
    )
    file_doc['file_size'] = file_size
    file_doc['mime_type'] = content_type
    
    file_id = db.insert_one('files', file_doc)
    
    if not file_id:
        return error_response('Failed to save file metadata', 500)
    
    # Award points
    try:
        points = current_app.config['POINTS_CONFIG']['UPLOAD_FILE']
        db.increment('users', {'_id': ObjectId(g.user_id)}, 'points', points)
    except Exception as e:
        print(f"Error awarding points: {e}")
    
    file_doc['_id'] = file_id
    return success_response(serialize_document(file_doc), 'File uploaded successfully', 201)

@files_bp.route('/<file_id>', methods=['GET'])
@require_auth
def download_file(file_id):
    """Download a file"""
    try:
        file_id_obj = ObjectId(file_id)
    except:
        return error_response('Invalid file ID', 400)
    
    db = Database()
    file_doc = db.find_one('files', {'_id': file_id_obj})
    
    if not file_doc:
        return error_response('File not found', 404)
    
    # Check if user has access
    user_id_obj = ObjectId(g.user_id)
    group = db.find_one('groups', {'_id': file_doc['group_id']})
    
    if user_id_obj not in group['members']:
        if not file_doc.get('is_public'):
            return error_response('Access denied', 403)
    
    # Get presigned URL from MinIO
    minio_client = MinioClient()
    presigned_url = minio_client.get_presigned_url(file_doc['minio_path'])
    
    if not presigned_url:
        return error_response('Failed to generate download URL', 500)
    
    # Increment download counter
    db.increment('files', {'_id': file_id_obj}, 'downloads')
    
    return success_response({'download_url': presigned_url}, 'Download URL generated successfully', 200)

@files_bp.route('/<file_id>', methods=['DELETE'])
@require_auth
def delete_file(file_id):
    """Delete a file"""
    try:
        file_id_obj = ObjectId(file_id)
    except:
        return error_response('Invalid file ID', 400)
    
    db = Database()
    file_doc = db.find_one('files', {'_id': file_id_obj})
    
    if not file_doc:
        return error_response('File not found', 404)
    
    user_id_obj = ObjectId(g.user_id)
    current_user = db.find_one('users', {'_id': user_id_obj})
    is_admin = current_user.get('is_admin', False) if current_user else False
    
    # Check if user is uploader, admin, or group moderator
    if str(file_doc['uploaded_by']) != g.user_id and not is_admin:
        group = db.find_one('groups', {'_id': file_doc['group_id']})
        if not group or user_id_obj not in group.get('moderators', []):
            return error_response('You can only delete your own files or must be an admin', 403)
    
    # Delete from MinIO
    minio_client = MinioClient()
    minio_client.delete_file(file_doc['minio_path'])
    
    # Delete from database
    db.delete_one('files', {'_id': file_id_obj})
    
    return success_response(None, 'File deleted successfully', 200)

@files_bp.route('/group/<group_id>', methods=['GET'])
@require_auth
def get_group_files(group_id):
    """Get all files in a group"""
    try:
        group_id_obj = ObjectId(group_id)
    except:
        return error_response('Invalid group ID', 400)
    
    db = Database()
    group = db.find_one('groups', {'_id': group_id_obj})
    
    if not group:
        return error_response('Group not found', 404)
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    skip = (page - 1) * per_page
    files = db.find('files', {'group_id': group_id_obj}, skip=skip, limit=per_page)
    
    total = db.count('files', {'group_id': group_id_obj})
    
    return success_response({
        'files': [serialize_document(f) for f in files],
        'total': total,
        'page': page,
        'per_page': per_page
    }, 'Files retrieved successfully', 200)

@files_bp.route('/<file_id>/share', methods=['POST'])
@require_auth
def make_file_public(file_id):
    """Make a file public"""
    try:
        file_id_obj = ObjectId(file_id)
    except:
        return error_response('Invalid file ID', 400)
    
    db = Database()
    file_doc = db.find_one('files', {'_id': file_id_obj})
    
    if not file_doc:
        return error_response('File not found', 404)
    
    # Check if user is uploader
    if str(file_doc['uploaded_by']) != g.user_id:
        return error_response('You can only share your own files', 403)
    
    db.update_one('files', {'_id': file_id_obj}, {'is_public': True})
    
    updated_file = db.find_one('files', {'_id': file_id_obj})
    return success_response(serialize_document(updated_file), 'File shared successfully', 200)
