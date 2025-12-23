from flask import Blueprint, render_template, redirect, url_for
from app.utils.auth import get_current_user

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    user = get_current_user()
    if not user:
        return redirect(url_for('main.auth_page'))
    return render_template('dashboard.html', user=user)

@main_bp.route('/auth')
def auth_page():
    user = get_current_user()
    if user:
        return redirect(url_for('main.index'))
    return render_template('auth.html', user=user)

@main_bp.route('/groups')
def groups_page():
    user = get_current_user()
    if not user:
        return redirect(url_for('main.auth_page'))
    return render_template('groups.html', user=user)

@main_bp.route('/messages')
def messages_page():
    user = get_current_user()
    if not user:
        return redirect(url_for('main.auth_page'))
    return render_template('messages.html', user=user)

@main_bp.route('/competitions')
def competitions_page():
    user = get_current_user()
    if not user:
        return redirect(url_for('main.auth_page'))
    return render_template('competitions.html', user=user)

@main_bp.route('/competitions/create')
def create_competition_page():
    user = get_current_user()
    if not user:
        return redirect(url_for('main.auth_page'))
    return render_template('create_competition.html', user=user)

@main_bp.route('/files')
def files_page():
    user = get_current_user()
    if not user:
        return redirect(url_for('main.auth_page'))
    return render_template('files.html', user=user)

@main_bp.route('/profile')
def profile_page():
    user = get_current_user()
    if not user:
        return redirect(url_for('main.auth_page'))
    return render_template('profile.html', user=user)

@main_bp.route('/whiteboard')
def whiteboard_page():
    user = get_current_user()
    if not user:
        return redirect(url_for('main.auth_page'))
    return render_template('whiteboard.html', user=user)

@main_bp.route('/admin')
def admin_page():
    user = get_current_user()
    if not user or not user.get('is_admin'):
        return redirect(url_for('main.index'))
    return render_template('admin.html', user=user)

@main_bp.route('/dm')
def dm_page():
    user = get_current_user()
    if not user:
        return redirect(url_for('main.auth_page'))
    return render_template('dm.html', user=user)

@main_bp.route('/leaderboard')
def leaderboard_page():
    user = get_current_user()
    if not user:
        return redirect(url_for('main.auth_page'))
    return render_template('leaderboard.html', user=user)

@main_bp.route('/terms')
def terms_page():
    user = get_current_user()
    return render_template('terms.html', user=user)
