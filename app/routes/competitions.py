from flask import Blueprint, request, g
from app.utils import success_response, error_response, serialize_document
from app.services import Database
from app.models import Competition
from bson import ObjectId
from functools import wraps
import jwt
from app.utils.decorators import require_auth
from flask import current_app
from datetime import datetime

competitions_bp = Blueprint('competitions', __name__, url_prefix='/api/competitions')

@competitions_bp.route('', methods=['GET'])
@require_auth
def get_competitions():
    """Get all competitions"""
    db = Database()
    
    # Get all competitions, optionally filtered by group or category
    group_id = request.args.get('group_id')
    category = request.args.get('category')
    channel_id = request.args.get('channel_id')
    query = {}
    
    if group_id:
        try:
            query['group_ids'] = ObjectId(group_id)
        except:
            return error_response('Invalid group ID', 400)
            
    if channel_id:
        try:
            query['channel_id'] = ObjectId(channel_id)
        except:
            return error_response('Invalid channel ID', 400)
    elif category:
        query['category'] = category
    
    competitions = list(db.find('competitions', query))
    
    # Add id field for frontend and convert participant user_ids
    for comp in competitions:
        comp['id'] = str(comp['_id'])
        for participant in comp.get('participants', []):
            if participant.get('user_id'):
                participant['user_id'] = str(participant['user_id'])
    
    return success_response({'competitions': [serialize_document(c) for c in competitions]}, 'Competitions retrieved successfully', 200)

@competitions_bp.route('', methods=['POST'])
@require_auth
def create_competition():
    """Create a new competition"""
    data = request.get_json()
    
    required_fields = ['title', 'group_ids', 'start_time', 'end_time']
    if not data or not all(k in data for k in required_fields):
        return error_response('Missing required fields', 400)
    
    title = data.get('title', '').strip()
    description = data.get('description', '').strip()
    group_ids = data.get('group_ids')
    competition_type = data.get('competition_type', 'quiz')
    questions = data.get('questions', [])
    
    if not isinstance(group_ids, list) or not group_ids:
        return error_response('group_ids must be a non-empty list', 400)

    is_general = bool(data.get('is_general', False))

    try:
        group_id_objs = [ObjectId(gid) for gid in group_ids]
        # Handle ISO strings with 'Z' suffix (JavaScript format)
        start_time_str = data.get('start_time').replace('Z', '+00:00')
        end_time_str = data.get('end_time').replace('Z', '+00:00')
        start_time = datetime.fromisoformat(start_time_str)
        end_time = datetime.fromisoformat(end_time_str)
    except:
        return error_response('Invalid data format', 400)
    
    if not title:
        return error_response('Competition title is required', 400)
    
    db = Database()
    user_id_obj = ObjectId(g.user_id)
    
    # Check if user is a moderator of all groups
    first_group = None
    for group_id_obj in group_id_objs:
        group = db.find_one('groups', {'_id': group_id_obj})
        if not group:
            return error_response(f'Group with id {group_id_obj} not found', 404)
        
        if user_id_obj not in group['moderators']:
            return error_response('You must be a moderator of all groups to create an intergroup competition', 403)
        
        if not first_group:
            first_group = group

    channel_id = first_group.get('channel_id')
    channel_name = None
    if channel_id:
        ch = db.find_one('channels', {'_id': channel_id})
        if ch:
            channel_name = ch.get('name')
    
    # Optionally attach to a season
    season_id = data.get('season_id')
    if season_id:
        # Validate season exists and is active
        try:
            season_obj = ObjectId(season_id)
            season = db.find_one('seasons', {'_id': season_obj})
            if not season or not season.get('is_active'):
                return error_response('Invalid or inactive season', 400)
        except Exception:
            return error_response('Invalid season id', 400)

    competition_doc = Competition.create_competition_doc(
        title, description, group_ids, g.user_id, start_time, end_time, 
        questions, competition_type, str(channel_id) if channel_id else None, channel_name or 'General', season_id=season_id, is_general=is_general
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
    
    # Add id field for frontend
    competition['id'] = str(competition['_id'])
    
    # Convert participant user_ids to strings for frontend comparison
    for participant in competition.get('participants', []):
        if participant.get('user_id'):
            participant['user_id'] = str(participant['user_id'])
    
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
    
    competitions = db.find('competitions', {'group_ids': group_id_obj})
    return success_response([serialize_document(c) for c in competitions], 'Competitions retrieved successfully', 200)

@competitions_bp.route('/<comp_id>/join', methods=['POST'])
@require_auth
def join_competition(comp_id):
    """Join a competition - optionally specifying which group the user represents (for general/multi-group competitions)."""
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
    
    # Check if user exists
    user = db.find_one('users', {'_id': user_id_obj})
    if not user:
        return error_response('User not found', 404)

    user_groups = user.get('groups', [])
    competition_groups = competition.get('group_ids', [])

    # Ensure user is a member of at least one participating group
    can_join = any(gid in user_groups for gid in competition_groups)
    if not can_join:
        return error_response('You must be a member of a participating group to join this competition', 403)

    # Accept optional representing group from request body
    data = request.get_json() or {}
    represent_group = data.get('group_id')

    # If competition is single-group, auto-assign
    selected_group_obj = None
    if len(competition_groups) == 1 and not competition.get('is_general'):
        selected_group_obj = competition_groups[0]
    else:
        # require represent_group to be provided and valid
        if not represent_group:
            return error_response('Please specify which group you represent when joining this competition', 400)
        try:
            selected_group_obj = ObjectId(represent_group)
        except Exception:
            return error_response('Invalid group id', 400)
        # Check that selected group is part of competition and user is a member
        if selected_group_obj not in competition_groups:
            return error_response('Selected group is not part of this competition', 400)
        if selected_group_obj not in user_groups:
            return error_response('You are not a member of the selected group', 403)

    # Check if already participating
    for participant in competition.get('participants', []):
        if participant.get('user_id') == user_id_obj:
            return error_response('Already participating in this competition', 400)
    
    # Add participant with representing group
    participant_data = {
        'user_id': user_id_obj,
        'joined_at': datetime.utcnow(),
        'score': 0,
        'answers': [],
        'group_id': selected_group_obj  # store ObjectId of group they represent
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
    
    # Check if competition has ended
    end_time = competition.get('end_time')
    if end_time and end_time < datetime.utcnow():
        return error_response('This competition has ended', 400)
    
    user_id_obj = ObjectId(g.user_id)
    
    # Find user in participants
    participant_index = None
    for i, p in enumerate(competition.get('participants', [])):
        if p.get('user_id') == user_id_obj:
            participant_index = i
            break
    
    if participant_index is None:
        return error_response('Not participating in this competition', 400)
    
    # Check if already answered
    participant = competition['participants'][participant_index]
    existing_answers = [a.get('question_id') for a in participant.get('answers', [])]
    if question_id in existing_answers:
        return error_response('Question already answered', 400)

    # Validate answer and calculate score
    questions = competition.get('questions', [])
    try:
        q_idx = int(question_id)
        if q_idx < 0 or q_idx >= len(questions):
            return error_response('Invalid question ID', 400)
        
        question = questions[q_idx]
        # If question is a discussion type, it is submitted for manual review and not auto-scored
        if question.get('type') == 'discussion' or question.get('type') == 'Discussion':
            is_correct = False
            points_awarded = 0
        else:
            is_correct = str(answer).strip().lower() == str(question.get('correct_answer')).strip().lower()
            points_awarded = 1 if is_correct else 0  # 1 point per correct answer
        
    except ValueError:
        return error_response('Invalid question ID format', 400)

    # Store answer (allow optional discussion text)
    answer_data = {
        'question_id': question_id,
        'answer': answer,
        'is_correct': is_correct,
        'points': points_awarded,
        'submitted_at': datetime.utcnow(),
        'discussion': data.get('discussion', '') if isinstance(data, dict) else ''
    }

    # For discussion questions, add review metadata
    try:
        if question.get('type') == 'discussion':
            answer_data['is_reviewed'] = False
            answer_data['comments'] = []
    except Exception:
        pass
    
    update_op = {
        '$push': {'participants.$.answers': answer_data},
        '$inc': {'participants.$.score': points_awarded}
    }

    # If correct answer, update group scores
    if is_correct and points_awarded > 0:
        # Determine which group to credit: prefer participant's selected group, otherwise fallback to user's groups
        selected_group = None
        try:
            # Find participant record in competition to get their group_id
            for p in competition.get('participants', []):
                if p.get('user_id') == user_id_obj:
                    selected_group = p.get('group_id')
                    break
        except Exception:
            selected_group = None

        # If participant didn't choose a group (older comps), fall back to intersection of user groups and comp groups
        if not selected_group:
            user = db.find_one('users', {'_id': user_id_obj})
            if user:
                user_groups = user.get('groups', [])
                comp_groups = competition.get('group_ids', [])
                for gid in user_groups:
                    if gid in comp_groups:
                        selected_group = gid
                        break

        if selected_group:
            # Use string key for group_scores map
            update_op['$inc'][f'group_scores.{str(selected_group)}'] = points_awarded

            # Also update season aggregates if this competition is part of a season
            season_id = competition.get('season_id')
            if season_id:
                try:
                    db.update_one('seasons', {'_id': season_id}, {'$inc': {f'group_scores.{str(selected_group)}': points_awarded}}, raw=True)
                except Exception:
                    # Best-effort: don't fail the whole request if season update fails
                    pass

    # Update participant answers and score, and group scores
    db.update_one('competitions', 
                 {'_id': comp_id_obj, 'participants.user_id': user_id_obj},
                 update_op,
                 raw=True)
    
    # Get updated participant data
    updated_comp = db.find_one('competitions', {'_id': comp_id_obj})
    updated_participant = None
    for p in updated_comp.get('participants', []):
        if p.get('user_id') == user_id_obj:
            updated_participant = p
            break
    
    total_questions = len(questions)
    answered_count = len(updated_participant.get('answers', [])) if updated_participant else 0
    current_score = updated_participant.get('score', 0) if updated_participant else 0
    is_complete = answered_count >= total_questions
    
    return success_response({
        'is_correct': is_correct, 
        'points': points_awarded,
        'current_score': current_score,
        'answered_count': answered_count,
        'total_questions': total_questions,
        'is_complete': is_complete
    }, 'Answer submitted successfully', 200)

@competitions_bp.route('/<comp_id>/individual-leaderboard', methods=['GET'])
@require_auth
def get_individual_leaderboard(comp_id):
    """Get competition individual leaderboard"""
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

@competitions_bp.route('/<comp_id>/leaderboard', methods=['GET'])
@require_auth
def get_group_leaderboard(comp_id):
    """Get competition group leaderboard"""
    try:
        comp_id_obj = ObjectId(comp_id)
    except:
        return error_response('Invalid competition ID', 400)
    
    db = Database()
    competition = db.find_one('competitions', {'_id': comp_id_obj})
    
    if not competition:
        return error_response('Competition not found', 404)
        
    group_scores = competition.get('group_scores', {})
    if not group_scores:
        return success_response([], 'Leaderboard is empty.', 200)
        
    leaderboard = []
    for group_id, score in group_scores.items():
        try:
            group_id_obj = ObjectId(group_id)
            group = db.find_one('groups', {'_id': group_id_obj})
            if group:
                leaderboard.append({
                    'group': serialize_document(group),
                    'score': score
                })
        except:
            # Ignore invalid group IDs in scores map
            continue
            
    # Sort by score descending
    leaderboard.sort(key=lambda x: x['score'], reverse=True)
    
    return success_response(leaderboard, 'Leaderboard retrieved successfully', 200)


@competitions_bp.route('/<comp_id>/answers/<user_id>/<int:question_index>/mark', methods=['POST'])
@require_auth
def mark_answer(comp_id, user_id, question_index):
    """Mark a discussion answer and award points (competition owner or admin only)"""
    try:
        comp_id_obj = ObjectId(comp_id)
        participant_id_obj = ObjectId(user_id)
    except Exception:
        return error_response('Invalid id format', 400)

    db = Database()
    competition = db.find_one('competitions', {'_id': comp_id_obj})
    if not competition:
        return error_response('Competition not found', 404)

    # Check permissions: creator or admin
    requester = db.find_one('users', {'_id': ObjectId(g.user_id)})
    is_admin = requester.get('is_admin', False) if requester else False
    if str(competition.get('created_by')) != g.user_id and not is_admin:
        return error_response('Only competition creator or admins can mark answers', 403)

    # Find participant and specific answer
    participants = competition.get('participants', [])
    participant = None
    for p in participants:
        if p.get('user_id') == participant_id_obj:
            participant = p
            break
    if not participant:
        return error_response('Participant not found', 404)

    # Find answer
    answer_obj = None
    for a in participant.get('answers', []):
        if str(a.get('question_id')) == str(question_index):
            answer_obj = a
            break
    if not answer_obj:
        return error_response('Answer not found', 404)

    data = request.get_json() or {}
    try:
        points = int(data.get('points', 0))
    except Exception:
        return error_response('Invalid points value', 400)
    comment = data.get('comment', '').strip()

    # compute delta points to update participant score and group scores accordingly
    prev_points = int(answer_obj.get('points', 0) or 0)
    delta = points - prev_points

    # Update answer fields
    answer_obj['points'] = points
    answer_obj['is_reviewed'] = True
    answer_obj['marked_by'] = ObjectId(g.user_id)
    answer_obj['marked_at'] = __import__('datetime').datetime.utcnow()
    if comment:
        c = {'user_id': ObjectId(g.user_id), 'text': comment, 'created_at': __import__('datetime').datetime.utcnow()}
        answer_obj.setdefault('comments', []).append(c)

    # Update participant score
    participant['score'] = participant.get('score', 0) + delta

    # Update group_scores for participant's selected group if applicable
    selected_group = participant.get('group_id')
    if not selected_group:
        # fallback: choose first of competition groups that the user is a member of
        user = db.find_one('users', {'_id': participant.get('user_id')})
        if user:
            for gid in user.get('groups', []):
                if gid in competition.get('group_ids', []):
                    selected_group = gid
                    break
    if delta != 0 and selected_group:
        # apply delta to competition group_scores
        key = f'group_scores.{str(selected_group)}'
        try:
            db.update_one('competitions', {'_id': comp_id_obj}, { '$inc': { key: delta } }, raw=True)
        except Exception:
            pass
        # also update season aggregate if present
        season_id = competition.get('season_id')
        if season_id:
            try:
                db.update_one('seasons', {'_id': season_id}, {'$inc': {f'group_scores.{str(selected_group)}': delta}}, raw=True)
            except Exception:
                pass

    # Persist participants array back to DB
    try:
        db.update_one('competitions', {'_id': comp_id_obj}, {'participants': participants, 'updated_at': __import__('datetime').datetime.utcnow()})
    except Exception as e:
        return error_response('Failed to save mark', 500)

    return success_response({'answer': answer_obj, 'participant_score': participant['score']}, 'Answer marked', 200)


@competitions_bp.route('/<comp_id>/answers/<user_id>/<int:question_index>/comment', methods=['POST'])
@require_auth
def comment_on_answer(comp_id, user_id, question_index):
    """Add a threaded comment to an answer"""
    try:
        comp_id_obj = ObjectId(comp_id)
        participant_id_obj = ObjectId(user_id)
    except Exception:
        return error_response('Invalid id format', 400)

    data = request.get_json() or {}
    text = (data.get('text') or '').strip()
    if not text:
        return error_response('Comment text required', 400)

    db = Database()
    competition = db.find_one('competitions', {'_id': comp_id_obj})
    if not competition:
        return error_response('Competition not found', 404)

    # Find participant and answer
    participants = competition.get('participants', [])
    participant = None
    for p in participants:
        if p.get('user_id') == participant_id_obj:
            participant = p
            break
    if not participant:
        return error_response('Participant not found', 404)

    answer_obj = None
    for a in participant.get('answers', []):
        if str(a.get('question_id')) == str(question_index):
            answer_obj = a
            break
    if not answer_obj:
        return error_response('Answer not found', 404)

    comment = {'user_id': ObjectId(g.user_id), 'text': text, 'created_at': __import__('datetime').datetime.utcnow()}
    answer_obj.setdefault('comments', []).append(comment)

    # Persist
    try:
        db.update_one('competitions', {'_id': comp_id_obj}, {'participants': participants, 'updated_at': __import__('datetime').datetime.utcnow()})
    except Exception:
        return error_response('Failed to save comment', 500)

    return success_response({'comment': comment}, 'Comment added', 201)


@competitions_bp.route('/<comp_id>', methods=['DELETE'])
@require_auth
def delete_competition(comp_id):
    """Delete a competition (creator only)"""
    try:
        comp_id_obj = ObjectId(comp_id)
    except:
        return error_response('Invalid competition ID', 400)
    
    db = Database()
    competition = db.find_one('competitions', {'_id': comp_id_obj})
    
    if not competition:
        return error_response('Competition not found', 404)
    
    # Check if user is the creator or an admin
    user = db.find_one('users', {'_id': ObjectId(g.user_id)})
    is_admin = user.get('is_admin', False) if user else False
    
    if str(competition.get('created_by')) != g.user_id and not is_admin:
        return error_response('Only the competition creator can delete this competition', 403)
    
    db.delete_one('competitions', {'_id': comp_id_obj})
    
    return success_response(None, 'Competition deleted successfully', 200)

@competitions_bp.route('/<comp_id>/end', methods=['POST'])
@require_auth
def end_competition(comp_id):
    """End a competition early (creator only)"""
    try:
        comp_id_obj = ObjectId(comp_id)
    except:
        return error_response('Invalid competition ID', 400)
    
    db = Database()
    competition = db.find_one('competitions', {'_id': comp_id_obj})
    
    if not competition:
        return error_response('Competition not found', 404)
    
    # Check if user is the creator or an admin
    user = db.find_one('users', {'_id': ObjectId(g.user_id)})
    is_admin = user.get('is_admin', False) if user else False
    
    if str(competition.get('created_by')) != g.user_id and not is_admin:
        return error_response('Only the competition creator can end this competition', 403)
    
    # Set end_time to now and mark as completed
    db.update_one('competitions', {'_id': comp_id_obj}, {
        'end_time': datetime.utcnow(),
        'completed': True,
        'is_active': False
    })
    
    return success_response(None, 'Competition ended successfully', 200)
