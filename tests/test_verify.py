from app.__init__ import create_app
from flask import url_for


def test_auth_page_url_builds():
    app, _ = create_app('testing')
    with app.test_request_context():
        url = url_for('auth_page', verified='true')
        assert url.endswith('/auth?verified=true') or url == '/auth?verified=true'


def test_verify_endpoint_returns_400_for_invalid_token():
    app, _ = create_app('testing')
    client = app.test_client()
    resp = client.get('/api/auth/verify-email/nonexistenttoken')
    assert resp.status_code == 400
    assert b'Invalid or expired verification link' in resp.data