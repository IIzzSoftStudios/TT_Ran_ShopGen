<<<<<<< HEAD
from flask import Blueprint, abort
from flask_login import login_required

=======
from flask import Blueprint, request
from flask_login import login_required

from app.extensions import limiter
>>>>>>> GCP
from app.routes.handlers.auth_handler import (
    handle_login,
    handle_logout,
    handle_register,
    handle_forgot_password,
    handle_reset_password,
<<<<<<< HEAD
=======
    handle_post_submission,
    handle_get_avatar,
    handle_upload_avatar,
>>>>>>> GCP
)

auth = Blueprint("auth", __name__)


@auth.route("/login", methods=["GET", "POST"])
def login():
<<<<<<< HEAD
    """Login route - delegates to handler."""
    return handle_login()
=======
    return handle_login()

>>>>>>> GCP

@auth.route("/logout")
@login_required
def logout():
<<<<<<< HEAD
    """Logout route - delegates to handler."""
    return handle_logout()

# @auth.route("/debug_user")
# @login_required
# def debug_user():
#     print(f"DEBUG: Session data: {session.items()}")
#     user_id = session.get("user_id")
#     user = db.session.get(User, user_id) if user_id else None
#     return f"User ID from session: {user_id}, User from DB: {user}"
=======
    return handle_logout()
>>>>>>> GCP


@auth.route("/register", methods=["GET", "POST"])
def register():
<<<<<<< HEAD
    """Registration route - delegates to handler."""
    return handle_register()

@auth.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Forgot password route - delegates to handler."""
    return handle_forgot_password()

@auth.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    """Reset password route (email + OTP) - delegates to handler."""
    return handle_reset_password()

# Admin-reset disabled for security: exposed reset tokens to any caller.
# Use forgot-password flow; token is logged to server console for local testing only.
@auth.route("/admin-reset", methods=["GET", "POST"])
def admin_reset():
    """Disabled - returns 404."""
    abort(404)
=======
    return handle_register()


@auth.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("5 per hour", exempt_when=lambda: request.method != "POST")
def forgot_password():
    return handle_forgot_password()


@auth.route("/reset-password", methods=["GET", "POST"])
@limiter.limit("10 per hour", exempt_when=lambda: request.method != "POST")
def reset_password():
    return handle_reset_password()


@auth.route("/account/submissions", methods=["POST"])
@login_required
@limiter.limit("10 per hour", exempt_when=lambda: request.method != "POST")
def account_submissions():
    return handle_post_submission()

>>>>>>> GCP

@auth.route("/account/avatar", methods=["GET", "POST"])
@login_required
@limiter.limit("20 per hour", exempt_when=lambda: request.method == "GET")
def account_avatar():
    if request.method == "GET":
        return handle_get_avatar()
    return handle_upload_avatar()
