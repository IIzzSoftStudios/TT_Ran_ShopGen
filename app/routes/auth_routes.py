from flask import Blueprint
from flask_login import login_required

from app.routes.handlers.auth_handler import (
    handle_login,
    handle_logout,
    handle_register,
    handle_forgot_password,
    handle_reset_password,
    handle_admin_reset,
)

auth = Blueprint("auth", __name__)

@auth.route("/login", methods=["GET", "POST"])
def login():
    """Login route - delegates to handler."""
    return handle_login()

@auth.route("/logout")
@login_required
def logout():
    """Logout route - delegates to handler."""
    return handle_logout()

# @auth.route("/debug_user")
# @login_required
# def debug_user():
#     print(f"DEBUG: Session data: {session.items()}")
#     user_id = session.get("user_id")
#     user = db.session.get(User, user_id) if user_id else None
#     return f"User ID from session: {user_id}, User from DB: {user}"


@auth.route("/register", methods=["GET", "POST"])
def register():
    """Registration route - delegates to handler."""
    return handle_register()

@auth.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Forgot password route - delegates to handler."""
    return handle_forgot_password()

@auth.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    """Reset password route - delegates to handler."""
    return handle_reset_password(token)

@auth.route("/admin-reset", methods=["GET", "POST"])
def admin_reset():
    """Admin reset route - delegates to handler."""
    return handle_admin_reset()

