"""
Direct Messages (DM) API Routes
"""
from flask import Blueprint, request, jsonify, g
from app.services import Database
from app.utils.decorators import token_required
from bson import ObjectId
from datetime import datetime

dm_bp = Blueprint('dm', __name__, url_prefix='/api/dm')
db = Database()


def get_or_create_dm_thread(user1_id, user2_id):
    """Get existing DM thread or create a new one between two users."""
    # Sort IDs to ensure consistent lookup regardless of who initiated
    participant_ids = sorted([str(user1_id), str(user2_id)])
    
    thread = db.db.dm_threads.find_one({
        'participants': participant_ids
    })
    
    if thread:
        return thread
    
    # Create new thread
    new_thread = {
        'participants': participant_ids,
        'created_at': datetime.utcnow(),
        'last_message_at': datetime.utcnow(),
        'last_message': None
    }
    
    result = db.db.dm_threads.insert_one(new_thread)
    new_thread['_id'] = result.inserted_id
    return new_thread


@dm_bp.route('/threads', methods=['GET'])
@token_required
def get_dm_threads():
    """Get all DM threads for the current user"""
    try:
        user_id = g.user_id
        
        threads = list(db.db.dm_threads.find({
            'participants': user_id
        }).sort('last_message_at', -1))
        
        # Enrich with other user's profile
        result = []
        for thread in threads:
            other_user_id = [p for p in thread['participants'] if p != user_id][0]
            other_user = db.find_one('users', {'_id': ObjectId(other_user_id)})
            
            result.append({
                '_id': str(thread['_id']),
                'other_user': {
                    'id': str(other_user['_id']) if other_user else other_user_id,
                    'username': other_user.get('username', 'Unknown') if other_user else 'Unknown',
                    'full_name': other_user.get('full_name', '') if other_user else '',
                    'avatar_url': other_user.get('avatar_url', '') if other_user else ''
                },
                'last_message': thread.get('last_message'),
                'last_message_at': thread.get('last_message_at').isoformat() if thread.get('last_message_at') else None,
                'unread_count': db.db.dm_messages.count_documents({
                    'thread_id': thread['_id'],
                    'sender_id': ObjectId(other_user_id),
                    'read': False
                })
            })
        
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@dm_bp.route('/thread/<other_user_id>', methods=['GET'])
@token_required
def get_or_start_thread(other_user_id):
    """Get or create a DM thread with another user"""
    try:
        # Verify other user exists
        other_user = db.find_one('users', {'_id': ObjectId(other_user_id)})
        if not other_user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        thread = get_or_create_dm_thread(g.user_id, other_user_id)
        
        return jsonify({
            'success': True,
            'data': {
                'thread_id': str(thread['_id']),
                'other_user': {
                    'id': str(other_user['_id']),
                    'username': other_user.get('username'),
                    'full_name': other_user.get('full_name'),
                    'avatar_url': other_user.get('avatar_url')
                }
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@dm_bp.route('/thread/<thread_id>/messages', methods=['GET'])
@token_required
def get_dm_messages(thread_id):
    """Get messages from a DM thread"""
    try:
        thread_id_obj = ObjectId(thread_id)
        
        # Verify user is participant
        thread = db.db.dm_threads.find_one({'_id': thread_id_obj})
        if not thread or g.user_id not in thread.get('participants', []):
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        skip = (page - 1) * per_page
        
        messages = list(db.db.dm_messages.find({
            'thread_id': thread_id_obj
        }).sort('created_at', -1).skip(skip).limit(per_page))
        
        # Reverse for chronological order
        messages = list(reversed(messages))
        
        # Mark messages as read
        other_user_id = [p for p in thread['participants'] if p != g.user_id][0]
        db.db.dm_messages.update_many(
            {
                'thread_id': thread_id_obj,
                'sender_id': ObjectId(other_user_id),
                'read': False
            },
            {'$set': {'read': True, 'read_at': datetime.utcnow()}}
        )
        
        # Format messages
        result = []
        for msg in messages:
            sender = db.find_one('users', {'_id': msg['sender_id']})
            result.append({
                '_id': str(msg['_id']),
                'content': msg.get('content', ''),
                'sender_id': str(msg['sender_id']),
                'sender_name': sender.get('full_name', sender.get('username', 'Unknown')) if sender else 'Unknown',
                'created_at': msg.get('created_at').isoformat() if msg.get('created_at') else None,
                'read': msg.get('read', False)
            })
        
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@dm_bp.route('/thread/<thread_id>/messages', methods=['POST'])
@token_required
def send_dm_message(thread_id):
    """Send a message in a DM thread"""
    try:
        thread_id_obj = ObjectId(thread_id)
        
        # Verify user is participant
        thread = db.db.dm_threads.find_one({'_id': thread_id_obj})
        if not thread or g.user_id not in thread.get('participants', []):
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        data = request.get_json()
        content = data.get('content', '').strip()
        
        if not content:
            return jsonify({'success': False, 'error': 'Message content required'}), 400
        
        # Create message
        message = {
            'thread_id': thread_id_obj,
            'sender_id': ObjectId(g.user_id),
            'content': content,
            'created_at': datetime.utcnow(),
            'read': False
        }
        
        result = db.db.dm_messages.insert_one(message)
        
        # Update thread's last message
        db.db.dm_threads.update_one(
            {'_id': thread_id_obj},
            {
                '$set': {
                    'last_message': content[:100],
                    'last_message_at': datetime.utcnow()
                }
            }
        )
        
        # Create notification for recipient
        other_user_id = [p for p in thread['participants'] if p != g.user_id][0]
        sender = db.find_one('users', {'_id': ObjectId(g.user_id)})
        sender_name = sender.get('full_name', sender.get('username', 'Someone')) if sender else 'Someone'
        
        from app.routes.notifications import create_notification
        create_notification(
            user_id=other_user_id,
            notification_type='dm',
            message=f'{sender_name} sent you a message',
            link=f'/messages?dm={g.user_id}'
        )
        
        return jsonify({
            'success': True,
            'data': {
                '_id': str(result.inserted_id),
                'content': content,
                'sender_id': g.user_id,
                'created_at': message['created_at'].isoformat()
            }
        }), 201
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@dm_bp.route('/unread-count', methods=['GET'])
@token_required
def get_unread_dm_count():
    """Get total unread DM count for the user"""
    try:
        # Find all threads the user is in
        threads = list(db.db.dm_threads.find({'participants': g.user_id}))
        
        total_unread = 0
        for thread in threads:
            other_user_id = [p for p in thread['participants'] if p != g.user_id][0]
            count = db.db.dm_messages.count_documents({
                'thread_id': thread['_id'],
                'sender_id': ObjectId(other_user_id),
                'read': False
            })
            total_unread += count
        
        return jsonify({'success': True, 'data': {'unread_count': total_unread}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
