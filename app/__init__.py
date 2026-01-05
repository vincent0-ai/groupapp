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
import threading
import time
from dotenv import load_dotenv
import asyncio
from app.services.livekit_service import LiveKitService
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri=None
)
load_dotenv()
def create_app(config_name='development'):
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    app.config.from_object(config[config_name])

    # Configure session cookie security
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = not app.config.get('DEBUG', False)

    # Configure CORS and Socket.IO allowed origins from config (avoid '*' in production)
    cors_origins = app.config.get('CORS_ALLOWED_ORIGINS')
    if cors_origins:
        CORS(app, resources={r"/api/*": {"origins": cors_origins}})
    else:
        # Fall back to default CORS (restrictive)
        CORS(app)

    socketio = SocketIO(app, cors_allowed_origins=app.config.get('SOCKETIO_CORS_ALLOWED_ORIGINS'))
    app.socketio = socketio

    # Initialize rate limiter with storage configured from app config
    limiter.storage_uri = app.config['LIMITER_STORAGE_URI']
    limiter.init_app(app)
    limiter.limit(app.config['DEFAULT_RATE_LIMITS'])

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    @app.after_request
    def set_security_headers(response):
        # Common security headers
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('Referrer-Policy', 'no-referrer-when-downgrade')
        # Basic Content-Security-Policy (adjust as needed for your static assets / CDNs)
        if 'Content-Security-Policy' not in response.headers:
            # Allow fonts from self, secure origins and data URIs so icon fonts (FontAwesome, Google fonts, etc.) can load
            # Allow Google accounts for embedded Google Identity frames (gsi/client) used on the auth page
            csp = "default-src 'self'; script-src 'self' 'unsafe-inline' https:; style-src 'self' 'unsafe-inline' https:; font-src 'self' https: data:; img-src 'self' data: https:; connect-src 'self' https: ws: wss:; frame-src https://accounts.google.com;"
            response.headers.setdefault('Content-Security-Policy', csp)
        # HSTS only in non-debug (i.e., production)
        if not app.debug:
            response.headers.setdefault('Strict-Transport-Security', 'max-age=63072000; includeSubDomains; preload')
        return response

    from app.routes.main import main_bp
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
    from app.routes.streaks import streaks_bp
    from app.routes.groups_leaderboard import leaderboard_bp
    from app.routes.seasons import seasons_bp
    
    app.register_blueprint(main_bp)
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
    app.register_blueprint(streaks_bp)
    app.register_blueprint(leaderboard_bp)
    app.register_blueprint(seasons_bp)
    
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

    @app.route('/reset-password')
    def reset_password_page():
        """Serve password reset page"""
        return render_template('reset_password.html')
    
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

    @app.route('/seasons')
    def seasons_page():
        """Serve seasons / Hall of Progress"""
        return render_template('seasons.html')

    @app.route('/test/footer')
    def test_footer():
        """Dev-only: preview footer at different mobile widths"""
        return render_template('test_footer.html')
    
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
    # Connection tracking: user_id -> set(sids) and sid -> user_id
    connected_users = {}  # {user_id: set(sids)}
    sid_to_user = {}      # {sid: user_id}
    online_users = {}  # Track online users per room {room: {user_id: {profile, last_seen}}}
    room_timers = {} # {room_id: {'start_time': datetime, 'warned': boolean}}
    # Locks for shared state accessed by socket handlers and background threads
    import threading
    connected_users_lock = threading.Lock()
    room_timers_lock = threading.Lock()
    online_users_lock = threading.Lock()

    # Expose internals on app for testing and admin hooks
    app.connected_users = connected_users
    app.sid_to_user = sid_to_user
    app.online_users = online_users
    app.room_timers = room_timers
    app._connected_users_lock = connected_users_lock
    app._room_timers_lock = room_timers_lock
    app._online_users_lock = online_users_lock
    
    # Import necessary modules for LiveKit integration
    import time
    import asyncio
    from app.services.livekit_service import LiveKitService, VideoGrants
    from app.utils.permissions import compute_permissions

    # Create a single LiveKit admin client for the process
    livekit_service = LiveKitService()
    def get_livekit():
        return livekit_service
    # expose accessor after it's defined
    app.get_livekit = get_livekit

    def _is_valid_object_id(oid):
        try:
            return bool(oid) and ObjectId.is_valid(str(oid))
        except Exception:
            return False

    def _run_async_coro(coro):
        """Wrapper to run a coroutine safely in a background thread."""
        try:
            asyncio.run(coro)
        except Exception as e:
            print(f"Error running coro in background: {e}")

    def check_session_timers(app, socketio):
        with app.app_context():
            livekit_service = get_livekit()

            while True:
                now = datetime.utcnow()
                try:
                    # Make a copy of items to avoid runtime errors during iteration
                    with room_timers_lock:
                        timers_copy = list(room_timers.items())
                    for room, timer_data in timers_copy:
                        start_time = timer_data['start_time']
                        session_duration = (now - start_time).total_seconds()

                        if session_duration > 1200:
                            wb_id = room.split(':', 1)[1]
                            try:
                                db = Database()
                                db.update_one('whiteboards', {'_id': ObjectId(wb_id)}, {'is_active': False, 'ended_at': now})
                            except Exception as e:
                                print(f"Failed to mark whiteboard {wb_id} ended: {e}")

                            # Notify connected clients and attempt to delete the underlying LiveKit room
                            socketio.emit('session_ended', {'session_id': wb_id, 'reason': 'Time limit reached.'}, room=room)
                            try:
                                # Run deletion in background to avoid blocking the timer thread
                                socketio.start_background_task(_run_async_coro, livekit_service.lkapi.room.delete_room(room=room))
                            except Exception as e:
                                print(f"Failed to delete LiveKit room {room}: {e}")

                            if room in room_timers:
                                del room_timers[room]
                        
                        # Broadcast 15-minute warning
                        elif session_duration > 900 and not timer_data.get('warned'): # 15 minutes
                            print(f"Session warning for room {room}.")
                            remaining = 1200 - session_duration
                            socketio.emit('session_warning', {'session_id': room.split(':', 1)[1], 'minutes_remaining': 5}, room=room)
                            with room_timers_lock:
                                if room in room_timers:
                                    room_timers[room]['warned'] = True
                except Exception as e:
                    print(f"Error in session timer thread: {e}")
                
                time.sleep(30) # Check every 30 seconds

    @socketio.on('connect')
    def handle_connect():
        # Require a JWT token on connection (via query param `token` or Authorization header)
        token = request.args.get('token')
        if not token:
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                token = auth_header.split(' ', 1)[1]
        if not token:
            print('Socket connect denied: missing token')
            try:
                from flask_socketio import disconnect
                disconnect()
            except Exception:
                pass
            return

        try:
            import jwt
            payload = jwt.decode(token, current_app.config['JWT_SECRET_KEY'], algorithms=[current_app.config['JWT_ALGORITHM']])
            uid = str(payload['user_id'])
        except Exception as e:
            print(f'Socket connect denied: token invalid: {e}')
            try:
                from flask_socketio import disconnect
                disconnect()
            except Exception:
                pass
            return

        # Track connection
        with connected_users_lock:
            s = connected_users.get(uid)
            if not s:
                s = set()
                connected_users[uid] = s
            s.add(request.sid)
            sid_to_user[request.sid] = uid

        emit('connect_response', {'data': 'Connected', 'user_id': uid})

    @socketio.on('join_room')
    def on_join_room(data):
        room = data.get('room')

        # Use authenticated user id derived from connection (do not trust client-supplied user_id)
        uid = sid_to_user.get(request.sid)
        if not room or not uid:
            return

        # Handle whiteboard session bookkeeping in a try/except
        if room.startswith('whiteboard:'):
            try:
                wb_id = room.split(':', 1)[1]
                if _is_valid_object_id(wb_id):
                    db = Database()
                    with room_timers_lock:
                        if room not in room_timers:
                            room_timers[room] = {'start_time': datetime.utcnow(), 'warned': False}
                            print(f"Started session timer for room: {room}")

                    # Only push participant if uid looks like a valid ObjectId
                    if _is_valid_object_id(uid):
                        db.push_to_array('whiteboards', {'_id': ObjectId(wb_id)}, 'participants', ObjectId(uid))
            except Exception as e:
                print(f"Error joining whiteboard: {e}")
                pass

        # Join the room (handle transient Engine.IO mapping errors)
        try:
            join_room(room)
        except KeyError as e:
            print(f"Warning: could not join room {room} for sid {request.sid}: {e}")
            emit('error', {'message': 'Could not join room due to transient connection error'})

        # Include basic user profile info
        try:
            db = Database()
            user_doc = db.find_one('users', {'_id': ObjectId(uid)})
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
        with online_users_lock:
            if room not in online_users:
                online_users[room] = {}
            online_users[room][uid] = {
                'profile': profile,
                'last_seen': datetime.utcnow(),
                'sid': request.sid
            }

        # Emit updated online users list to the room
        online_list = [{'user_id': u, 'profile': info['profile']} 
                      for u, info in online_users.get(room, {}).items()]
        emit('online_users', {'users': online_list}, room=room)
        
        emit('user_joined', {
            'user_id': uid,
            'profile': profile,
            'timestamp': datetime.utcnow().isoformat()
        }, room=room)
    
    
    
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
        message = data.get('message')
        uid = sid_to_user.get(request.sid)
        if room and message and uid:
            # Escape message content to prevent XSS when clients render it
            from html import escape as _escape
            safe_message = _escape(str(message))
            emit('new_message', {
                'user_id': uid,
                'message': safe_message,
                'timestamp': datetime.utcnow().isoformat()
            }, room=room)
    
    @socketio.on('clear_board')
    def handle_clear_board(data):
        """Handle clearing the whiteboard"""
        room = data.get('room')
        uid = sid_to_user.get(request.sid)
        
        if room and room.startswith('whiteboard:') and uid:
            wb_id = room.split(':', 1)[1]
            if not _is_valid_object_id(wb_id):
                print(f"clear_board called with invalid wb_id: '{wb_id}'")
                return
            # Verify permissions (creator or can_draw)
            db = Database()
            wb = db.find_one('whiteboards', {'_id': ObjectId(wb_id)})
            if wb:
                # Check draw permission via centralized helper
                perms = compute_permissions(wb, uid)
                if perms.get('can_draw'):
                    # Clear drawing data in DB
                    db.update_one('whiteboards', {'_id': ObjectId(wb_id)}, {'drawing_data': []})
                    emit('board_cleared', {'user_id': uid}, room=room)

    @socketio.on('whiteboard_draw')
    def handle_whiteboard_draw(data):
        """Handle whiteboard drawing"""
        room = data.get('room')
        drawing_data = data.get('drawing_data')
        uid = sid_to_user.get(request.sid)
        
        if room and drawing_data and uid:
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
                    if wb:
                        perms = compute_permissions(wb, uid)
                        allowed = perms.get('can_draw', True)
            except Exception:
                allowed = True
            if allowed:
                emit('draw_update', {
                    'user_id': uid,
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

    @socketio.on('undo_action')
    def handle_undo_action(data):
        """Handle undo of the last stroke"""
        room = data.get('room')
        uid = sid_to_user.get(request.sid)
        if room and room.startswith('whiteboard:') and uid:
            wb_id = room.split(':', 1)[1]
            if not _is_valid_object_id(wb_id):
                print(f"undo_action called with invalid wb_id: '{wb_id}'")
                return
            from app.services import Database
            db = Database()
            wb = db.find_one('whiteboards', {'_id': ObjectId(wb_id)})
            if wb:
                perms = compute_permissions(wb, uid)
                if perms.get('can_draw'):
                    try:
                        # remove last element from the drawing_data array
                        db.update_one('whiteboards', {'_id': ObjectId(wb_id)}, {'$pop': {'drawing_data': 1}})
                    except Exception:
                        pass
                    emit('undo_action', {'user_id': uid}, room=room, skip_sid=request.sid)
    
    @socketio.on('typing_indicator')
    def handle_typing(data):
        """Handle typing indicator"""
        room = data.get('room')
        uid = sid_to_user.get(request.sid)
        is_typing = data.get('is_typing', False)
        
        if room and uid:
            emit('user_typing', {
                'user_id': uid,
                'is_typing': is_typing
            }, room=room, skip_sid=request.sid)

    @socketio.on('raise_hand')
    def handle_raise_hand(data):
        room = data.get('room')
        uid = sid_to_user.get(request.sid)
        if not room or not room.startswith('whiteboard:') or not uid:
            return
        wb_id = room.split(':', 1)[1]
        if not _is_valid_object_id(wb_id):
            print(f"raise_hand called with invalid wb_id: '{wb_id}'")
            return
        db = Database()
        try:
            db.push_to_array('whiteboards', {'_id': ObjectId(wb_id)}, 'raised_hands', ObjectId(uid))
            user_doc = db.find_one('users', {'_id': ObjectId(uid)})
            profile = {'id': str(user_doc['_id']), 'full_name': user_doc.get('full_name', ''), 'avatar_url': user_doc.get('avatar_url', ''), 'username': user_doc.get('username', '')} if user_doc else None
            emit('hand_raised', {'user_id': uid, 'profile': profile}, room=room)
        except Exception:
            pass

    @socketio.on('clear_hand')
    def handle_clear_hand(data):
        room = data.get('room')
        uid = sid_to_user.get(request.sid)
        if not room or not room.startswith('whiteboard:') or not uid:
            return
        wb_id = room.split(':', 1)[1]
        if not _is_valid_object_id(wb_id):
            print(f"clear_hand called with invalid wb_id: '{wb_id}'")
            return
        db = Database()
        try:
            db.pull_from_array('whiteboards', {'_id': ObjectId(wb_id)}, 'raised_hands', ObjectId(uid))
            emit('hand_cleared', {'user_id': uid}, room=room)
        except Exception:
            pass

    # Simplified handlers for video state, LiveKit handles the media part
    @socketio.on('video_join')
    def handle_video_join(data):
        """User indicates they are joining the video/media session."""
        room = data.get('room')
        uid = sid_to_user.get(request.sid)
        print(f"User {uid} joining video session in room {room}")
        # This is now mostly for app-level logic if needed.
        # Client will fetch token and connect to LiveKit separately.
        emit('video_user_joined', {'user_id': uid}, room=room, skip_sid=request.sid)

    @socketio.on('video_leave')
    def handle_video_leave(data):
        """User indicates they are leaving the video/media session."""
        room = data.get('room')
        uid = sid_to_user.get(request.sid)
        print(f"User {uid} leaving video session in room {room}")
        # This is now mostly for app-level logic if needed.
        emit('video_user_left', {'user_id': uid}, room=room, skip_sid=request.sid)

    async def _update_lk_permissions(wb, target_user_id, room_name):
        """Async helper to update LiveKit participant permissions."""
        perms = compute_permissions(wb, target_user_id)
        can_publish = perms['can_publish']
        try:
            print(f"[_update_lk_permissions] updating LiveKit permissions for {target_user_id} in {room_name} - perms={perms}")
            lk = get_livekit()
            # Use the service helper that converts to the proper SDK permission object
            success, err = await lk.update_participant_permission(room_name, target_user_id, can_publish, True)
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
        requester = sid_to_user.get(request.sid)
        if not room or not room.startswith('whiteboard:') or not requester:
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
        requester = sid_to_user.get(request.sid)
        if not room or not room.startswith('whiteboard:') or not requester:
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
        requester = sid_to_user.get(request.sid)
        if not room or not room.startswith('whiteboard:') or not requester:
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
            socketio.start_background_task(_run_async_coro, _update_lk_permissions(updated_wb, target_user, room))

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
        requester = sid_to_user.get(request.sid)
        if not room or not room.startswith('whiteboard:') or not requester:
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
            socketio.start_background_task(_run_async_coro, _update_lk_permissions(updated_wb, target_user, room))

            emit('permissions_updated', {
                'can_draw': [str(x) for x in updated_wb.get('can_draw', [])],
                'can_speak': [str(x) for x in updated_wb.get('can_speak', [])],
                'can_share_screen': [str(x) for x in updated_wb.get('can_share_screen', [])]
            }, room=room)
            # If the target user is currently connected, send a direct event to force them to stop publishing
            try:
                with connected_users_lock:
                    sids = connected_users.get(str(target_user), set()).copy()
                for sid in sids:
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
        requester = sid_to_user.get(request.sid)
        if not room or not room.startswith('whiteboard:') or not requester:
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
            socketio.start_background_task(_run_async_coro, _update_lk_permissions(updated_wb, target_user, room))

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
        requester = sid_to_user.get(request.sid)
        if not room or not room.startswith('whiteboard:') or not requester:
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
            socketio.start_background_task(_run_async_coro, _update_lk_permissions(updated_wb, target_user, room))

            emit('permissions_updated', {
                'can_draw': [str(x) for x in updated_wb.get('can_draw', [])],
                'can_speak': [str(x) for x in updated_wb.get('can_speak', [])],
                'can_share_screen': [str(x) for x in updated_wb.get('can_share_screen', [])]
            }, room=room)
            # Notify target participant to stop screen sharing if connected
            try:
                with connected_users_lock:
                    sids = connected_users.get(str(target_user), set()).copy()
                for sid in sids:
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
            # Remove only this sid for the user
            uid = str(user_id)
            with connected_users_lock:
                s = connected_users.get(uid)
                if s:
                    s.discard(request.sid)
                    if not s:
                        del connected_users[uid]
                if request.sid in sid_to_user:
                    del sid_to_user[request.sid]
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
            uid = sid_to_user.get(request.sid)
            if uid:
                # Remove mapping
                with connected_users_lock:
                    s = connected_users.get(uid)
                    if s:
                        s.discard(request.sid)
                        if not s:
                            del connected_users[uid]
                    if request.sid in sid_to_user:
                        del sid_to_user[request.sid]

                # remove from all whiteboards where user present
                db = Database()
                user_obj_id = ObjectId(uid)
                whiteboards = db.find('whiteboards', {'participants': user_obj_id})
                for wb in whiteboards:
                    room_name = f"whiteboard:{str(wb['_id'])}"
                    # Pull from participants array
                    db.pull_from_array('whiteboards', {'_id': wb['_id']}, 'participants', user_obj_id)
                    # Handle online_users tracking
                    with online_users_lock:
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

    def check_group_streaks(app):
        """Background checker to update group streaks daily (or every configured interval)."""
        with app.app_context():
            from datetime import timedelta
            while True:
                try:
                    now = datetime.utcnow()
                    start_window = now - timedelta(days=1)
                    db = Database()
                    groups = list(db.find('groups', {}))
                    for group in groups:
                        try:
                            group_id = group['_id']
                            members = group.get('members', [])
                            total_members = len(members)
                            if total_members == 0:
                                continue

                            # Determine threshold
                            gs = db.find_one('group_streaks', {'group_id': group_id})
                            if gs and gs.get('threshold'):
                                threshold = gs['threshold']
                            else:
                                min_percent = app.config.get('GROUP_STREAK_MIN_PERCENT', 0.2)
                                min_abs = app.config.get('GROUP_STREAK_MIN_ABSOLUTE', 2)
                                calc = int(max(1, round(total_members * min_percent)))
                                threshold = max(min_abs, calc)

                            # Compute active users in last 24 hours from messages (and other participation signals in the future)
                            active_user_ids = set()
                            msgs = db.find('messages', {'group_id': group_id, 'created_at': {'$gt': start_window}})
                            for m in msgs:
                                uid = m.get('user_id')
                                if uid:
                                    active_user_ids.add(str(uid))

                            # Potential future signals: competitions participation, insights, etc.
                            active_count = len(active_user_ids)

                            today_str = now.date().isoformat()

                            if active_count >= threshold:
                                # increment or set streak (allow small gaps before considering streak broken)
                                allowed_gap = app.config.get('GROUP_STREAK_MAX_GAP_DAYS', 7)

                                if not gs:
                                    db.insert_one('group_streaks', {
                                        '_id': ObjectId(),
                                        'group_id': group_id,
                                        'streak_count': 1,
                                        'last_active_day': today_str,
                                        'threshold': None,
                                        'min_percent': None,
                                        'created_at': now,
                                        'updated_at': now
                                    })
                                else:
                                    last_day = gs.get('last_active_day')
                                    if last_day == today_str:
                                        # already updated today
                                        pass
                                    else:
                                        # compute days since last active (robust to missing/invalid data)
                                        try:
                                            from datetime import date
                                            last_date = date.fromisoformat(last_day) if last_day else None
                                            days_since = (now.date() - last_date).days if last_date else None
                                        except Exception:
                                            days_since = None

                                        # If we have a valid last_active_day and it's within the allowed gap, increment the streak
                                        if days_since is not None and days_since <= int(allowed_gap):
                                            db.update_one('group_streaks', {'_id': gs['_id']}, {'streak_count': gs.get('streak_count', 0) + 1, 'last_active_day': today_str, 'updated_at': now})
                                        else:
                                            # gap longer than allowed (or unknown last_day) -> reset streak to 1
                                            db.update_one('group_streaks', {'_id': gs['_id']}, {'streak_count': 1, 'last_active_day': today_str, 'updated_at': now})
                            else:
                                # streak may be broken; only reset if the last active day is older than the allowed gap
                                if gs and gs.get('streak_count', 0) > 0:
                                    allowed_gap = app.config.get('GROUP_STREAK_MAX_GAP_DAYS', 7)
                                    last_day = gs.get('last_active_day')
                                    try:
                                        from datetime import date
                                        last_date = date.fromisoformat(last_day) if last_day else None
                                        days_since = (now.date() - last_date).days if last_date else None
                                    except Exception:
                                        days_since = None

                                    # Reset only if the last active day is older than allowed_gap days
                                    if days_since is None or days_since > int(allowed_gap):
                                        db.update_one('group_streaks', {'_id': gs['_id']}, {'streak_count': 0, 'last_active_day': None, 'updated_at': now})

                        except Exception as e:
                            print(f"Error processing group streak for {group.get('_id')}: {e}")
                except Exception as e:
                    print(f"Error in group streak checker: {e}")

                # Sleep until next iteration
                import time
                interval = app.config.get('GROUP_STREAK_CHECK_INTERVAL_SECONDS', 3600)
                time.sleep(interval)

    socketio.start_background_task(target=check_group_streaks, app=app)

    # Production sanity checks
    if not app.config.get('DEBUG', False):
        if not app.config.get('SECRET_KEY') or not app.config.get('JWT_SECRET_KEY'):
            raise RuntimeError("In production, SECRET_KEY and JWT_SECRET_KEY must be set and not use default values.")
        if app.config.get('CORS_ALLOWED_ORIGINS') == '*' or app.config.get('SOCKETIO_CORS_ALLOWED_ORIGINS') == '*':
            raise RuntimeError("In production, CORS origins must be restricted; do not set '*' for origins.")

    return app, socketio

