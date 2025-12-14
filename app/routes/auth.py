from flask import Blueprint, request, url_for, redirect
import os
import secrets
from dotenv import load_dotenv
load_dotenv()

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

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


def send_verification_email(to_email, token):
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
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
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

    send_verification_email(email, user_doc["verification_token"])

    return success_response(
        None,
        "Signup successful. Please check your email to verify your account.",
        201
    )


# =========================
# EMAIL / PASSWORD LOGIN
# =========================
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
    
    return redirect(url_for('auth_page', verified='true'))


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