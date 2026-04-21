"""Admin vault routes."""
from flask import Blueprint
from flask_login import login_required

from app.decorators import admin_required
from app.routes.handlers.admin_handler import (
    handle_admin_keys,
    handle_generate_bulk,
    handle_reveal_key,
    handle_approve_access_request,
    handle_hold_access_request,
    handle_reject_access_request,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/vault/keys", methods=["GET"])
@login_required
@admin_required
def keys_overview():
    return handle_admin_keys()


@admin_bp.route("/vault/keys/generate", methods=["POST"])
@login_required
@admin_required
def keys_generate():
    return handle_generate_bulk()


@admin_bp.route("/vault/keys/reveal/<int:key_id>", methods=["GET"])
@login_required
@admin_required
def keys_reveal(key_id):
    return handle_reveal_key(key_id)


@admin_bp.route("/vault/access-requests/<int:request_id>/approve", methods=["POST"])
@login_required
@admin_required
def access_request_approve(request_id):
    return handle_approve_access_request(request_id)


@admin_bp.route("/vault/access-requests/<int:request_id>/hold", methods=["POST"])
@login_required
@admin_required
def access_request_hold(request_id):
    return handle_hold_access_request(request_id)


@admin_bp.route("/vault/access-requests/<int:request_id>/reject", methods=["POST"])
@login_required
@admin_required
def access_request_reject(request_id):
    return handle_reject_access_request(request_id)
