from app.__init__ import create_app


def test_app_exposes_locks():
    app, socketio = create_app('testing')
    assert hasattr(app, '_room_timers_lock')
    assert hasattr(app, '_connected_users_lock')
    assert hasattr(app, '_online_users_lock')
