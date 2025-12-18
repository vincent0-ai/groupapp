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
