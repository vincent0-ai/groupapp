from app.__init__ import create_app


def test_livekit_singleton():
    app, socketio = create_app('testing')
    lk1 = app.get_livekit()
    lk2 = app.get_livekit()
    assert lk1 is lk2
