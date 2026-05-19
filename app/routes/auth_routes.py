from flask import Blueprint, request
from flask_login import login_required

from app.extensions import limiter
from app.routes.handlers.auth_handler import (
    handle_login,
    handle_logout,
    handle_register,
    handle_forgot_password,
    handle_reset_password,
    handle_post_submission,
    handle_get_avatar,
    handle_upload_avatar,
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


@auth.route("/account/submissions", methods=["POST"])
@login_required
@limiter.limit("10 per hour", exempt_when=lambda: request.method != "POST")
def account_submissions():
    return handle_post_submission()


@auth.route("/account/avatar", methods=["GET", "POST"])
@login_required
@limiter.limit("20 per hour", exempt_when=lambda: request.method == "GET")
def account_avatar():
    if request.method == "GET":
        return handle_get_avatar()
    return handle_upload_avatar()
