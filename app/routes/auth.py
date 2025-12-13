from flask import Blueprint, request
import os
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

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


# =========================
# EMAIL / PASSWORD SIGNUP
# =========================
@auth_bp.route("/signup", methods=["POST"])
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
        avatar_url=None,
        auth_provider="local"
    )

    user_id = db.insert_one("users", user_doc)
    if not user_id:
        return error_response("User creation failed", 500)

    user_doc["_id"] = user_id
    del user_doc["password_hash"]

    token = generate_token(str(user_id))

    return success_response(
        {"user": serialize_document(user_doc), "token": token},
        "Signup successful",
        201
    )


# =========================
# EMAIL / PASSWORD LOGIN
# =========================
@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}

    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()

    if not email or not password:
        return error_response("Missing email or password", 400)

    db = Database()
    user = db.find_one("users", {"email": email})

    if not user:
        return error_response("Invalid email or password", 401)

    if user.get("auth_provider", "local") != "local":
        return error_response("Use Google login for this account", 400)

    if not verify_password(password, user.get("password_hash", "")):
        return error_response("Invalid email or password", 401)

    if not user.get("is_active", True):
        return error_response("Account inactive", 403)

    db.update_one(
        "users",
        {"_id": user["_id"]},
        {"last_login": datetime.utcnow()}
    )

    token = generate_token(str(user["_id"]))

    del user["password_hash"]
    return success_response(
        {"user": serialize_document(user), "token": token},
        "Login successful"
    )


# =========================
# GOOGLE LOGIN (CORRECT WAY)
# =========================
@auth_bp.route("/google", methods=["GET", "POST"])
def google_login():
    data = request.get_json() or {}
    google_token = data.get("id_token")

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
            avatar_url=id_info.get("picture"),
            auth_provider="google"
        )

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

    token = generate_token(str(user["_id"]))

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