from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
from config.config import config
from app.services import Database
import os
from datetime import datetime
from bson import ObjectId
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],  # Set default limits in config.py
    storage_uri=None # Set in create_app
)

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

    # Initialize Flask-Limiter
    limiter.init_app(app)
    limiter.limit(app.config['DEFAULT_RATE_LIMITS'])
    limiter.storage_uri = app.config['LIMITER_STORAGE_URI']
    
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
    
    # Serve service worker from root with proper scope header
    @app.route('/service-worker.js')
    def service_worker():
        """Serve service worker from root to allow full scope"""
        response = app.send_static_file('js/service-worker.js')
        response.headers['Service-Worker-Allowed'] = '/'
        response.headers['Content-Type'] = 'application/javascript'
        return response
    
    # Serve manifest from root for PWA
    @app.route('/manifest.json')
    def manifest():
        """Serve manifest from root"""
        return app.send_static_file('manifest.json')
    
    # Page routes (serving templates)

    
    @app.route('/auth')
    def auth_page():
        """Serve auth page"""
        return render_template('auth.html', google_client_id=os.environ.get('GOOGLE_CLIENT_ID'))
    
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
    
    @app.route('/terms')
    def terms_page():
        """Serve terms and conditions page"""
        return render_template('terms.html')
    
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
    room_timers = {} # {room_id: {'start_time': datetime, 'warned': boolean}}
    
    # Import necessary modules for LiveKit integration
    import threading
    import time
    import asyncio
    from app.services.livekit_service import LiveKitService, VideoGrants

    def run_async_from_sync(coro):
        """Helper to run an async function from a sync context."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(coro)

    def _is_valid_object_id(oid):
        """Return True if oid is a valid BSON ObjectId string."""
        try:
            return bool(oid) and ObjectId.is_valid(str(oid))
        except Exception:
            return False

    def check_session_timers(app, socketio):
        """Background thread to enforce session duration limits."""
        with app.app_context():
            livekit_service = LiveKitService()
            
            while True:
                now = datetime.utcnow()
                try:
                    # Make a copy of items to avoid runtime errors during iteration
                    for room, timer_data in list(room_timers.items()):
                        start_time = timer_data['start_time']
                        session_duration = (now - start_time).total_seconds()

                        # Enforce 20-minute hard limit
                        if session_duration > 1200: # 20 minutes
                            print(f"Session limit reached for room {room}. Terminating.")
                            wb_id = room.split(':', 1)[1]
                            # Mark the whiteboard as ended in the DB so clients get correct state
                            try:
                                from app.services import Database
                                from bson import ObjectId
                                db = Database()
                                db.update_one('whiteboards', {'_id': ObjectId(wb_id)}, {'is_active': False, 'ended_at': now})
                            except Exception as e:
                                print(f"Failed to mark whiteboard {wb_id} ended: {e}")

                            # Notify connected clients and attempt to delete the underlying LiveKit room
                            socketio.emit('session_ended', {'session_id': wb_id, 'reason': 'Time limit reached.'}, room=room)
                            try:
                                run_async_from_sync(livekit_service.lkapi.room.delete_room(room=room))
                            except Exception as e:
                                print(f"Failed to delete LiveKit room {room}: {e}")

                            if room in room_timers:
                                del room_timers[room]
                        
                        # Broadcast 15-minute warning
                        elif session_duration > 900 and not timer_data.get('warned'): # 15 minutes
                            print(f"Session warning for room {room}.")
                            remaining = 1200 - session_duration
                            socketio.emit('session_warning', {'session_id': room.split(':', 1)[1], 'minutes_remaining': 5}, room=room)
                            room_timers[room]['warned'] = True
                except Exception as e:
                    print(f"Error in session timer thread: {e}")
                
                time.sleep(30) # Check every 30 seconds

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
                    # Validate whiteboard id before converting
                    if not _is_valid_object_id(wb_id):
                        print(f"Invalid whiteboard id when joining room: '{wb_id}'")
                        emit('error', {'message': 'Invalid session id'})
                        return

                    db = Database()
                    wb = db.find_one('whiteboards', {'_id': ObjectId(wb_id)})
                    if not wb or not wb.get('is_active', True):
                        emit('error', {'message': 'Session has ended'})
                        return

                    # Start session timer on first join
                    if room not in room_timers:
                        room_timers[room] = {'start_time': datetime.utcnow(), 'warned': False}
                        print(f"Started session timer for room: {room}")

                    # Only push participant if user_id looks like a valid ObjectId
                    if _is_valid_object_id(user_id):
                        db.push_to_array('whiteboards', {'_id': ObjectId(wb_id)}, 'participants', ObjectId(user_id))
                except Exception as e:
                    print(f"Error joining whiteboard: {e}")
                    pass

            try:
                join_room(room)
            except KeyError as e:
                # This can happen if the Engine.IO session mapping is lost due to a disconnect.
                print(f"Warning: could not join room {room} for sid {request.sid}: {e}")
                emit('error', {'message': 'Could not join room due to transient connection error'})
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
            if not _is_valid_object_id(wb_id):
                print(f"clear_board called with invalid wb_id: '{wb_id}'")
                return
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
                    if not _is_valid_object_id(wb_id):
                        # invalid id, allow by default but skip permission checks
                        wb = None
                    else:
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
                            if _is_valid_object_id(wb_id):
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

    @socketio.on('raise_hand')
    def handle_raise_hand(data):
        room = data.get('room')
        user_id = data.get('user_id')
        if not room or not room.startswith('whiteboard:'):
            return
        wb_id = room.split(':', 1)[1]
        if not _is_valid_object_id(wb_id):
            print(f"raise_hand called with invalid wb_id: '{wb_id}'")
            return
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
        if not _is_valid_object_id(wb_id):
            print(f"clear_hand called with invalid wb_id: '{wb_id}'")
            return
        db = Database()
        try:
            db.pull_from_array('whiteboards', {'_id': ObjectId(wb_id)}, 'raised_hands', ObjectId(user_id))
            emit('hand_cleared', {'user_id': user_id}, room=room)
        except Exception:
            pass

    # Simplified handlers for video state, LiveKit handles the media part
    @socketio.on('video_join')
    def handle_video_join(data):
        """User indicates they are joining the video/media session."""
        room = data.get('room')
        user_id = data.get('user_id')
        print(f"User {user_id} joining video session in room {room}")
        # This is now mostly for app-level logic if needed.
        # Client will fetch token and connect to LiveKit separately.
        emit('video_user_joined', {'user_id': user_id}, room=room, skip_sid=request.sid)

    @socketio.on('video_leave')
    def handle_video_leave(data):
        """User indicates they are leaving the video/media session."""
        room = data.get('room')
        user_id = data.get('user_id')
        print(f"User {user_id} leaving video session in room {room}")
        # This is now mostly for app-level logic if needed.
        emit('video_user_left', {'user_id': user_id}, room=room, skip_sid=request.sid)

    async def _update_lk_permissions(wb, target_user_id, room_name):
        """Async helper to update LiveKit participant permissions."""
        is_creator = str(wb.get('created_by')) == target_user_id
        can_speak = is_creator or target_user_id in [str(uid) for uid in wb.get('can_speak', [])]
        can_share = is_creator or target_user_id in [str(uid) for uid in wb.get('can_share_screen', [])]

        can_publish = bool(can_speak or can_share)
        try:
            print(f"[_update_lk_permissions] updating LiveKit permissions for {target_user_id} in {room_name} - is_creator={is_creator} can_speak={can_speak} can_share={can_share} can_publish={can_publish}")
            livekit_service = LiveKitService()
            # Use the service helper that converts to the proper SDK permission object
            success, err = await livekit_service.update_participant_permission(room_name, target_user_id, can_publish, True)
            if not success:
                print(f"LiveKit permission update returned error for {target_user_id} in {room_name}: {err}")
            else:
                print(f"LiveKit permission update succeeded for {target_user_id} in {room_name}")
        except Exception as e:
            print(f"Failed to update LiveKit permissions for {target_user_id} in {room_name}: {e}")
            try:
                import traceback
                traceback.print_exc()
            except Exception:
                pass

    @socketio.on('grant_draw')
    def handle_grant_draw(data):
        room = data.get('room')
        target_user = data.get('user_id')
        requester = data.get('requester_id')
        if not room or not room.startswith('whiteboard:'):
            return
        wb_id = room.split(':', 1)[1]
        if not _is_valid_object_id(wb_id):
            print(f"grant_draw called with invalid wb_id: '{wb_id}'")
            return
        db = Database()
        try:
            wb = db.find_one('whiteboards', {'_id': ObjectId(wb_id)})
            if not wb:
                return
            group_id = wb.get('group_id')
            group = db.find_one('groups', {'_id': group_id}) if group_id else None
            is_owner = group and str(group.get('owner')) == requester
            # Allow update if requester is either the session creator OR the group owner
            if str(wb.get('created_by')) != requester and not is_owner:
                return
            current = wb.get('can_draw', [])
            if ObjectId(target_user) not in current:
                current.append(ObjectId(target_user))
                db.update_one('whiteboards', {'_id': wb['_id']}, {'can_draw': current})
            updated_wb = db.find_one('whiteboards', {'_id': ObjectId(wb_id)})
            emit('permissions_updated', {
                'can_draw': [str(x) for x in updated_wb.get('can_draw', [])],
                'can_speak': [str(x) for x in updated_wb.get('can_speak', [])],
                'can_share_screen': [str(x) for x in updated_wb.get('can_share_screen', [])]
            }, room=room)
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
        if not _is_valid_object_id(wb_id):
            print(f"revoke_draw called with invalid wb_id: '{wb_id}'")
            return
        db = Database()
        try:
            wb = db.find_one('whiteboards', {'_id': ObjectId(wb_id)})
            if not wb:
                return
            group_id = wb.get('group_id')
            group = db.find_one('groups', {'_id': group_id}) if group_id else None
            is_owner = group and str(group.get('owner')) == requester
            # Allow update if requester is either the session creator OR the group owner
            if str(wb.get('created_by')) != requester and not is_owner:
                return
            current = wb.get('can_draw', [])
            current = [x for x in current if str(x) != target_user]
            db.update_one('whiteboards', {'_id': wb['_id']}, {'can_draw': current})
            updated_wb = db.find_one('whiteboards', {'_id': ObjectId(wb_id)})
            emit('permissions_updated', {
                'can_draw': [str(x) for x in updated_wb.get('can_draw', [])],
                'can_speak': [str(x) for x in updated_wb.get('can_speak', [])],
                'can_share_screen': [str(x) for x in updated_wb.get('can_share_screen', [])]
            }, room=room)
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
        if not _is_valid_object_id(wb_id):
            print(f"grant_speak called with invalid wb_id: '{wb_id}'")
            return
        db = Database()
        try:
            wb = db.find_one('whiteboards', {'_id': ObjectId(wb_id)})
            if not wb:
                return
            group_id = wb.get('group_id')
            group = db.find_one('groups', {'_id': group_id}) if group_id else None
            is_owner = group and str(group.get('owner')) == requester
            # Allow update if requester is either the session creator OR the group owner
            if str(wb.get('created_by')) != requester and not is_owner:
                return
            current = wb.get('can_speak', [])
            if ObjectId(target_user) not in current:
                current.append(ObjectId(target_user))
                db.update_one('whiteboards', {'_id': wb['_id']}, {'can_speak': current})
            
            # Update LiveKit permissions
            updated_wb = db.find_one('whiteboards', {'_id': ObjectId(wb_id)})
            run_async_from_sync(_update_lk_permissions(updated_wb, target_user, room))

            emit('permissions_updated', {
                'can_draw': [str(x) for x in updated_wb.get('can_draw', [])],
                'can_speak': [str(x) for x in updated_wb.get('can_speak', [])],
                'can_share_screen': [str(x) for x in updated_wb.get('can_share_screen', [])]
            }, room=room)
        except Exception as e:
            print(f"Error in grant_speak: {e}")
            return


    @socketio.on('revoke_speak')
    def handle_revoke_speak(data):
        room = data.get('room')
        target_user = data.get('user_id')
        requester = data.get('requester_id')
        if not room or not room.startswith('whiteboard:'):
            return
        wb_id = room.split(':', 1)[1]
        if not _is_valid_object_id(wb_id):
            print(f"revoke_speak called with invalid wb_id: '{wb_id}'")
            return
        db = Database()
        try:
            wb = db.find_one('whiteboards', {'_id': ObjectId(wb_id)})
            if not wb:
                return
            group_id = wb.get('group_id')
            group = db.find_one('groups', {'_id': group_id}) if group_id else None
            is_owner = group and str(group.get('owner')) == requester
            # Allow update if requester is either the session creator OR the group owner
            if str(wb.get('created_by')) != requester and not is_owner:
                return
            current_speak = wb.get('can_speak', [])
            current_speak = [x for x in current_speak if str(x) != target_user]
            db.update_one('whiteboards', {'_id': wb['_id']}, {'can_speak': current_speak})

            # Update LiveKit permissions
            updated_wb = db.find_one('whiteboards', {'_id': ObjectId(wb_id)})
            run_async_from_sync(_update_lk_permissions(updated_wb, target_user, room))

            emit('permissions_updated', {
                'can_draw': [str(x) for x in updated_wb.get('can_draw', [])],
                'can_speak': [str(x) for x in updated_wb.get('can_speak', [])],
                'can_share_screen': [str(x) for x in updated_wb.get('can_share_screen', [])]
            }, room=room)
            # If the target user is currently connected, send a direct event to force them to stop publishing
            try:
                sid = connected_users.get(str(target_user))
                if sid:
                    socketio.emit('force_mute', {'reason': 'Your microphone has been disabled by the session moderator.'}, to=sid)
            except Exception:
                pass
        except Exception as e:
            print(f"Error in revoke_speak: {e}")
            return


    @socketio.on('grant_screen_share')
    def handle_grant_screen_share(data):
        room = data.get('room')
        target_user = data.get('user_id')
        requester = data.get('requester_id')
        if not room or not room.startswith('whiteboard:'):
            return
        wb_id = room.split(':', 1)[1]
        if not _is_valid_object_id(wb_id):
            print(f"grant_screen_share called with invalid wb_id: '{wb_id}'")
            return
        db = Database()
        try:
            wb = db.find_one('whiteboards', {'_id': ObjectId(wb_id)})
            if not wb:
                return
            if str(wb.get('created_by')) != requester:
                return
            current = wb.get('can_share_screen', [])
            if ObjectId(target_user) not in current:
                current.append(ObjectId(target_user))
                db.update_one('whiteboards', {'_id': wb['_id']}, {'can_share_screen': current})

            # Update LiveKit permissions
            updated_wb = db.find_one('whiteboards', {'_id': ObjectId(wb_id)})
            run_async_from_sync(_update_lk_permissions(updated_wb, target_user, room))

            emit('permissions_updated', {
                'can_draw': [str(x) for x in updated_wb.get('can_draw', [])],
                'can_speak': [str(x) for x in updated_wb.get('can_speak', [])],
                'can_share_screen': [str(x) for x in updated_wb.get('can_share_screen', [])]
            }, room=room)
        except Exception as e:
            print(f"Error in grant_screen_share: {e}")
            return


    @socketio.on('revoke_screen_share')
    def handle_revoke_screen_share(data):
        room = data.get('room')
        target_user = data.get('user_id')
        requester = data.get('requester_id')
        if not room or not room.startswith('whiteboard:'):
            return
        wb_id = room.split(':', 1)[1]
        if not _is_valid_object_id(wb_id):
            print(f"revoke_screen_share called with invalid wb_id: '{wb_id}'")
            return
        db = Database()
        try:
            wb = db.find_one('whiteboards', {'_id': ObjectId(wb_id)})
            if not wb:
                return
            if str(wb.get('created_by')) != requester:
                return
            current = wb.get('can_share_screen', [])
            current = [x for x in current if str(x) != target_user]
            db.update_one('whiteboards', {'_id': wb['_id']}, {'can_share_screen': current})

            # Update LiveKit permissions
            updated_wb = db.find_one('whiteboards', {'_id': ObjectId(wb_id)})
            run_async_from_sync(_update_lk_permissions(updated_wb, target_user, room))

            emit('permissions_updated', {
                'can_draw': [str(x) for x in updated_wb.get('can_draw', [])],
                'can_speak': [str(x) for x in updated_wb.get('can_speak', [])],
                'can_share_screen': [str(x) for x in updated_wb.get('can_share_screen', [])]
            }, room=room)
            # Notify target participant to stop screen sharing if connected
            try:
                sid = connected_users.get(str(target_user))
                if sid:
                    socketio.emit('force_stop_screen', {'reason': 'Screen sharing has been disabled by the session moderator.'}, to=sid)
            except Exception:
                pass
        except Exception as e:
            print(f"Error in revoke_screen_share: {e}")
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
                if uid in connected_users:
                    del connected_users[uid]
                # remove from all whiteboards where user present
                db = Database()
                # Find all whiteboards the user is a participant in
                user_obj_id = ObjectId(uid)
                whiteboards = db.find('whiteboards', {'participants': user_obj_id})
                for wb in whiteboards:
                    room_name = f"whiteboard:{str(wb['_id'])}"
                    # Pull from participants array
                    db.pull_from_array('whiteboards', {'_id': wb['_id']}, 'participants', user_obj_id)
                    # Handle online_users tracking
                    if room_name in online_users and uid in online_users[room_name]:
                        del online_users[room_name][uid]
                        online_list = [{'user_id': u, 'profile': info['profile']} 
                                      for u, info in online_users.get(room_name, {}).items()]
                        socketio.emit('online_users', {'users': online_list}, room=room_name)
                        socketio.emit('user_left', {'user_id': uid, 'timestamp': datetime.utcnow().isoformat()}, room=room_name)
        except Exception as e:
            print(f"Error in disconnect handler: {e}")
            pass
    
    # Start the background task for session timers
    socketio.start_background_task(target=check_session_timers, app=app, socketio=socketio)
    
    return app, socketio

# Create app instance
if __name__ == '__main__':
    app, socketio = create_app(os.getenv('FLASK_ENV', 'development'))
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)

