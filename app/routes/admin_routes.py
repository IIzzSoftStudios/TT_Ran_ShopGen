<<<<<<< HEAD
"""Admin Bastion: GM-only key management. 404 for non-GM."""
from flask import Blueprint
=======
"""Admin vault routes."""
from flask import Blueprint, jsonify
>>>>>>> GCP
from flask_login import login_required

from app.decorators import admin_required
from app.routes.handlers.admin_handler import (
    handle_admin_keys,
    handle_generate_bulk,
<<<<<<< HEAD
=======
    handle_generate_admin_test_keys,
>>>>>>> GCP
    handle_reveal_key,
    handle_approve_access_request,
    handle_hold_access_request,
    handle_reject_access_request,
<<<<<<< HEAD
)
=======
    handle_gm_simulation_usage_api,
    handle_gm_simulation_usage_export,
    handle_submission_action,
)
from app.services.sim_metrics import snapshot as simulation_metrics_snapshot
>>>>>>> GCP

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/vault/keys", methods=["GET"])
@login_required
@admin_required
def keys_overview():
<<<<<<< HEAD
    """List registration keys (masked). GM only; 404 for others."""
=======
>>>>>>> GCP
    return handle_admin_keys()


@admin_bp.route("/vault/keys/generate", methods=["POST"])
@login_required
@admin_required
def keys_generate():
<<<<<<< HEAD
    """Bulk generate keys. GM only; CSRF required via form."""
    return handle_generate_bulk()


=======
    return handle_generate_bulk()


@admin_bp.route("/vault/keys/generate-admin-test", methods=["POST"])
@login_required
@admin_required
def keys_generate_admin_test():
    return handle_generate_admin_test_keys()


>>>>>>> GCP
@admin_bp.route("/vault/keys/reveal/<int:key_id>", methods=["GET"])
@login_required
@admin_required
def keys_reveal(key_id):
<<<<<<< HEAD
    """On-demand reveal one key as JSON. GM only."""
    return handle_reveal_key(key_id)


=======
    return handle_reveal_key(key_id)


@admin_bp.route("/vault/gm-simulation-usage/export", methods=["GET"])
@login_required
@admin_required
def gm_simulation_usage_export():
    return handle_gm_simulation_usage_export()


@admin_bp.route("/vault/gm-simulation-usage", methods=["GET"])
@login_required
@admin_required
def gm_simulation_usage_api():
    return handle_gm_simulation_usage_api()


>>>>>>> GCP
@admin_bp.route("/vault/access-requests/<int:request_id>/approve", methods=["POST"])
@login_required
@admin_required
def access_request_approve(request_id):
<<<<<<< HEAD
    """Approve an access request card: generates a one-time vault key + emails applicant."""
=======
>>>>>>> GCP
    return handle_approve_access_request(request_id)


@admin_bp.route("/vault/access-requests/<int:request_id>/hold", methods=["POST"])
@login_required
@admin_required
def access_request_hold(request_id):
<<<<<<< HEAD
    """Hold an access request: moves it to the bottom of the current rank order."""
=======
>>>>>>> GCP
    return handle_hold_access_request(request_id)


@admin_bp.route("/vault/access-requests/<int:request_id>/reject", methods=["POST"])
@login_required
@admin_required
def access_request_reject(request_id):
<<<<<<< HEAD
    """Reject an access request: remove it from the actionable list (no email)."""
    return handle_reject_access_request(request_id)
=======
    return handle_reject_access_request(request_id)


@admin_bp.route("/vault/submissions/<int:submission_id>/<action>", methods=["POST"])
@login_required
@admin_required
def submission_action(submission_id, action):
    return handle_submission_action(submission_id, action)


@admin_bp.route("/vault/metrics/simulation", methods=["GET"])
@login_required
@admin_required
def simulation_metrics():
    """Operator view of simulation queue depth, in-flight count, and durations.

    Backs the alpha-metrics-queue todo: replaces "unknown concurrent load"
    with concrete numbers for sizing worker concurrency, Cloud SQL tier, and
    the eventual alpha-year-hard-no thresholds.
    """
    return jsonify(simulation_metrics_snapshot())
>>>>>>> GCP
