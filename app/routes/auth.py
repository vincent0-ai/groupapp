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
    
    # Generate verification URL
    verify_url = url_for('auth.verify_email', token=token, _external=True)
    
    if not smtp_user or not smtp_password:
        print(f"============================================")
        print(f"EMAIL VERIFICATION for {to_email}")
        print(f"Link: {verify_url}")
        print(f"============================================")
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
            data["verification_link"] = url_for('auth.verify_email', token=user_doc["verification_token"], _external=True)
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
    return success_response(
        {"user": serialize_document(user), "token": token},
        "Login successful"
    )


@auth_bp.route("/verify-email/<token>", methods=["GET"])
def verify_email(token):
    db = Database()
    user = db.find_one("users", {"verification_token": token})
    
    if not user:
        return "Invalid or expired verification link.", 400
        
    db.update_one(
        "users",
        {"_id": user["_id"]},
        {"$set": {"is_verified": True}, "$unset": {"verification_token": ""}}
    )
    
    return redirect(url_for('main.auth_page', verified='true'))


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
        user_doc["auth_provider"] = "google"

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
    return success_response(
        {"user": serialize_document(user), "token": token},
        "Google login successful"
    )


# =========================
# LOGOUT (JWT CLIENT-SIDE)
# =========================
@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    return success_response(None, "Logout successful")
# Note: Actual logout is handled client-side by deleting the JWT token.