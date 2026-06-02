import logging
from datetime import datetime

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import login_required, current_user
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db, limiter
from app.models import AccessRequest, RegistrationKey
from app.routes.handlers.campaign_selection_handler import (
    delete_campaign_character,
    select_campaign,
    load_campaign,
    load_campaign_character,
    redeem_campaign_post,
)
from app.services.distributed_lock import get_redis_client
from app.services.key_generator import generate_secure_code

main_bp = Blueprint("main", __name__)

_ready_logger = logging.getLogger(__name__)
AUTO_ACCESS_PHASE = "default"


@main_bp.route("/healthz")
def healthz():
    """Cloud Run startup / liveness probe.

    Intentionally dependency-free: a slow DB or Redis must not flap the
    revision out. Deeper readiness checks belong on /ready.
    """
    return jsonify(ok=True), 200


@main_bp.route("/ready")
def ready():
    """Deep readiness probe — Redis (over the VPC path) and DB.

    Suitable for post-deploy smoke tests and low-frequency probes; do NOT wire
    this as an aggressive Cloud Run startup probe (each call talks to Redis
    over the connector and to Cloud SQL, amplifying load on every cold start).
    /healthz remains the cheap probe.

    Response shape:
        200 {ok: true, redis: "ok", db: "ok"}
        503 {ok: false, redis: <ok|error>, db: <ok|error>, error: "..."}
    """
    payload = {"ok": True, "redis": "ok", "db": "ok"}
    status_code = 200

    try:
        client = get_redis_client()
        if not client.ping():
            raise RuntimeError("PING returned falsy")
    except (RedisError, RuntimeError, OSError) as exc:
        payload["ok"] = False
        payload["redis"] = "error"
        payload["error"] = f"redis: {exc.__class__.__name__}"
        status_code = 503
        _ready_logger.warning("/ready Redis check failed: %s", exc)

    try:
        db.session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        payload["ok"] = False
        payload["db"] = "error"
        existing = payload.get("error")
        payload["error"] = (
            f"{existing}; db: {exc.__class__.__name__}"
            if existing
            else f"db: {exc.__class__.__name__}"
        )
        status_code = 503
        _ready_logger.warning("/ready DB check failed: %s", exc)
    finally:
        try:
            db.session.rollback()
        except Exception:
            pass

    return jsonify(payload), status_code


@main_bp.route("/")
def index():
    return render_template("landing.html")


_DOCS_SECTIONS = frozenset(
    {
        "overview",
        "getting-started",
        "gm-hub",
        "player",
        "items",
        "changelog",
        "terms",
        "privacy",
        "faq",
    }
)


@main_bp.route("/docs")
def docs():
    q = (request.args.get("q") or "").strip()
    section = (request.args.get("section") or "getting-started").strip()
    if section not in _DOCS_SECTIONS:
        section = "getting-started"
    return render_template("docs.html", q=q, section=section)


@main_bp.route("/changelog")
def changelog():
    return redirect(url_for("main.docs", section="changelog") + "#changelog")


@main_bp.route("/register")
def register_alias():
    vault_key = request.args.get("vault_key")
    email = request.args.get("email")
    return redirect(url_for("auth.register", vault_key=vault_key, email=email))


@main_bp.route("/access-request", methods=["GET", "POST"])
def access_request():
    if request.method == "POST":
        contact_name = (request.form.get("contact_name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        user_role = request.form.get("user_role")

        if not contact_name or len(contact_name) > 120:
            flash("Name is required (max 120 characters).", "warning")
            return redirect(url_for("main.access_request"))

        try:
            player_count = int(request.form.get("player_count") or 0)
        except ValueError:
            flash("Please enter a valid number for player count.", "warning")
            return redirect(url_for("main.access_request"))

        try:
            total_expected_users = int(request.form.get("total_expected_users") or 1)
        except ValueError:
            flash("Please enter a valid number for expected users.", "warning")
            return redirect(url_for("main.access_request"))

        is_homebrew = request.form.get("is_homebrew") == "yes"
        primary_ruleset = request.form.get("primary_ruleset")
        discovery_source = request.form.get("discovery_source")
        notes = request.form.get("notes")

        if not email or not user_role or not primary_ruleset:
            flash("Email, role, and primary ruleset are required.", "warning")
            return redirect(url_for("main.access_request"))

        if user_role in ["GM", "Both"] and player_count <= 0:
            flash("If you select GM or Both, player count is required.", "warning")
            return redirect(url_for("main.access_request"))

        vault_key = _generate_unique_access_key(AUTO_ACCESS_PHASE)
        ar = AccessRequest(
            contact_name=contact_name,
            email=email,
            user_role=user_role,
            player_count=player_count if user_role in ["GM", "Both"] else 0,
            total_expected_users=total_expected_users if total_expected_users >= 1 else 1,
            is_homebrew=is_homebrew,
            primary_ruleset=primary_ruleset,
            discovery_source=discovery_source,
            notes=notes,
            status="approved",
            processed_at=datetime.utcnow(),
            vault_key=vault_key,
            vault_key_used=False,
        )
        db.session.add(ar)
        db.session.add(
            RegistrationKey(
                key_code=vault_key,
                email=email,
                is_used=False,
                key_phase=AUTO_ACCESS_PHASE,
                is_admin_test_key=False,
            )
        )
        db.session.commit()

        return redirect(url_for("main.register_alias", vault_key=vault_key, email=email))

    return render_template("access_request.html")


def _generate_unique_access_key(phase_slug: str) -> str:
    pc = current_app.extensions["phase_config"]
    row = pc.get_phase(phase_slug)
    prefix = row["prefix"]
    while True:
        code = generate_secure_code(prefix=prefix, segments=2, segment_len=4)
        exists = RegistrationKey.query.filter_by(key_code=code).first()
        exists = exists or AccessRequest.query.filter_by(vault_key=code).first()
        if not exists:
            return code


@main_bp.route("/thank-you")
def thank_you():
    ruleset = (request.args.get("ruleset") or "").strip()
    return render_template("thank_you.html", ruleset=ruleset)


@main_bp.route("/campaigns")
@login_required
def campaigns():
    return select_campaign()


@main_bp.route("/campaigns/load/<int:campaign_id>")
@login_required
def load_campaign_route(campaign_id):
    return load_campaign(campaign_id)


@main_bp.route("/campaigns/load/<int:campaign_id>/character/<int:player_id>")
@login_required
def load_campaign_character_route(campaign_id, player_id):
    return load_campaign_character(campaign_id, player_id)


@main_bp.route(
    "/campaigns/load/<int:campaign_id>/character/<int:player_id>/delete",
    methods=["POST"],
)
@login_required
def delete_campaign_character_route(campaign_id, player_id):
    return delete_campaign_character(campaign_id, player_id)


@main_bp.route("/campaigns/redeem", methods=["POST"])
@login_required
@limiter.limit("3 per hour")
def campaign_redeem():
    return redeem_campaign_post()


@main_bp.route("/home")
@login_required
def home():
    if current_user.role == "vault_keeper":
        return redirect(url_for("admin.keys_overview"))

    if "campaign_id" not in session:
        return redirect(url_for("main.campaigns"))

    mode = session.get("session_mode")
    if mode == "gm":
        return redirect(url_for("gm.home"))
    if mode == "player":
        return redirect(url_for("player.player_home"))
    # Legacy sessions before session_mode existed
    if current_user.role == "GM":
        return redirect(url_for("gm.home"))
    return redirect(url_for("player.player_home"))


@main_bp.route("/player_dashboard")
@login_required
def player_dashboard():
    return redirect(url_for("player.player_home"))
