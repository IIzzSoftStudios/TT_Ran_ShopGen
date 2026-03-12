"""Admin Bastion: GM-only key management. 404 for non-GM."""
from flask import Blueprint
from flask_login import login_required

from app.decorators import admin_required
from app.routes.handlers.admin_handler import (
    handle_admin_keys,
    handle_generate_bulk,
    handle_reveal_key,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/vault/keys", methods=["GET"])
@login_required
@admin_required
def keys_overview():
    """List registration keys (masked). GM only; 404 for others."""
    return handle_admin_keys()


@admin_bp.route("/vault/keys/generate", methods=["POST"])
@login_required
@admin_required
def keys_generate():
    """Bulk generate keys. GM only; CSRF required via form."""
    return handle_generate_bulk()


@admin_bp.route("/vault/keys/reveal/<int:key_id>", methods=["GET"])
@login_required
@admin_required
def keys_reveal(key_id):
    """On-demand reveal one key as JSON. GM only."""
    return handle_reveal_key(key_id)
