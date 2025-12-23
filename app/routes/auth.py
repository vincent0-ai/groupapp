from flask import Blueprint, request, url_for, redirect, current_app
import os
import secrets
from dotenv import load_dotenv
load_dotenv()

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import time

from app.utils import (
    hash_password,
    verify_password,
    generate_token,
    success_response,
    error_response,
    validate_email,
    serialize_document
)
from app.services import Database
from app.models import User
from app import limiter

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def send_verification_email(to_email, token, return_error=False):
    """Send a verification email.

    If return_error is True, return a tuple: (success: bool, error: str|None, fatal: bool)
    Where `fatal` indicates a non-retriable error (e.g., missing config or auth failure).
    When return_error is False (backwards compatible), return a boolean success flag.
    """
    smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", 465))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    
    # Generate verification URL. Prefer configured APP_URL (useful when behind an HTTPS reverse proxy).
    app_url = current_app.config.get('APP_URL') if current_app else None
    if app_url:
        # Build absolute URL using configured APP_URL (preserves https if set)
        # Include the recipient email as a query param so if a token is invalid but
        # the account is already verified we can still redirect the user gracefully.
        path = url_for('auth.verify_email', token=token, email=to_email, _external=False)
        verify_url = app_url.rstrip('/') + path
    else:
        # Fallback to request-based external url. Include email query param as above.
        verify_url = url_for('auth.verify_email', token=token, email=to_email, _external=True)
    
    if not smtp_user or not smtp_password:
        if return_error:
            return False, 'missing_credentials', True
        return False

    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = to_email
    msg["Subject"] = "Verify your email - Discussio"

    body = f"""
    <h3>Welcome to Discussio!</h3>
    <p>Please verify your email address by clicking the link below:</p>
    <a href="{verify_url}" style="padding: 10px 20px; background-color: #4F46E5; color: white; text-decoration: none; border-radius: 5px;">Verify Email</a>
    <p>Or copy this link: {verify_url}</p>
    """
    msg.attach(MIMEText(body, "html"))

    try:
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        else:
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
        server.quit()
        if return_error:
            return True, None, False
        return True
    except smtplib.SMTPAuthenticationError as e:
        print(f"Failed to send email (auth): {e}")
        if return_error:
            return False, 'auth_error', True
        return False
    except Exception as e:
        # Treat generic exceptions as transient unless explicitly an auth/missing config error
        print(f"Failed to send email: {e}")
        if return_error:
            return False, str(e), False
        return False


# =========================
# EMAIL / PASSWORD SIGNUP
# =========================
@auth_bp.route("/signup", methods=["POST"])
@limiter.limit("2 per hour")
def signup():
    data = request.get_json() or {}

    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()
    username = data.get("username", "").strip()
    full_name = data.get("full_name", "").strip()

    if not all([email, password, username]):
        return error_response("Missing required fields", 400)

    if not validate_email(email):
        return error_response("Invalid email format", 400)

    if len(password) < 8:
        return error_response("Password must be at least 8 characters", 400)

    if len(username) < 3:
        return error_response("Username must be at least 3 characters", 400)

    db = Database()

    if db.find_one("users", {"email": email}):
        return error_response("Email already registered", 400)

    if db.find_one("users", {"username": username}):
        return error_response("Username already taken", 400)

    user_doc = User.create_user_doc(
        email=email,
        username=username,
        password_hash=hash_password(password),
        full_name=full_name,
        avatar_url=None
    )
    user_doc["auth_provider"] = "local"

    # Add verification
    user_doc["is_verified"] = False
    user_doc["verification_token"] = secrets.token_urlsafe(32)

    user_id = db.insert_one("users", user_doc)
    if not user_id:
        return error_response("User creation failed", 500)

    # Try to send verification email and report if it fails. Get detailed error info
    email_ok, err, fatal = send_verification_email(email, user_doc["verification_token"], return_error=True)

    if not email_ok:
        # If it's a transient error, schedule background retries
        if not fatal:
            try:
                schedule_verification_email_retry(email, user_doc["verification_token"])
                retry_scheduled = True
            except Exception as e:
                print(f"Failed to schedule retry worker: {e}")
                retry_scheduled = False
        else:
            retry_scheduled = False

        # In development expose the verification link to make it easy for local testing
        data = {"email_sent": False, "retry_scheduled": retry_scheduled}
        if current_app and current_app.config.get('DEBUG', False):
            app_url = current_app.config.get('APP_URL') if current_app else None
            if app_url:
                data["verification_link"] = app_url.rstrip('/') + url_for('auth.verify_email', token=user_doc["verification_token"], email=user_doc.get('email'), _external=False)
            else:
                data["verification_link"] = url_for('auth.verify_email', token=user_doc["verification_token"], email=user_doc.get('email'), _external=True)
            data["error"] = err

        return success_response(
            data,
            "Signup successful. We were unable to send a verification email. Please check server logs or contact support.",
            201
        )

    return success_response(
        {"email_sent": True},
        "Signup successful. Please check your email to verify your account.",
        201
    )


# =========================
# EMAIL / PASSWORD LOGIN
# =========================
def _email_retry_worker(to_email, token, max_attempts: int = 3, initial_delay: int = 5, backoff_factor: int = 2):
    """Background worker that retries sending emails with exponential backoff.

    This is intentionally simple: it uses time.sleep and prints logs. It will
    stop early on fatal errors (auth/misconfiguration).
    """
    attempt = 1
    delay = initial_delay
    while attempt <= max_attempts:
        print(f"Email retry attempt {attempt}/{max_attempts} for {to_email}")
        success, err, fatal = send_verification_email(to_email, token, return_error=True)
        if success:
            print(f"Email sent to {to_email} on retry attempt {attempt}.")
            return True
        if fatal:
            print(f"Fatal email error for {to_email}: {err}. Aborting retries.")
            return False
        if attempt == max_attempts:
            print(f"Reached max email retry attempts for {to_email}. Giving up.")
            return False
        print(f"Transient email error for {to_email}: {err}. Sleeping {delay}s before next attempt.")
        time.sleep(delay)
        delay *= backoff_factor
        attempt += 1
    return False


def schedule_verification_email_retry(to_email, token, max_attempts: int = 3):
    """Schedule the email retry worker in the background.

    Tries to use the app's SocketIO background task helper, falling back to
    a plain thread if necessary.
    """
    try:
        # Use socketio background task if available to run inside app context properly
        if current_app and hasattr(current_app, 'socketio'):
            current_app.socketio.start_background_task(_email_retry_worker, to_email, token, max_attempts)
            return True
    except Exception as e:
        print(f"Failed to start background task via socketio: {e}")

    # Fallback to a simple thread
    try:
        import threading
        t = threading.Thread(target=_email_retry_worker, args=(to_email, token, max_attempts), daemon=True)
        t.start()
        return True
    except Exception as e:
        print(f"Failed to start background thread for email retries: {e}")
        return False

@auth_bp.route("/login", methods=["POST"])
@limiter.limit("5 per 15 minute")
def login():
    data = request.get_json() or {}

    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()
    remember = data.get("remember", False)

    if not email or not password:
        return error_response("Missing email or password", 400)

    db = Database()
    user = db.find_one("users", {"email": email})

    if not user:
        return error_response("Invalid email or password", 401)

    if user.get("auth_provider", "local") != "local":
        return error_response("Use Google login for this account", 400)

    if not user.get("is_verified", True):
        return error_response("Please verify your email address", 403)

    if not verify_password(password, user.get("password_hash", "")):
        return error_response("Invalid email or password", 401)

    if not user.get("is_active", True):
        return error_response("Account inactive", 403)

    db.update_one(
        "users",
        {"_id": user["_id"]},
        {"last_login": datetime.utcnow()}
    )

    expires_in = 2592000 if remember else 3600  # 30 days or 1 hour
    token = generate_token(str(user["_id"]), expires_in=expires_in)

    del user["password_hash"]
    # Set auth cookie for browser navigations; keep session storage behavior for SPA/API
    from flask import make_response
    resp, status = success_response({"user": serialize_document(user), "token": token}, "Login successful")
    resp = make_response(resp, status)
    secure_flag = not current_app.config.get('DEBUG', False)
    resp.set_cookie('auth_token', token, httponly=True, secure=secure_flag, samesite='Lax', path='/')
    return resp


@auth_bp.route("/verify-email/<token>", methods=["GET"])
def verify_email(token):
    db = Database()
    user = db.find_one("users", {"verification_token": token})
    
    if not user:
        # If token isn't found, check whether the link included an email and
        # that account is already verified. This handles cases where a token
        # has been consumed or removed (e.g., by admin or prior verification)
        # and avoids showing a confusing error to the end user.
        email = request.args.get('email')
        if email:
            existing = db.find_one("users", {"email": email.lower()})
            if existing and existing.get('is_verified', False):
                try:
                    return redirect(url_for('auth_page', verified='true'))
                except Exception as e:
                    print(f"Failed to build auth_page url: {e}")
                    fallback = current_app.config.get('APP_URL', '/') + '/auth?verified=true'
                    return redirect(fallback)
        return "Invalid or expired verification link.", 400
        
    db.update_one(
        "users",
        {"_id": user["_id"]},
        {"$set": {"is_verified": True}, "$unset": {"verification_token": ""}}
    )
    
    # Redirect to the auth page. Use 'auth_page' (defined in app routes) and
    # fall back to APP_URL if building the URL fails for any reason.
    try:
        return redirect(url_for('auth_page', verified='true'))
    except Exception as e:
        print(f"Failed to build auth_page url: {e}")
        fallback = current_app.config.get('APP_URL', '/') + '/auth?verified=true'
        return redirect(fallback)


# =========================
# PASSWORD RESET FLOW
# =========================
from datetime import timedelta


def send_password_reset_email(to_email, token, return_error=False):
    """Send a password reset email.

    Works like send_verification_email in terms of return value semantics.
    """
    smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", 465))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    
    # Build reset URL. Prefer APP_URL config to preserve correct scheme.
    app_url = current_app.config.get('APP_URL') if current_app else None
    if app_url:
        path = url_for('reset_password_page', _external=False)
        reset_url = app_url.rstrip('/') + path + f"?token={token}&email={to_email}"
    else:
        reset_url = url_for('reset_password_page', token=token, email=to_email, _external=True)

    if not smtp_user or not smtp_password:
        if return_error:
            return False, 'missing_credentials', True
        return False

    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = to_email
    msg["Subject"] = "Reset your password - Discussio"

    body = f"""
    <h3>Password reset requested</h3>
    <p>Click the button below to reset your password. This link will expire in 1 hour.</p>
    <a href="{reset_url}" style="padding: 10px 20px; background-color: #4F46E5; color: white; text-decoration: none; border-radius: 5px;">Reset Password</a>
    <p>Or copy this link: {reset_url}</p>
    """
    msg.attach(MIMEText(body, "html"))

    try:
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        else:
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
        server.quit()
        if return_error:
            return True, None, False
        return True
    except smtplib.SMTPAuthenticationError as e:
        print(f"Failed to send reset email (auth): {e}")
        if return_error:
            return False, 'auth_error', True
        return False
    except Exception as e:
        print(f"Failed to send reset email: {e}")
        if return_error:
            return False, str(e), False
        return False


def _reset_email_retry_worker(to_email, token, max_attempts: int = 3, initial_delay: int = 5, backoff_factor: int = 2):
    attempt = 1
    delay = initial_delay
    while attempt <= max_attempts:
        print(f"Reset email retry attempt {attempt}/{max_attempts} for {to_email}")
        success, err, fatal = send_password_reset_email(to_email, token, return_error=True)
        if success:
            print(f"Reset email sent to {to_email} on retry attempt {attempt}.")
            return True
        if fatal:
            print(f"Fatal reset email error for {to_email}: {err}. Aborting retries.")
            return False
        if attempt == max_attempts:
            print(f"Reached max reset email retry attempts for {to_email}. Giving up.")
            return False
        print(f"Transient reset email error for {to_email}: {err}. Sleeping {delay}s before next attempt.")
        time.sleep(delay)
        delay *= backoff_factor
        attempt += 1
    return False


def schedule_password_reset_email_retry(to_email, token, max_attempts: int = 3):
    try:
        if current_app and hasattr(current_app, 'socketio'):
            current_app.socketio.start_background_task(_reset_email_retry_worker, to_email, token, max_attempts)
            return True
    except Exception as e:
        print(f"Failed to start background task via socketio for reset email: {e}")

    try:
        import threading
        t = threading.Thread(target=_reset_email_retry_worker, args=(to_email, token, max_attempts), daemon=True)
        t.start()
        return True
    except Exception as e:
        print(f"Failed to start background thread for reset email retries: {e}")
        return False


@auth_bp.route('/forgot-password', methods=['POST'])
@limiter.limit('5 per hour')
def forgot_password():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()

    # Always return success to avoid disclosing whether an email exists
    db = Database()
    user = db.find_one('users', {'email': email}) if email else None

    if user:
        token = secrets.token_urlsafe(32)
        expires = datetime.utcnow() + timedelta(hours=1)
        # Store token and expiry
        db.update_one('users', {'_id': user['_id']}, {'$set': {'password_reset_token': token, 'password_reset_expires': expires}} , raw=True)

        # Attempt to send email and schedule retries on transient failures
        sent, err, fatal = send_password_reset_email(email, token, return_error=True)
        if not sent:
            if not fatal:
                try:
                    schedule_password_reset_email_retry(email, token)
                    retry_scheduled = True
                except Exception as e:
                    print(f"Failed to schedule reset email retry worker: {e}")
                    retry_scheduled = False
            else:
                retry_scheduled = False

            # In DEBUG expose link for local testing
            data = {'email_sent': False, 'retry_scheduled': retry_scheduled}
            if current_app and current_app.config.get('DEBUG', False):
                app_url = current_app.config.get('APP_URL') if current_app else None
                if app_url:
                    data['reset_link'] = app_url.rstrip('/') + url_for('reset_password_page', _external=False) + f'?token={token}&email={email}'
                else:
                    data['reset_link'] = url_for('reset_password_page', token=token, email=email, _external=True)
                data['error'] = err

            return success_response(data, "If an account with that email exists, you'll receive a reset link shortly.")

    return success_response({'email_sent': True}, "If an account with that email exists, you'll receive a reset link shortly.")


@auth_bp.route('/validate-reset-token', methods=['POST'])
def validate_reset_token():
    data = request.get_json() or {}
    token = data.get('token')

    if not token:
        return error_response('Missing token', 400)

    db = Database()
    user = db.find_one('users', {'password_reset_token': token})
    if not user:
        return error_response('Invalid token', 400)

    expires = user.get('password_reset_expires')
    if not expires or (isinstance(expires, str) and not expires) :
        return error_response('Invalid token', 400)

    # If expires stored as datetime or string, compare correctly
    try:
        if isinstance(expires, str):
            # Try parsing ISO format
            expires_dt = datetime.fromisoformat(expires)
        else:
            expires_dt = expires
    except Exception:
        expires_dt = expires

    if expires_dt < datetime.utcnow():
        return error_response('Token expired', 400)

    return success_response({}, 'Token valid')


@auth_bp.route('/reset-password', methods=['POST'])
@limiter.limit('10 per hour')
def reset_password():
    data = request.get_json() or {}
    token = data.get('token')
    password = data.get('password', '').strip()

    if not token or not password:
        return error_response('Missing token or password', 400)

    if len(password) < 8:
        return error_response('Password must be at least 8 characters', 400)

    db = Database()
    user = db.find_one('users', {'password_reset_token': token})
    if not user:
        return error_response('Invalid token', 400)

    expires = user.get('password_reset_expires')
    try:
        if isinstance(expires, str):
            from dateutil import parser
            expires_dt = parser.isoparse(expires)
        else:
            expires_dt = expires
    except Exception:
        expires_dt = expires

    if expires_dt < datetime.utcnow():
        return error_response('Token expired', 400)

    # Update password and remove token fields
    db.update_one('users', {'_id': user['_id']}, {"$set": {'password_hash': hash_password(password), 'last_password_reset': datetime.utcnow()}, "$unset": {'password_reset_token': '', 'password_reset_expires': ''}}, raw=True)

    return success_response({}, 'Password reset successful')


@auth_bp.route("/google", methods=["GET", "POST"])
def google_login():
    data = request.get_json(silent=True, force=True) or request.form or request.args or {}
    google_token = data.get("id_token") or data.get("credential")

    if not google_token:
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            google_token = auth_header.split(' ')[1]

    if not google_token:
        return error_response("Missing Google id_token", 400)

    try:
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests

        id_info = id_token.verify_oauth2_token(
            google_token,
            google_requests.Request(),
            os.environ.get("GOOGLE_CLIENT_ID")
        )
    except Exception:
        return error_response("Invalid Google token", 401)

    email = id_info.get("email")
    if not email:
        return error_response("Google account has no email", 400)

    email = email.lower()
    db = Database()
    user = db.find_one("users", {"email": email})

    if not user:
        username_base = email.split("@")[0]
        username = username_base
        counter = 1

        while db.find_one("users", {"username": username}):
            username = f"{username_base}{counter}"
            counter += 1

        user_doc = User.create_user_doc(
            email=email,
            username=username,
            password_hash=None,
            full_name=id_info.get("name"),
            avatar_url=id_info.get("picture")
        )
        # Users created via Google are treated as verified automatically
        user_doc["auth_provider"] = "google"
        user_doc["is_verified"] = True

        user_doc["last_login"] = datetime.utcnow()
        user_id = db.insert_one("users", user_doc)

        user = user_doc
        user["_id"] = user_id
    else:
        if not user.get("is_active", True):
            return error_response("Account inactive", 403)

        db.update_one(
            "users",
            {"_id": user["_id"]},
            {"last_login": datetime.utcnow()}
        )

    remember = data.get("remember", False)
    expires_in = 2592000 if remember else 3600  # 30 days or 1 hour
    token = generate_token(str(user["_id"]), expires_in=expires_in)

    del user["password_hash"]
    # Set auth cookie for browser navigations; keep session storage behavior for SPA/API
    from flask import make_response
    resp, status = success_response({"user": serialize_document(user), "token": token}, "Google login successful")
    resp = make_response(resp, status)
    secure_flag = not current_app.config.get('DEBUG', False)
    resp.set_cookie('auth_token', token, httponly=True, secure=secure_flag, samesite='Lax', path='/')
    return resp


# =========================
# LOGOUT (JWT CLIENT-SIDE)
# =========================
@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    from flask import make_response
    resp, status = success_response(None, "Logout successful")
    resp = make_response(resp, status)
    # Clear auth cookie
    resp.set_cookie('auth_token', '', expires=0, path='/')
    return resp
# Note: Actual logout is handled client-side by deleting the JWT token.