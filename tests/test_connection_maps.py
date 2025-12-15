from app.__init__ import create_app


def test_connected_users_mapping():
    app, socketio = create_app('testing')
    # simulate two tabs for same user
    uid = 'user123'
    sid1 = 'sid-A'
    sid2 = 'sid-B'
    with app._connected_users_lock:
        s = app.connected_users.get(uid)
        if not s:
            s = set(); app.connected_users[uid] = s
        s.add(sid1)
        s.add(sid2)
        app.sid_to_user[sid1] = uid
        app.sid_to_user[sid2] = uid

    assert uid in app.connected_users
    assert sid1 in app.connected_users[uid]
    assert sid2 in app.connected_users[uid]
    # remove one sid
    with app._connected_users_lock:
        app.connected_users[uid].discard(sid1)
        del app.sid_to_user[sid1]
    assert sid1 not in app.connected_users[uid]
    assert sid2 in app.connected_users[uid]
    # remove last sid
    with app._connected_users_lock:
        app.connected_users[uid].discard(sid2)
        if not app.connected_users[uid]:
            del app.connected_users[uid]
        del app.sid_to_user[sid2]
    assert uid not in app.connected_users
