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
import asyncio

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri=None
)

def create_app(config_name='development'):
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    app.config.from_object(config[config_name])

    CORS(app, resources={r"/api/*": {"origins": "*"}})
    socketio = SocketIO(app, cors_allowed_origins="*")
    app.socketio = socketio

    limiter.init_app(app)
    limiter.limit(app.config['DEFAULT_RATE_LIMITS'])
    limiter.storage_uri = app.config['LIMITER_STORAGE_URI']

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

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
    from app.routes.main import main_bp

    for bp in [
        auth_bp, groups_bp, messages_bp, competitions_bp,
        files_bp, users_bp, whiteboards_bp, admin_bp,
        notifications_bp, dm_bp, main_bp
    ]:
        app.register_blueprint(bp)

    connected_users = {}     # {user_id: sid}
    online_users = {}        # {room: {user_id: {...}}}
    room_timers = {}
    room_timers_lock = threading.Lock()

    from app.services.livekit_service import LiveKitService

    livekit_service = LiveKitService()
    livekit_service.init_app(app)

    def run_async_from_sync(coro):
        socketio.start_background_task(asyncio.run, coro)

    def _is_valid_object_id(oid):
        try:
            return bool(oid) and ObjectId.is_valid(str(oid))
        except Exception:
            return False

    def check_session_timers(app, socketio):
        with app.app_context():
            while True:
                now = datetime.utcnow()
                with room_timers_lock:
                    for room, timer in list(room_timers.items()):
                        elapsed = (now - timer['start_time']).total_seconds()

                        if elapsed > 1200:
                            wb_id = room.split(':', 1)[1]
                            try:
                                db = Database()
                                db.update_one(
                                    'whiteboards',
                                    {'_id': ObjectId(wb_id)},
                                    {'is_active': False, 'ended_at': now}
                                )
                            except Exception:
                                pass

                            socketio.emit(
                                'session_ended',
                                {'session_id': wb_id, 'reason': 'Time limit reached'},
                                room=room
                            )

                            run_async_from_sync(
                                livekit_service.lkapi.room.delete_room(room=room)
                            )

                            del room_timers[room]

                        elif elapsed > 900 and not timer.get('warned'):
                            socketio.emit(
                                'session_warning',
                                {'session_id': room.split(":")[1], 'minutes_remaining': 5},
                                room=room
                            )
                            timer['warned'] = True

                time.sleep(30)

    @socketio.on('connect')
    def handle_connect():
        emit('connect_response', {'data': 'Connected'})

    @socketio.on('join_room')
    def on_join_room(data):
        room = data.get('room')
        user_id = data.get('user_id')

        if not room or not user_id:
            return

        join_room(room)
        connected_users[user_id] = request.sid

        if room.startswith('whiteboard:'):
            wb_id = room.split(':', 1)[1]
            if _is_valid_object_id(wb_id):
                db = Database()
                with room_timers_lock:
                    if room not in room_timers:
                        room_timers[room] = {'start_time': datetime.utcnow(), 'warned': False}
                try:
                    db.push_to_array(
                        'whiteboards',
                        {'_id': ObjectId(wb_id)},
                        'participants',
                        ObjectId(user_id)
                    )
                except Exception:
                    pass

        online_users.setdefault(room, {})[user_id] = {
            'sid': request.sid,
            'last_seen': datetime.utcnow()
        }

        emit('user_joined', {'user_id': user_id}, room=room)

    @socketio.on('leave_room')
    def on_leave_room(data):
        room = data.get('room')
        user_id = data.get('user_id')

        if not room or not user_id:
            return

        leave_room(room)
        connected_users.pop(user_id, None)

        if room in online_users:
            online_users[room].pop(user_id, None)

        if room.startswith('whiteboard:'):
            wb_id = room.split(':', 1)[1]
            if _is_valid_object_id(wb_id):
                try:
                    db = Database()
                    db.pull_from_array(
                        'whiteboards',
                        {'_id': ObjectId(wb_id)},
                        'participants',
                        ObjectId(user_id)
                    )
                except Exception:
                    pass

        emit('user_left', {'user_id': user_id}, room=room)

    @socketio.on('disconnect')
    def handle_disconnect():
        sid = request.sid
        stale_users = [u for u, s in connected_users.items() if s == sid]

        for user_id in stale_users:
            connected_users.pop(user_id, None)
            for room, users in online_users.items():
                if user_id in users:
                    users.pop(user_id)
                    socketio.emit('user_left', {'user_id': user_id}, room=room)

    socketio.start_background_task(
        target=check_session_timers,
        app=app,
        socketio=socketio
    )

    return app, socketio


if __name__ == '__main__':
    app, socketio = create_app(os.getenv('FLASK_ENV', 'development'))
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
