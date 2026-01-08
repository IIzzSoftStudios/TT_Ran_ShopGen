from flask import Blueprint
from flask_login import login_required
from app.routes.handlers.auth_login_handler import (
    handle_login,
    handle_logout
)
from app.routes.handlers.auth_registration_handler import (
    handle_register
)
from app.routes.handlers.auth_password_handler import (
    handle_forgot_password,
    handle_reset_password,
    handle_admin_reset
)
from app.routes.handlers.auth_verification_handler import (
    handle_verify_email,
    handle_resend_verification
)
from app.routes.handlers.auth_2fa_handler import (
    handle_2fa_setup,
    handle_2fa_verify,
    handle_2fa_disable
)

auth = Blueprint("auth", __name__)

@auth.route("/login", methods=["GET", "POST"])
def login():
    """Route for user login"""
    return handle_login()

@auth.route("/logout")
@login_required
def logout():
    """Route for user logout"""
    return handle_logout()

@auth.route("/register", methods=["GET", "POST"])
def register():
    """Route for user registration"""
    return handle_register()

@auth.route("/verify-email/<token>", methods=["GET"])
def verify_email(token):
    """Route for email verification"""
    return handle_verify_email(token)

@auth.route("/resend-verification", methods=["GET", "POST"])
def resend_verification():
    """Route to resend verification email"""
    return handle_resend_verification()

@auth.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Route for password reset requests"""
    return handle_forgot_password()

@auth.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    """Route for password reset with token"""
    return handle_reset_password(token)

@auth.route("/admin-reset", methods=["GET", "POST"])
def admin_reset():
    """Admin utility to generate reset token for testing"""
    return handle_admin_reset()

@auth.route("/2fa/setup", methods=["GET", "POST"])
@login_required
def two_factor_setup():
    """Route for 2FA setup"""
    return handle_2fa_setup()

@auth.route("/2fa/verify", methods=["POST"])
def two_factor_verify():
    """Route for 2FA verification during login"""
    return handle_2fa_verify()

@auth.route("/2fa/disable", methods=["POST"])
@login_required
def two_factor_disable():
    """Route to disable 2FA"""
    return handle_2fa_disable()

