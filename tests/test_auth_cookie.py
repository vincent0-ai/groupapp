from app.__init__ import create_app
from app.services import Database
from app.models import User
from app.utils.auth import hash_password


def test_login_sets_cookie_and_allows_navigation():
    app, _ = create_app('testing')
    client = app.test_client()
    db = Database()

    # Create a user
    password = 'password123'
    user_doc = User.create_user_doc('usercookie@example.com', 'cookieuser', hash_password(password), full_name='Cookie')
    user_doc['is_verified'] = True
    db.insert_one('users', user_doc)

    # Login
    resp = client.post('/api/auth/login', json={'email': 'usercookie@example.com', 'password': password})
    assert resp.status_code == 200
    # Check Set-Cookie header
    set_cookie = resp.headers.get('Set-Cookie', '')
    assert 'auth_token=' in set_cookie

    # Now use client (cookies stored) to access a protected page
    resp2 = client.get('/competitions', follow_redirects=False)
    # Should not redirect to auth page; should render competitions page (200)
    assert resp2.status_code == 200
    assert b'Competitions' in resp2.data

    # Test logout clears cookie
    resp3 = client.post('/api/auth/logout')
    set_cookie = resp3.headers.get('Set-Cookie', '')
    assert 'auth_token=;' in set_cookie or 'auth_token=' in set_cookie
    # After logout, accessing protected page should redirect to auth
    resp4 = client.get('/competitions', follow_redirects=False)
    assert resp4.status_code in (301, 302)
    assert '/auth' in resp4.headers.get('Location', '')
