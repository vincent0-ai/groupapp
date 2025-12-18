from app.__init__ import create_app
from app.routes.auth import send_verification_email, schedule_verification_email_retry


def test_send_verification_email_returns_false_without_smtp(monkeypatch):
    # Ensure SMTP creds are not set
    monkeypatch.delenv('SMTP_USER', raising=False)
    monkeypatch.delenv('SMTP_PASSWORD', raising=False)

    app, socketio = create_app('testing')
    with app.test_request_context():
        result = send_verification_email('test@example.com', 'token123')
        assert result is False


def test_send_verification_email_returns_error_details(monkeypatch):
    monkeypatch.delenv('SMTP_USER', raising=False)
    monkeypatch.delenv('SMTP_PASSWORD', raising=False)

    app, socketio = create_app('testing')
    with app.test_request_context():
        success, err, fatal = send_verification_email('test@example.com', 'token123', return_error=True)
        assert success is False
        assert fatal is True
        assert 'missing' in err or err == 'missing_credentials'


def test_schedule_retry_does_not_raise(monkeypatch):
    # Ensure SMTP creds are not set so initial send will fail and schedule a retry
    monkeypatch.delenv('SMTP_USER', raising=False)
    monkeypatch.delenv('SMTP_PASSWORD', raising=False)

    app, socketio = create_app('testing')
    with app.app_context():
        # Should not raise
        schedule_verification_email_retry('test@example.com', 'token123')


def test_login_route_is_mapped_and_returns_400_when_missing_fields():
    app, socketio = create_app('testing')
    client = app.test_client()
    resp = client.post('/api/auth/login', json={})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['status'] == 'error'
    assert 'Missing email or password' in data['message']


def test_verification_link_uses_app_url_if_set(monkeypatch, capsys):
    # Ensure SMTP creds are not set so the function prints the verification link to stdout
    monkeypatch.delenv('SMTP_USER', raising=False)
    monkeypatch.delenv('SMTP_PASSWORD', raising=False)

    app, socketio = create_app('testing')
    app.config['APP_URL'] = 'https://example.com'
    with app.test_request_context():
        send_verification_email('test@example.com', 'token123')
        captured = capsys.readouterr()
        assert 'https://example.com' in captured.out