from app.__init__ import create_app
from app.services import Database
import json


def test_login_handles_invalid_password_hash():
    app, _ = create_app('testing')
    client = app.test_client()

    db = Database()
    # Insert a user that is marked as local but has a malformed/None password hash
    user = {
        'email': 'badhash@example.com',
        'username': 'badhash',
        'password_hash': None,
        'auth_provider': 'local',
        'is_verified': True,
        'is_active': True,
    }
    user_id = db.insert_one('users', user)
    assert user_id is not None

    resp = client.post('/api/auth/login', json={'email': 'badhash@example.com', 'password': 'whatever'})
    assert resp.status_code == 401
    body = json.loads(resp.data)
    assert body['message'] == 'Invalid email or password'
