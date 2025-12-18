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


def test_verify_redirects_if_email_param_and_already_verified():
    from app.services import Database
    from app.models import User
    from urllib.parse import quote_plus

    app, _ = create_app('testing')
    db = Database()

    # Insert an already-verified user
    user_doc = User.create_user_doc('alreadyverified@example.com', 'verified', 'passwordhash')
    user_doc['is_verified'] = True
    user_doc.pop('password_hash', None)
    db.insert_one('users', user_doc)

    client = app.test_client()
    url = f"/api/auth/verify-email/nonexistenttoken?email={quote_plus('alreadyverified@example.com')}"
    resp = client.get(url)

    # Should redirect to the auth page with verified=true
    assert resp.status_code in (301, 302, 303, 307)
    assert resp.location.endswith('/auth?verified=true')