from app.__init__ import create_app
from app.services import Database
import os
import json


def test_google_signup_auto_verified(monkeypatch):
    app, _ = create_app('testing')
    client = app.test_client()

    # Fake Google's verify method to return a valid payload
    def fake_verify(token, request, client_id):
        return {
            'email': 'guser@example.com',
            'name': 'Google User',
            'picture': 'https://example.com/avatar.png'
        }

    # Ensure GOOGLE_CLIENT_ID is set for the function call
    monkeypatch.setenv('GOOGLE_CLIENT_ID', 'fake-client-id')

    # Monkeypatch the verify function
    try:
        import google.oauth2.id_token as id_token
        monkeypatch.setattr(id_token, 'verify_oauth2_token', fake_verify)
    except Exception:
        # If the google package isn't present, inject a dummy module
        import types, sys
        fake_mod = types.SimpleNamespace(verify_oauth2_token=fake_verify)
        sys.modules['google'] = types.ModuleType('google')
        sys.modules['google.oauth2'] = types.ModuleType('google.oauth2')
        sys.modules['google.oauth2.id_token'] = fake_mod

    # Call the endpoint
    resp = client.post('/api/auth/google', json={'id_token': 'dummy-token'})
    assert resp.status_code == 200

    body = json.loads(resp.data)
    assert body['status'] == 'success'
    # Check user was created and marked verified
    db = Database()
    user = db.find_one('users', {'email': 'guser@example.com'})
    assert user is not None
    assert user.get('is_verified', False) is True
