from flask import Blueprint, request, g
from app.utils import success_response, error_response, serialize_document
from app.services import Database
from app.models import Competition
from bson import ObjectId
from functools import wraps
import jwt
from flask import current_app
from datetime import datetime

competitions_bp = Blueprint('competitions', __name__, url_prefix='/api/competitions')

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

@competitions_bp.route('', methods=['GET'])
@require_auth
def get_competitions():
    """Get all competitions"""
    db = Database()
    
    # Get all competitions, optionally filtered by group
    group_id = request.args.get('group_id')
    query = {}
    
    if group_id:
        try:
            query['group_id'] = ObjectId(group_id)
        except:
            return error_response('Invalid group ID', 400)
    
    competitions = list(db.find('competitions', query))
    
    return success_response({'competitions': [serialize_document(c) for c in competitions]}, 'Competitions retrieved successfully', 200)

@competitions_bp.route('', methods=['POST'])
@require_auth
def create_competition():
    """Create a new competition"""
    data = request.get_json()
    
    required_fields = ['title', 'group_id', 'start_time', 'end_time']
    if not data or not all(k in data for k in required_fields):
        return error_response('Missing required fields', 400)
    
    title = data.get('title', '').strip()
    description = data.get('description', '').strip()
    group_id = data.get('group_id')
    competition_type = data.get('competition_type', 'quiz')
    questions = data.get('questions', [])
    
    try:
        group_id_obj = ObjectId(group_id)
        start_time = datetime.fromisoformat(data.get('start_time'))
        end_time = datetime.fromisoformat(data.get('end_time'))
    except:
        return error_response('Invalid data format', 400)
    
    if not title:
        return error_response('Competition title is required', 400)
    
    db = Database()
    
    # Check if user is group moderator
    group = db.find_one('groups', {'_id': group_id_obj})
    if not group:
        return error_response('Group not found', 404)
    
    user_id_obj = ObjectId(g.user_id)
    if user_id_obj not in group['moderators']:
        return error_response('Only group moderators can create competitions', 403)
    
    competition_doc = Competition.create_competition_doc(
        title, description, group_id, g.user_id, start_time, end_time, 
        questions, competition_type
    )
    
    comp_id = db.insert_one('competitions', competition_doc)
    
    if not comp_id:
        return error_response('Failed to create competition', 500)
    
    competition_doc['_id'] = comp_id
    return success_response(serialize_document(competition_doc), 'Competition created successfully', 201)

@competitions_bp.route('/<comp_id>', methods=['GET'])
@require_auth
def get_competition(comp_id):
    """Get competition details"""
    try:
        comp_id_obj = ObjectId(comp_id)
    except:
        return error_response('Invalid competition ID', 400)
    
    db = Database()
    competition = db.find_one('competitions', {'_id': comp_id_obj})
    
    if not competition:
        return error_response('Competition not found', 404)
    
    return success_response(serialize_document(competition), 'Competition retrieved successfully', 200)

@competitions_bp.route('/group/<group_id>', methods=['GET'])
@require_auth
def get_group_competitions(group_id):
    """Get all competitions for a group"""
    try:
        group_id_obj = ObjectId(group_id)
    except:
        return error_response('Invalid group ID', 400)
    
    db = Database()
    group = db.find_one('groups', {'_id': group_id_obj})
    
    if not group:
        return error_response('Group not found', 404)
    
    competitions = db.find('competitions', {'group_id': group_id_obj})
    return success_response([serialize_document(c) for c in competitions], 'Competitions retrieved successfully', 200)

@competitions_bp.route('/<comp_id>/join', methods=['POST'])
@require_auth
def join_competition(comp_id):
    """Join a competition"""
    try:
        comp_id_obj = ObjectId(comp_id)
    except:
        return error_response('Invalid competition ID', 400)
    
    db = Database()
    competition = db.find_one('competitions', {'_id': comp_id_obj})
    
    if not competition:
        return error_response('Competition not found', 404)
    
    if not competition['is_active']:
        return error_response('Competition is not active', 400)
    
    user_id_obj = ObjectId(g.user_id)
    
    # Check if already participating
    for participant in competition.get('participants', []):
        if participant.get('user_id') == user_id_obj:
            return error_response('Already participating in this competition', 400)
    
    # Add participant
    participant_data = {
        'user_id': user_id_obj,
        'joined_at': datetime.utcnow(),
        'score': 0,
        'answers': []
    }
    
    db.push_to_array('competitions', {'_id': comp_id_obj}, 'participants', participant_data)
    
    return success_response(None, 'Joined competition successfully', 200)

@competitions_bp.route('/<comp_id>/submit-answer', methods=['POST'])
@require_auth
def submit_answer(comp_id):
    """Submit an answer to a competition question"""
    data = request.get_json()
    
    if not data or 'question_id' not in data or 'answer' not in data:
        return error_response('Missing required fields', 400)
    
    try:
        comp_id_obj = ObjectId(comp_id)
    except:
        return error_response('Invalid competition ID', 400)
    
    question_id = data.get('question_id')
    answer = data.get('answer')
    
    db = Database()
    competition = db.find_one('competitions', {'_id': comp_id_obj})
    
    if not competition:
        return error_response('Competition not found', 404)
    
    user_id_obj = ObjectId(g.user_id)
    
    # Find user in participants
    participant_index = None
    for i, p in enumerate(competition.get('participants', [])):
        if p.get('user_id') == user_id_obj:
            participant_index = i
            break
    
    if participant_index is None:
        return error_response('Not participating in this competition', 400)
    
    # Store answer (in production, validate against correct answers)
    answer_data = {
        'question_id': question_id,
        'answer': answer,
        'submitted_at': datetime.utcnow()
    }
    
    # This is a simplified version; in production you'd calculate score
    db.update_one('competitions', 
                 {'_id': comp_id_obj, 'participants.user_id': user_id_obj},
                 {'$push': {'participants.$.answers': answer_data}})
    
    return success_response(None, 'Answer submitted successfully', 200)

@competitions_bp.route('/<comp_id>/leaderboard', methods=['GET'])
@require_auth
def get_leaderboard(comp_id):
    """Get competition leaderboard"""
    try:
        comp_id_obj = ObjectId(comp_id)
    except:
        return error_response('Invalid competition ID', 400)
    
    db = Database()
    competition = db.find_one('competitions', {'_id': comp_id_obj})
    
    if not competition:
        return error_response('Competition not found', 404)
    
    # Get leaderboard with user details
    leaderboard = []
    for participant in competition.get('participants', []):
        user = db.find_one('users', {'_id': participant.get('user_id')})
        if user:
            del user['password_hash']
            leaderboard.append({
                'user': serialize_document(user),
                'score': participant.get('score', 0),
                'joined_at': participant.get('joined_at')
            })
    
    # Sort by score descending
    leaderboard.sort(key=lambda x: x['score'], reverse=True)
    
    return success_response(leaderboard, 'Leaderboard retrieved successfully', 200)
