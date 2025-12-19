from datetime import datetime
from bson import ObjectId
from typing import Dict, List, Optional

class User:
    """User model for MongoDB"""
    
    @staticmethod
    def create_user_doc(email: str, username: str, password_hash: str, 
                       full_name: str = '', avatar_url: str = '') -> Dict:
        """Create a new user document"""
        return {
            '_id': ObjectId(),
            'email': email,
            'username': username,
            'password_hash': password_hash,
            'full_name': full_name,
            'avatar_url': avatar_url or f'https://api.dicebear.com/7.x/avataaars/svg?seed={email}',
            'bio': '',
            'points': 0,
            'badges': [],
            'groups': [],  # List of group IDs
            'channels': [],  # List of channel IDs
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            'last_login': None,
            'is_active': True,
            'is_verified': False,
            'is_admin': False,
            'preferences': {
                'notifications_enabled': True,
                'dark_mode': False,
                'language': 'en'
            }
        }

class Group:
    """Group model for MongoDB"""
    
    @staticmethod
    def create_group_doc(name: str, description: str, owner_id: str,
                        channel_id: Optional[str] = None, is_private: bool = False, avatar_url: str = '') -> Dict:
        """Create a new group document; channel_id is a reference to Channel._id"""
        return {
            '_id': ObjectId(),
            'name': name,
            'description': description,
            'channel_id': ObjectId(channel_id) if channel_id else None,
            'owner_id': ObjectId(owner_id),
            'avatar_url': avatar_url or f'https://api.dicebear.com/7.x/shapes/svg?seed={name}',
            'is_private': is_private,
            'members': [ObjectId(owner_id)],  # Include owner as member
            'pending_members': [],  # List of user IDs waiting for approval
            'moderators': [ObjectId(owner_id)],
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            'settings': {
                'allow_file_uploads': True,
                'require_approval': False,
                'max_file_size': 104857600  # 100MB
            }
        }

class Channel:
    """Channel (Category) model for MongoDB. Channels are global categories such as 'Science' or 'Games'."""
    
    @staticmethod
    def create_channel_doc(name: str, description: str = '', is_private: bool = False) -> Dict:
        """Create a new channel (category) document"""
        return {
            '_id': ObjectId(),
            'name': name,
            'description': description,
            'is_private': is_private,
            'group_count': 0,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }

class Message:
    """Message model for MongoDB"""
    
    @staticmethod
    def create_message_doc(content: str, user_id: str, channel_id: Optional[str],
                          group_id: str, attachments: List = None,
                          reply_to: Optional[str] = None) -> Dict:
        """Create a new message document"""
        return {
            '_id': ObjectId(),
            'content': content,
            'user_id': ObjectId(user_id),
            'channel_id': ObjectId(channel_id) if channel_id else None,
            'group_id': ObjectId(group_id),
            'attachments': attachments or [],
            'reply_to': ObjectId(reply_to) if reply_to else None,
            'reactions': {},  # Format: {'emoji': ['user_id1', 'user_id2']}
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            'is_edited': False,
            'is_pinned': False
        }

class Argument:
    """Threaded Argument node model for MongoDB

    A node represents a Claim, Evidence, or Counter-argument tied to a group and
    optionally to a message (discussion) or another argument node.
    """

    VALID_TYPES = ('claim', 'evidence', 'counter')

    @staticmethod
    def create_argument_doc(node_type: str, content: str, author_id: str,
                            group_id: str, message_id: Optional[str] = None,
                            parent_id: Optional[str] = None, metadata: Dict = None) -> Dict:
        """Create a new argument node document"""
        if node_type not in Argument.VALID_TYPES:
            raise ValueError('Invalid node_type')

        return {
            '_id': ObjectId(),
            'node_type': node_type,
            'content': content,
            'author_id': ObjectId(author_id),
            'group_id': ObjectId(group_id),
            'message_id': ObjectId(message_id) if message_id else None,
            'parent_id': ObjectId(parent_id) if parent_id else None,
            'metadata': metadata or {},
            'reactions': {},
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }

class Whiteboard:
    """Whiteboard session model"""
    
    @staticmethod
    def create_whiteboard_doc(group_id: str, channel_id: str, 
                             created_by: str, title: str = '') -> Dict:
        """Create a new whiteboard session"""
        return {
            '_id': ObjectId(),
            'group_id': ObjectId(group_id),
            'channel_id': ObjectId(channel_id),
            'created_by': ObjectId(created_by),
            'title': title or 'Untitled Whiteboard',
            'drawing_data': [],  # Stores drawing actions
            'audio_files': [],
            'raised_hands': [],
            'participants': [ObjectId(created_by)],
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            'is_active': True
        }

class Competition:
    """Competition/Challenge model"""
    
    @staticmethod
    def create_competition_doc(title: str, description: str, group_ids: List[str],
                              created_by: str, start_time: datetime,
                              end_time: datetime, questions: List = None,
                              competition_type: str = 'quiz',
                              channel_id: Optional[str] = None, category: str = 'General') -> Dict:
        """Create a new competition (optionally tied to a channel/category)"""
        is_intergroup = len(group_ids) > 1
        group_scores = {gid: 0 for gid in group_ids}
        return {
            '_id': ObjectId(),
            'title': title,
            'description': description,
            'group_ids': [ObjectId(gid) for gid in group_ids],
            'is_intergroup': is_intergroup,
            'channel_id': ObjectId(channel_id) if channel_id else None,
            'category': category,
            'created_by': ObjectId(created_by),
            'competition_type': competition_type,  # 'quiz', 'challenge', 'contest'
            'questions': questions or [],
            'start_time': start_time,
            'end_time': end_time,
            'participants': [],
            'group_scores': group_scores,
            'individual_leaderboard': [],  # Format: [{'user_id': str, 'score': int, 'time': int}]
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            'is_active': True
        }

class File:
    """File/Document model"""
    
    @staticmethod
    def create_file_doc(filename: str, file_type: str, uploaded_by: str,
                       group_id: str, channel_id: Optional[str] = None,
                       competition_id: Optional[str] = None,
                       minio_path: str = '') -> Dict:
        """Create a new file document"""
        return {
            '_id': ObjectId(),
            'filename': filename,
            'file_type': file_type,
            'uploaded_by': ObjectId(uploaded_by),
            'group_id': ObjectId(group_id),
            'channel_id': ObjectId(channel_id) if channel_id else None,
            'competition_id': ObjectId(competition_id) if competition_id else None,
            'minio_path': minio_path,
            'file_size': 0,
            'mime_type': '',
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            'downloads': 0,
            'is_public': False
        }

class Notification:
    """Notification model"""
    
    @staticmethod
    def create_notification_doc(user_id: str, notification_type: str,
                               title: str, message: str,
                               related_id: Optional[str] = None,
                               data: Dict = None) -> Dict:
        """Create a new notification"""
        return {
            '_id': ObjectId(),
            'user_id': ObjectId(user_id),
            'notification_type': notification_type,  # 'message', 'invite', 'challenge', etc.
            'title': title,
            'message': message,
            'related_id': ObjectId(related_id) if related_id else None,
            'data': data or {},
            'is_read': False,
            'created_at': datetime.utcnow(),
            'expires_at': None
        }

class Event:
    """Event/Invitation model"""
    
    @staticmethod
    def create_event_doc(event_type: str, title: str, description: str,
                        group_id: str, created_by: str, 
                        start_time: datetime, end_time: Optional[datetime] = None,
                        invitees: List = None) -> Dict:
        """Create a new event"""
        return {
            '_id': ObjectId(),
            'event_type': event_type,  # 'whiteboard', 'competition', 'group_meeting'
            'title': title,
            'description': description,
            'group_id': ObjectId(group_id),
            'created_by': ObjectId(created_by),
            'start_time': start_time,
            'end_time': end_time,
            'invitees': [ObjectId(uid) for uid in (invitees or [])],
            'attendees': [ObjectId(created_by)],
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            'is_cancelled': False
        }

class GroupStreak:
    """Group streak model for tracking daily group engagement"""

    @staticmethod
    def create_group_streak_doc(group_id: str, streak_count: int = 0,
                                last_active_day: Optional[str] = None,
                                threshold: Optional[int] = None,
                                min_percent: Optional[float] = None) -> Dict:
        """Create a new group streak document"""
        return {
            '_id': ObjectId(),
            'group_id': ObjectId(group_id),
            'streak_count': streak_count,
            'last_active_day': last_active_day,  # ISO date string YYYY-MM-DD
            'threshold': threshold,
            'min_percent': min_percent,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
