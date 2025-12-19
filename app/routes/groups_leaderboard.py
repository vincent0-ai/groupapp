from flask import Blueprint, request
from app.utils import success_response, error_response, serialize_document
from app.services import Database
from bson import ObjectId
from flask import g
from functools import wraps
import jwt
from datetime import datetime, timedelta

leaderboard_bp = Blueprint('groups_leaderboard', __name__, url_prefix='/api/groups')

# Reuse same require_auth from groups or define lightweight
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
                request.app.config['JWT_SECRET_KEY'],
                algorithms=[request.app.config['JWT_ALGORITHM']]
            )
            g.user_id = payload['user_id']
        except Exception:
            return error_response('Invalid token', 401)
        return f(*args, **kwargs)
    return decorated


@leaderboard_bp.route('/leaderboard', methods=['GET'])
@require_auth
def groups_leaderboard():
    """Return top groups, sorted by streak_count desc then activity desc."""
    db = Database()
    cutoff = datetime.utcnow() - timedelta(days=7)
    groups = list(db.find('groups', {}))
    leaderboard = []
    for g in groups:
        try:
            streak = db.find_one('group_streaks', {'group_id': g['_id']}) or {}
            activity = db.count('messages', {'group_id': g['_id'], 'created_at': {'$gt': cutoff}})
            leaderboard.append({
                'id': str(g['_id']),
                'name': g.get('name'),
                'member_count': len(g.get('members', [])),
                'activity': activity,
                'streak_count': streak.get('streak_count', 0)
            })
        except Exception:
            continue

    leaderboard.sort(key=lambda x: (x.get('streak_count', 0), x.get('activity', 0)), reverse=True)
    return success_response({'groups': leaderboard}, 'Groups leaderboard retrieved', 200)
