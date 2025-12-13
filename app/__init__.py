from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
from config.config import config
from app.services import Database
import os
from datetime import datetime
from bson import ObjectId

def create_app(config_name='development'):
    """Create and configure Flask app"""
    
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    
    # Load configuration
    app.config.from_object(config[config_name])
    
    # Initialize extensions
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    socketio = SocketIO(app, cors_allowed_origins="*")
    # Attach socketio to app for access in routes
    app.socketio = socketio
    
    # Create upload folder
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.groups import groups_bp
    from app.routes.messages import messages_bp
    from app.routes.competitions import competitions_bp
    from app.routes.files import files_bp
    from app.routes.users import users_bp
    from app.routes.whiteboards import whiteboards_bp
    from app.routes.admin import admin_bp
    from app.routes.notifications import notifications_bp
    from app.routes.dm import dm_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(groups_bp)
    app.register_blueprint(messages_bp)
    app.register_blueprint(competitions_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(whiteboards_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(dm_bp)
    
    # Page routes (serving templates)

    
    @app.route('/auth')
    def auth_page():
        """Serve auth page"""
        return render_template('auth.html')
    
    @app.route('/admin')
    def admin_page():
        """Serve admin page"""
        return render_template('admin.html')
    
    @app.route('/dashboard')
    @app.route('/')
    def dashboard():
        """Serve dashboard"""
        return render_template('dashboard.html')
    
    @app.route('/groups')
    def groups_page():
        """Serve groups page"""
        return render_template('groups.html')
    
    @app.route('/messages')
    def messages_page():
        """Serve messages page"""
        return render_template('messages.html')
    
    @app.route('/dm')
    def dm_page():
        """Serve direct messages page"""
        return render_template('dm.html')
    
    @app.route('/competitions')
    def competitions_page():
        """Serve competitions page"""
        return render_template('competitions.html')
    
    @app.route('/files')
    def files_page():
        """Serve files page"""
        return render_template('files.html')
    
    @app.route('/profile')
    def profile_page():
        """Serve profile page"""
        return render_template('profile.html')
    
    @app.route('/whiteboard')
    def whiteboard_page():
        """Serve whiteboard page"""
        return render_template('whiteboard.html')
    
    @app.route('/leaderboard')
    def leaderboard_page():
        """Serve leaderboard page"""
        return render_template('leaderboard.html')
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'status': 'error', 'message': 'Not found'}), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({'status': 'error', 'message': 'Internal server error'}), 500
    
    # Health check endpoint
    @app.route('/health', methods=['GET'])
    def health_check():
        return jsonify({'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()}), 200
    
    # Socket.IO events for real-time communication
    connected_users = {}  # Store user connections {user_id: sid}
    online_users = {}  # Track online users per room {room: {user_id: {profile, last_seen}}}
    
    @socketio.on('connect')
    def handle_connect():
        """Handle user connection"""
        print(f'Client connected: {request.sid}')
        emit('connect_response', {'data': 'Connected to server'})
    
    @socketio.on('join_room')
    def on_join_room(data):
        """Handle user joining a room"""
        room = data.get('room')
        user_id = data.get('user_id')
        
        if room and user_id:
            # If joining a whiteboard session, check if active and persist participant
            if room.startswith('whiteboard:'):
                try:
                    wb_id = room.split(':', 1)[1]
                    db = Database()
                    wb = db.find_one('whiteboards', {'_id': ObjectId(wb_id)})
                    if not wb or not wb.get('is_active', True):
                        emit('error', {'message': 'Session has ended'})
                        return
                    
                    db.push_to_array('whiteboards', {'_id': ObjectId(wb_id)}, 'participants', ObjectId(user_id))
                except Exception as e:
                    print(f"Error joining whiteboard: {e}")
                    pass

            join_room(room)
            connected_users[user_id] = request.sid
            
            # Include basic user profile info
            try:
                db = Database()
                user_doc = db.find_one('users', {'_id': ObjectId(user_id)})
                profile = None
                if user_doc:
                    profile = {
                        'id': str(user_doc['_id']),
                        'full_name': user_doc.get('full_name', ''),
                        'avatar_url': user_doc.get('avatar_url', ''),
                        'username': user_doc.get('username', '')
                    }
            except Exception:
                profile = None
            
            # Track online status per room
            if room not in online_users:
                online_users[room] = {}
            online_users[room][user_id] = {
                'profile': profile,
                'last_seen': datetime.utcnow(),
                'sid': request.sid
            }
            
            # Emit updated online users list to the room
            online_list = [{'user_id': uid, 'profile': info['profile']} 
                          for uid, info in online_users.get(room, {}).items()]
            emit('online_users', {'users': online_list}, room=room)
            
            emit('user_joined', {
                'user_id': user_id,
                'profile': profile,
                'timestamp': datetime.utcnow().isoformat()
            }, room=room)
    
    @socketio.on('leave_room')
    def on_leave_room(data):
        """Handle user leaving a room"""
        room = data.get('room')
        user_id = data.get('user_id')
        
        if room and user_id:
            leave_room(room)
            
            # Remove from online users
            if room in online_users and user_id in online_users[room]:
                del online_users[room][user_id]
                
                # Emit updated online users list
                online_list = [{'user_id': uid, 'profile': info['profile']} 
                              for uid, info in online_users.get(room, {}).items()]
                emit('online_users', {'users': online_list}, room=room)
                emit('user_left', {'user_id': user_id, 'timestamp': datetime.utcnow().isoformat()}, room=room)
    
    @socketio.on('get_online_users')
    def on_get_online_users(data):
        """Get list of online users in a room"""
        room = data.get('room')
        if room:
            online_list = [{'user_id': uid, 'profile': info['profile']} 
                          for uid, info in online_users.get(room, {}).items()]
            emit('online_users', {'users': online_list})
    
    @socketio.on('message')
    def handle_message(data):
        """Handle real-time messages"""
        room = data.get('room')
        user_id = data.get('user_id')
        message = data.get('message')
        
        if room and message:
            emit('new_message', {
                'user_id': user_id,
                'message': message,
                'timestamp': datetime.utcnow().isoformat()
            }, room=room)
    
    @socketio.on('clear_board')
    def handle_clear_board(data):
        """Handle clearing the whiteboard"""
        room = data.get('room')
        user_id = data.get('user_id')
        
        if room and room.startswith('whiteboard:'):
            wb_id = room.split(':', 1)[1]
            # Verify permissions (creator or can_draw)
            db = Database()
            wb = db.find_one('whiteboards', {'_id': ObjectId(wb_id)})
            if wb:
                # Check if creator or has draw permission
                is_creator = str(wb.get('created_by')) == str(user_id)
                can_draw = str(user_id) in [str(x) for x in wb.get('can_draw', [])]
                
                if is_creator or can_draw:
                    # Clear drawing data in DB
                    db.update_one('whiteboards', {'_id': ObjectId(wb_id)}, {'drawing_data': []})
                    emit('board_cleared', {'user_id': user_id}, room=room)

    @socketio.on('whiteboard_draw')
    def handle_whiteboard_draw(data):
        """Handle whiteboard drawing"""
        room = data.get('room')
        drawing_data = data.get('drawing_data')
        user_id = data.get('user_id')
        
        if room and drawing_data:
            # enforce draw permissions if room is a whiteboard session (format: 'whiteboard:<id>')
            allowed = True
            try:
                if room.startswith('whiteboard:'):
                    wb_id = room.split(':', 1)[1]
                    from app.services import Database
                    db = Database()
                    wb = db.find_one('whiteboards', {'_id': ObjectId(wb_id)})
                    if wb and wb.get('can_draw'):
                        # can_draw contains ObjectIds
                        ids = [str(x) for x in wb.get('can_draw', [])]
                        allowed = str(user_id) in ids
            except Exception:
                allowed = True
            if allowed:
                emit('draw_update', {
                    'user_id': user_id,
                    'drawing_data': drawing_data,
                    'timestamp': datetime.utcnow().isoformat()
                }, room=room, skip_sid=request.sid)
                # Persist drawing to the whiteboard document
                try:
                    if room.startswith('whiteboard:'):
                        wb_id = room.split(':', 1)[1]
                        db.push_to_array('whiteboards', {'_id': ObjectId(wb_id)}, 'drawing_data', drawing_data)
                except Exception:
                    pass
    
    @socketio.on('typing_indicator')
    def handle_typing(data):
        """Handle typing indicator"""
        room = data.get('room')
        user_id = data.get('user_id')
        is_typing = data.get('is_typing', False)
        
        if room:
            emit('user_typing', {
                'user_id': user_id,
                'is_typing': is_typing
            }, room=room, skip_sid=request.sid)


    @socketio.on('whiteboard_audio')
    def handle_whiteboard_audio(data):
        """Broadcast base64 audio chunks to room; clients will assemble/play them."""
        room = data.get('room')
        user_id = data.get('user_id')
        audio_b64 = data.get('audio_b64')
        if room and audio_b64:
            # Enforce speak permissions similar to draw
            allowed = True
            try:
                if room.startswith('whiteboard:'):
                    wb_id = room.split(':', 1)[1]
                    db = Database()
                    wb = db.find_one('whiteboards', {'_id': ObjectId(wb_id)})
                    if wb and wb.get('can_speak'):
                        ids = [str(x) for x in wb.get('can_speak', [])]
                        allowed = str(user_id) in ids
            except Exception:
                allowed = True
            if allowed:
                emit('audio_clip', {
                    'user_id': user_id,
                    'audio_b64': audio_b64,
                    'timestamp': datetime.utcnow().isoformat()
                }, room=room, skip_sid=request.sid)


    @socketio.on('raise_hand')
    def handle_raise_hand(data):
        room = data.get('room')
        user_id = data.get('user_id')
        if not room or not room.startswith('whiteboard:'):
            return
        wb_id = room.split(':', 1)[1]
        db = Database()
        try:
            db.push_to_array('whiteboards', {'_id': ObjectId(wb_id)}, 'raised_hands', ObjectId(user_id))
            user_doc = db.find_one('users', {'_id': ObjectId(user_id)})
            profile = {'id': str(user_doc['_id']), 'full_name': user_doc.get('full_name', ''), 'avatar_url': user_doc.get('avatar_url', ''), 'username': user_doc.get('username', '')} if user_doc else None
            emit('hand_raised', {'user_id': user_id, 'profile': profile}, room=room)
        except Exception:
            pass

    @socketio.on('clear_hand')
    def handle_clear_hand(data):
        room = data.get('room')
        user_id = data.get('user_id')
        if not room or not room.startswith('whiteboard:'):
            return
        wb_id = room.split(':', 1)[1]
        db = Database()
        try:
            db.pull_from_array('whiteboards', {'_id': ObjectId(wb_id)}, 'raised_hands', ObjectId(user_id))
            emit('hand_cleared', {'user_id': user_id}, room=room)
        except Exception:
            pass

    # WebRTC signaling - track users in each call room
    webrtc_rooms = {}  # {room_id: set(user_ids)}
    
    @socketio.on('webrtc_join')
    def handle_webrtc_join(data):
        room = data.get('room')
        user_id = data.get('user_id')
        if room and user_id:
            # Initialize room if needed
            if room not in webrtc_rooms:
                webrtc_rooms[room] = set()
            
            # Get list of existing users BEFORE adding the new user
            existing_users = list(webrtc_rooms[room])
            
            # Add user to the room
            webrtc_rooms[room].add(user_id)
            
            # Send the list of existing users to the joining user
            emit('webrtc_existing_users', {'users': existing_users})
            
            # Notify existing users that a new user joined
            emit('webrtc_user_joined', {'user_id': user_id}, room=room, skip_sid=request.sid)

    @socketio.on('webrtc_leave')
    def handle_webrtc_leave(data):
        room = data.get('room')
        user_id = data.get('user_id')
        if room and user_id:
            # Remove user from room tracking
            if room in webrtc_rooms:
                webrtc_rooms[room].discard(user_id)
                # Clean up empty rooms
                if not webrtc_rooms[room]:
                    del webrtc_rooms[room]
            emit('webrtc_user_left', {'user_id': user_id}, room=room, skip_sid=request.sid)

    @socketio.on('webrtc_offer')
    def handle_webrtc_offer(data):
        room = data.get('room')
        offer = data.get('offer')
        sender = data.get('sender')
        target = data.get('target')
        
        if not room or not offer or not target:
            return
            
        # Send only to the specific target user
        # We need to find the socket ID for the target user
        # For now, we'll broadcast to the room but clients will filter by target ID
        # In a production app, you'd map user_ids to socket_ids
        emit('webrtc_offer', {
            'offer': offer, 
            'sender': sender,
            'target': target
        }, room=room, skip_sid=request.sid)

    @socketio.on('webrtc_answer')
    def handle_webrtc_answer(data):
        room = data.get('room')
        answer = data.get('answer')
        sender = data.get('sender')
        target = data.get('target')
        
        if not room or not answer or not target:
            return
            
        emit('webrtc_answer', {
            'answer': answer, 
            'sender': sender,
            'target': target
        }, room=room, skip_sid=request.sid)

    @socketio.on('webrtc_ice')
    def handle_webrtc_ice(data):
        room = data.get('room')
        candidate = data.get('candidate')
        sender = data.get('sender')
        target = data.get('target')
        
        if not room or not candidate or not target:
            return
            
        emit('webrtc_ice', {
            'candidate': candidate, 
            'sender': sender,
            'target': target
        }, room=room, skip_sid=request.sid)


    @socketio.on('grant_draw')
    def handle_grant_draw(data):
        room = data.get('room')
        target_user = data.get('user_id')
        requester = data.get('requester_id')
        if not room or not room.startswith('whiteboard:'):
            return
        wb_id = room.split(':', 1)[1]
        db = Database()
        try:
            wb = db.find_one('whiteboards', {'_id': ObjectId(wb_id)})
            if not wb:
                return
            # only creator can grant
            if str(wb.get('created_by')) != requester:
                return
            current = wb.get('can_draw', [])
            if ObjectId(target_user) not in current:
                current.append(ObjectId(target_user))
                db.update_one('whiteboards', {'_id': wb['_id']}, {'can_draw': current})
                emit('permissions_updated', {'can_draw': [str(x) for x in current]}, room=room)
        except Exception:
            return


    @socketio.on('revoke_draw')
    def handle_revoke_draw(data):
        room = data.get('room')
        target_user = data.get('user_id')
        requester = data.get('requester_id')
        if not room or not room.startswith('whiteboard:'):
            return
        wb_id = room.split(':', 1)[1]
        db = Database()
        try:
            wb = db.find_one('whiteboards', {'_id': ObjectId(wb_id)})
            if not wb:
                return
            if str(wb.get('created_by')) != requester:
                return
            current = wb.get('can_draw', [])
            current = [x for x in current if str(x) != target_user]
            db.update_one('whiteboards', {'_id': wb['_id']}, {'can_draw': current})
            emit('permissions_updated', {'can_draw': [str(x) for x in current]}, room=room)
        except Exception:
            return


    @socketio.on('grant_speak')
    def handle_grant_speak(data):
        room = data.get('room')
        target_user = data.get('user_id')
        requester = data.get('requester_id')
        if not room or not room.startswith('whiteboard:'):
            return
        wb_id = room.split(':', 1)[1]
        db = Database()
        try:
            wb = db.find_one('whiteboards', {'_id': ObjectId(wb_id)})
            if not wb:
                return
            # only creator can grant
            if str(wb.get('created_by')) != requester:
                return
            current = wb.get('can_speak', [])
            if ObjectId(target_user) not in current:
                current.append(ObjectId(target_user))
                db.update_one('whiteboards', {'_id': wb['_id']}, {'can_speak': current})
                emit('permissions_updated', {'can_speak': [str(x) for x in current]}, room=room)
        except Exception:
            return


    @socketio.on('revoke_speak')
    def handle_revoke_speak(data):
        room = data.get('room')
        target_user = data.get('user_id')
        requester = data.get('requester_id')
        if not room or not room.startswith('whiteboard:'):
            return
        wb_id = room.split(':', 1)[1]
        db = Database()
        try:
            wb = db.find_one('whiteboards', {'_id': ObjectId(wb_id)})
            if not wb:
                return
            if str(wb.get('created_by')) != requester:
                return
            current = wb.get('can_speak', [])
            current = [x for x in current if str(x) != target_user]
            db.update_one('whiteboards', {'_id': wb['_id']}, {'can_speak': current})
            emit('permissions_updated', {'can_speak': [str(x) for x in current]}, room=room)
        except Exception:
            return
    
    @socketio.on('leave_room')
    def on_leave_room(data):
        """Handle user leaving a room"""
        room = data.get('room')
        user_id = data.get('user_id')
        
        if room and user_id:
            leave_room(room)
            if user_id in connected_users:
                del connected_users[user_id]
            try:
                if room.startswith('whiteboard:'):
                    wb_id = room.split(':', 1)[1]
                    db = Database()
                    db.pull_from_array('whiteboards', {'_id': ObjectId(wb_id)}, 'participants', ObjectId(user_id))
            except Exception:
                pass
            # Emit with profile if possible
            try:
                user_doc = db.find_one('users', {'_id': ObjectId(user_id)})
                profile = None
                if user_doc:
                    profile = {'id': str(user_doc['_id']), 'full_name': user_doc.get('full_name', ''), 'avatar_url': user_doc.get('avatar_url', ''), 'username': user_doc.get('username', '')}
                emit('user_left', {'user_id': user_id, 'profile': profile, 'timestamp': datetime.utcnow().isoformat()}, room=room)
            except Exception:
                # Fallback to minimal event
                emit('user_left', {'user_id': user_id, 'timestamp': datetime.utcnow().isoformat()}, room=room)

    
    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle user disconnect"""
        print(f'Client disconnected: {request.sid}')
        # Attempt to remove user from any whiteboard participant lists based on connected_users reverse mapping
        try:
            user_ids_to_remove = [u for u, sid in connected_users.items() if sid == request.sid]
            for uid in user_ids_to_remove:
                del connected_users[uid]
                # remove from all whiteboards where user present
                db = Database()
                db.pull_from_array('whiteboards', {'participants': ObjectId(uid)}, 'participants', ObjectId(uid))
                
                # Remove from online_users and notify rooms
                for room, users in list(online_users.items()):
                    if uid in users:
                        del online_users[room][uid]
                        # Emit updated online users list
                        online_list = [{'user_id': u, 'profile': info['profile']} 
                                      for u, info in online_users.get(room, {}).items()]
                        socketio.emit('online_users', {'users': online_list}, room=room)
                        socketio.emit('user_left', {'user_id': uid, 'timestamp': datetime.utcnow().isoformat()}, room=room)
        except Exception as e:
            print(f"Error in disconnect handler: {e}")
            pass
    
    return app, socketio

# Create app instance
if __name__ == '__main__':
    app, socketio = create_app(os.getenv('FLASK_ENV', 'development'))
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
