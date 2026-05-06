from flask import Blueprint, request
from flask_login import login_required

from app.extensions import limiter
from app.routes.handlers.auth_handler import (
    handle_login,
    handle_logout,
    handle_register,
    handle_forgot_password,
    handle_reset_password,
)

auth = Blueprint("auth", __name__)


@auth.route("/login", methods=["GET", "POST"])
def login():
    return handle_login()


@auth.route("/logout")
@login_required
def logout():
    return handle_logout()


@auth.route("/register", methods=["GET", "POST"])
def register():
    return handle_register()


@auth.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("5 per hour", exempt_when=lambda: request.method != "POST")
def forgot_password():
    return handle_forgot_password()


@auth.route("/reset-password", methods=["GET", "POST"])
@limiter.limit("10 per hour", exempt_when=lambda: request.method != "POST")
def reset_password():
    return handle_reset_password()
