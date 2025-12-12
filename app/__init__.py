from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
from config.config import config
import os
from datetime import datetime

def create_app(config_name='development'):
    """Create and configure Flask app"""
    
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    
    # Load configuration
    app.config.from_object(config[config_name])
    
    # Initialize extensions
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    socketio = SocketIO(app, cors_allowed_origins="*")
    
    # Create upload folder
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.groups import groups_bp
    from app.routes.messages import messages_bp
    from app.routes.competitions import competitions_bp
    from app.routes.files import files_bp
    from app.routes.users import users_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(groups_bp)
    app.register_blueprint(messages_bp)
    app.register_blueprint(competitions_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(users_bp)
    
    # Page routes (serving templates)

    
    @app.route('/auth')
    def auth_page():
        """Serve auth page"""
        return render_template('auth.html')
    
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
            join_room(room)
            connected_users[user_id] = request.sid
            emit('user_joined', {
                'user_id': user_id,
                'timestamp': datetime.utcnow().isoformat()
            }, room=room)
    
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
    
    @socketio.on('whiteboard_draw')
    def handle_whiteboard_draw(data):
        """Handle whiteboard drawing"""
        room = data.get('room')
        drawing_data = data.get('drawing_data')
        user_id = data.get('user_id')
        
        if room and drawing_data:
            emit('draw_update', {
                'user_id': user_id,
                'drawing_data': drawing_data,
                'timestamp': datetime.utcnow().isoformat()
            }, room=room, skip_sid=request.sid)
    
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
    
    @socketio.on('leave_room')
    def on_leave_room(data):
        """Handle user leaving a room"""
        room = data.get('room')
        user_id = data.get('user_id')
        
        if room and user_id:
            leave_room(room)
            if user_id in connected_users:
                del connected_users[user_id]
            emit('user_left', {
                'user_id': user_id,
                'timestamp': datetime.utcnow().isoformat()
            }, room=room)
    
    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle user disconnect"""
        print(f'Client disconnected: {request.sid}')
    
    return app, socketio

# Create app instance
if __name__ == '__main__':
    app, socketio = create_app(os.getenv('FLASK_ENV', 'development'))
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
