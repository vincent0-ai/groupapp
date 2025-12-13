"""
Notifications API Routes
"""
from flask import Blueprint, request, jsonify, g
from app.services import Database
from app.utils.decorators import require_auth
from bson import ObjectId
from datetime import datetime

notifications_bp = Blueprint('notifications', __name__, url_prefix='/api/notifications')
db = Database()


@notifications_bp.route('', methods=['GET'])
@require_auth
def get_notifications():
    """Get user's notifications"""
    try:
        limit = request.args.get('limit', 50, type=int)
        
        notifications = list(db.db.notifications.find(
            {'user_id': ObjectId(g.user_id)}
        ).sort('created_at', -1).limit(limit))
        
        # Count unread
        unread_count = db.db.notifications.count_documents({
            'user_id': ObjectId(g.user_id),
            'read': False
        })
        
        # Format for response
        for n in notifications:
            n['_id'] = str(n['_id'])
            n['user_id'] = str(n['user_id'])
            if 'created_at' in n:
                n['created_at'] = n['created_at'].isoformat()
        
        return jsonify({
            'success': True,
            'data': {
                'notifications': notifications,
                'unread_count': unread_count
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@notifications_bp.route('/<notification_id>/read', methods=['POST'])
@require_auth
def mark_as_read(notification_id):
    """Mark a notification as read"""
    try:
        result = db.db.notifications.update_one(
            {
                '_id': ObjectId(notification_id),
                'user_id': ObjectId(g.user_id)
            },
            {'$set': {'read': True, 'read_at': datetime.utcnow()}}
        )
        
        if result.modified_count == 0:
            return jsonify({'success': False, 'error': 'Notification not found'}), 404
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@notifications_bp.route('/read-all', methods=['POST'])
@require_auth
def mark_all_as_read():
    """Mark all notifications as read"""
    try:
        db.db.notifications.update_many(
            {'user_id': ObjectId(g.user_id), 'read': False},
            {'$set': {'read': True, 'read_at': datetime.utcnow()}}
        )
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@notifications_bp.route('/<notification_id>', methods=['DELETE'])
@require_auth
def delete_notification(notification_id):
    """Delete a notification"""
    try:
        result = db.db.notifications.delete_one({
            '_id': ObjectId(notification_id),
            'user_id': ObjectId(g.user_id)
        })
        
        if result.deleted_count == 0:
            return jsonify({'success': False, 'error': 'Notification not found'}), 404
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def create_notification(user_id, notification_type, message, link=None, data=None):
    """
    Helper function to create a notification.
    
    Types:
    - mention: User was mentioned in a message
    - message: New message in a group
    - join_request: User requested to join a group
    - announcement: Admin announcement
    - reaction: Someone reacted to user's message
    - group_invite: User was invited to a group
    - dm: Direct message received
    """
    try:
        notification = {
            'user_id': ObjectId(user_id) if isinstance(user_id, str) else user_id,
            'type': notification_type,
            'message': message,
            'link': link,
            'data': data or {},
            'read': False,
            'created_at': datetime.utcnow()
        }
        
        result = db.db.notifications.insert_one(notification)
        return str(result.inserted_id)
    except Exception as e:
        print(f"Failed to create notification: {e}")
        return None


def create_bulk_notifications(user_ids, notification_type, message, link=None, data=None):
    """Create notifications for multiple users"""
    try:
        notifications = []
        for user_id in user_ids:
            notifications.append({
                'user_id': ObjectId(user_id) if isinstance(user_id, str) else user_id,
                'type': notification_type,
                'message': message,
                'link': link,
                'data': data or {},
                'read': False,
                'created_at': datetime.utcnow()
            })
        
        if notifications:
            db.db.notifications.insert_many(notifications)
        return True
    except Exception as e:
        print(f"Failed to create bulk notifications: {e}")
        return False
