from app.__init__ import create_app
from app.services import Database
from app.models import User
from datetime import datetime, timedelta


def test_forgot_password_sets_token_and_returns_success(monkeypatch):
    # Ensure SMTP creds are not set so send will fail gracefully
    monkeypatch.delenv('SMTP_USER', raising=False)
    monkeypatch.delenv('SMTP_PASSWORD', raising=False)

    app, _ = create_app('testing')
    db = Database()

    # Insert a user
    user_doc = User.create_user_doc('resetme@example.com', 'resetme', 'initialhash')
    user_id = db.insert_one('users', user_doc)
    assert user_id is not None

    client = app.test_client()
    resp = client.post('/api/auth/forgot-password', json={'email': 'resetme@example.com'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'success'

    updated = db.find_one('users', {'email': 'resetme@example.com'})
    assert updated is not None
    assert 'password_reset_token' in updated
    assert 'password_reset_expires' in updated


def test_validate_reset_token_invalid():
    app, _ = create_app('testing')
    client = app.test_client()

    resp = client.post('/api/auth/validate-reset-token', json={'token': 'nonexistent'})
    assert resp.status_code == 400


def test_reset_password_with_valid_token():
    app, _ = create_app('testing')
    db = Database()

    # Create user and set a token
    user_doc = User.create_user_doc('user2@example.com', 'user2', 'oldhash')
    user_id = db.insert_one('users', user_doc)

    token = 'resettoken123'
    expires = datetime.utcnow() + timedelta(hours=1)
    db.update_one('users', {'_id': user_id}, {'$set': {'password_reset_token': token, 'password_reset_expires': expires}}, raw=True)

    client = app.test_client()
    new_password = 'newstrongpassword'
    resp = client.post('/api/auth/reset-password', json={'token': token, 'password': new_password})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'success'

    updated = db.find_one('users', {'email': 'user2@example.com'})
    assert updated is not None
    assert 'password_reset_token' not in updated
    assert 'password_reset_expires' not in updated
    assert 'password_hash' in updated
    assert updated['password_hash'] != 'oldhash'