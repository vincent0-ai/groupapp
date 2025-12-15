from flask import Blueprint, render_template
from app.utils.auth import get_current_user

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    return render_template('dashboard.html')

@main_bp.route('/auth')
def auth_page():
    return render_template('auth.html')

@main_bp.route('/groups')
def groups_page():
    return render_template('groups.html')

@main_bp.route('/messages')
def messages_page():
    return render_template('messages.html')

@main_bp.route('/competitions')
def competitions_page():
    return render_template('competitions.html')

@main_bp.route('/files')
def files_page():
    return render_template('files.html')

@main_bp.route('/profile')
def profile_page():
    return render_template('profile.html')

@main_bp.route('/whiteboard')
def whiteboard_page():
    return render_template('whiteboard.html')

@main_bp.route('/admin')
def admin_page():
    return render_template('admin.html')

@main_bp.route('/dm')
def dm_page():
    return render_template('dm.html')

@main_bp.route('/leaderboard')
def leaderboard_page():
    return render_template('leaderboard.html')

@main_bp.route('/terms')
def terms_page():
    return render_template('terms.html')
