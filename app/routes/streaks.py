from flask import Blueprint, request, g, current_app
from app.utils import success_response, error_response, serialize_document
from app.services import Database
from bson import ObjectId
from functools import wraps
import jwt

streaks_bp = Blueprint('streaks', __name__, url_prefix='/api/groups')

# Lightweight auth decorator
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


@streaks_bp.route('/<group_id>/streak', methods=['GET'])
@require_auth
def get_group_streak(group_id):
    try:
        gid = ObjectId(group_id)
    except:
        return error_response('Invalid group id', 400)

    db = Database()
    group = db.find_one('groups', {'_id': gid})
    if not group:
        return error_response('Group not found', 404)

    streak = db.find_one('group_streaks', {'group_id': gid})
    if not streak:
        # return default
        return success_response({'streak_count': 0, 'last_active_day': None, 'threshold': None}, 'Streak retrieved', 200)

    return success_response(serialize_document(streak), 'Streak retrieved', 200)


@streaks_bp.route('/<group_id>/streak/config', methods=['POST'])
@require_auth
def update_streak_config(group_id):
    try:
        gid = ObjectId(group_id)
    except:
        return error_response('Invalid group id', 400)

    db = Database()
    group = db.find_one('groups', {'_id': gid})
    if not group:
        return error_response('Group not found', 404)

    # only owner can configure
    if str(group.get('owner_id')) != g.user_id:
        return error_response('Only group owner can configure streaks', 403)

    data = request.get_json() or {}
    update = {}
    if 'threshold' in data:
        try:
            t = int(data['threshold'])
            if t < 1:
                return error_response('Threshold must be >= 1', 400)
            update['threshold'] = t
        except Exception:
            return error_response('Invalid threshold', 400)
    if 'min_percent' in data:
        try:
            p = float(data['min_percent'])
            if p <= 0 or p > 1:
                return error_response('min_percent must be between 0 and 1', 400)
            update['min_percent'] = p
        except Exception:
            return error_response('Invalid min_percent', 400)

    if not update:
        return error_response('No valid fields to update', 400)

    update['updated_at'] = __import__('datetime').datetime.utcnow()
    # Upsert
    existing = db.find_one('group_streaks', {'group_id': gid})
    if existing:
        db.update_one('group_streaks', {'group_id': gid}, update, raw=False)
    else:
        doc = {
            '_id': ObjectId(),
            'group_id': gid,
            'streak_count': 0,
            'last_active_day': None,
            'threshold': update.get('threshold'),
            'min_percent': update.get('min_percent'),
            'created_at': __import__('datetime').datetime.utcnow(),
            'updated_at': __import__('datetime').datetime.utcnow()
        }
        db.insert_one('group_streaks', doc)

    updated = db.find_one('group_streaks', {'group_id': gid})
    return success_response(serialize_document(updated), 'Streak config updated', 200)
