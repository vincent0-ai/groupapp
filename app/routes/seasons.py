from flask import Blueprint, request, g, current_app
from app.utils import success_response, error_response, serialize_document
from app.services import Database
from app.models import Season
from bson import ObjectId
from datetime import timedelta
from app.utils.decorators import require_auth

seasons_bp = Blueprint('seasons', __name__, url_prefix='/api/seasons')

@seasons_bp.route('', methods=['GET'])
@require_auth
def list_seasons():
    db = Database()
    seasons = list(db.find('seasons', {}, sort=[('start_time', -1)]))
    return success_response({'seasons': [serialize_document(s) for s in seasons]}, 'Seasons retrieved', 200)

@seasons_bp.route('', methods=['POST'])
@require_auth
def create_season():
    """Create a weekly season. Only admins allowed to create seasons."""
    db = Database()
    user = db.find_one('users', {'_id': ObjectId(g.user_id)})
    if not user or not user.get('is_admin'):
        return error_response('Only admins can create seasons', 403)

    data = request.get_json() or {}
    title = data.get('title', '').strip()
    start_time = None
    end_time = None

    try:
        if data.get('start_time'):
            start_time = data.get('start_time')
        else:
            # use current time
            from datetime import datetime
            start_time = datetime.utcnow().isoformat()
        # ensure ISO format
        from datetime import datetime
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        # 7 days season
        end_dt = start_dt + timedelta(days=7)
    except Exception:
        return error_response('Invalid start_time format', 400)

    if not title:
        return error_response('Season title is required', 400)

    # Ensure no active overlapping season
    active = db.find_one('seasons', {'is_active': True})
    if active:
        return error_response('There is already an active season. Close it before creating a new one.', 400)

    season_doc = Season.create_season_doc(title, start_dt, end_dt, g.user_id)
    sid = db.insert_one('seasons', season_doc)
    if not sid:
        return error_response('Failed to create season', 500)
    season_doc['_id'] = sid
    return success_response(serialize_document(season_doc), 'Season created successfully', 201)

@seasons_bp.route('/<season_id>/close', methods=['POST'])
@require_auth
def close_season(season_id):
    """Close a season and compute winners from group_scores."""
    db = Database()
    user = db.find_one('users', {'_id': ObjectId(g.user_id)})
    if not user or not user.get('is_admin'):
        return error_response('Only admins can close seasons', 403)

    try:
        season_obj = ObjectId(season_id)
    except Exception:
        return error_response('Invalid season id', 400)

    season = db.find_one('seasons', {'_id': season_obj})
    if not season:
        return error_response('Season not found', 404)

    if not season.get('is_active'):
        return error_response('Season already closed', 400)

    # Compute winners from group_scores
    group_scores = season.get('group_scores', {}) or {}
    # sort by score desc
    sorted_groups = sorted(group_scores.items(), key=lambda x: x[1], reverse=True)
    winners = []
    for rank, (group_id, score) in enumerate(sorted_groups[:10], start=1):
        try:
            g_obj = db.find_one('groups', {'_id': ObjectId(group_id)})
            winners.append({'rank': rank, 'group_id': str(group_id), 'group': serialize_document(g_obj) if g_obj else None, 'score': score})
        except Exception:
            winners.append({'rank': rank, 'group_id': str(group_id), 'group': None, 'score': score})

    # Update season
    db.update_one('seasons', {'_id': season_obj}, {'is_active': False, 'winners': winners, 'updated_at': __import__('datetime').datetime.utcnow()}, raw=False)

    return success_response({'winners': winners}, 'Season closed and winners computed', 200)

@seasons_bp.route('/<season_id>', methods=['GET'])
@require_auth
def get_season(season_id):
    try:
        season_obj = ObjectId(season_id)
    except Exception:
        return error_response('Invalid season id', 400)

    db = Database()
    season = db.find_one('seasons', {'_id': season_obj})
    if not season:
        return error_response('Season not found', 404)
    return success_response(serialize_document(season), 'Season retrieved', 200)