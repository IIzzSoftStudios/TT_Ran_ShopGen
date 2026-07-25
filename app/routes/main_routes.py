import logging
import re
from datetime import datetime
from pathlib import Path

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, send_from_directory, session, url_for
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
from app.services.creator_partnership_mail import send_creator_partnership_emails
from app.services.distributed_lock import get_redis_client
from app.services.investor_deck_mail import send_investor_request_emails
from app.services.key_generator import generate_secure_code
from app.services.landing_tiktok import load_landing_tiktok_feed
from app.services.landing_youtube import load_landing_youtube_feed

main_bp = Blueprint("main", __name__)

_ready_logger = logging.getLogger(__name__)
AUTO_ACCESS_PHASE = "alpha"
PUBLIC_DECK_FILENAME = "web-deck-v1.pdf"
_CONSUMER_EMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "yahoo.com",
        "hotmail.com",
        "outlook.com",
        "live.com",
        "aol.com",
        "icloud.com",
        "me.com",
        "proton.me",
        "protonmail.com",
    }
)
_INVESTOR_STATUSES = frozenset({"accredited", "institutional"})
_CHECK_SIZES = frozenset({"10000_25000", "25000_50000", "50000_100000", "100000_plus"})
_CREATOR_PLATFORMS = frozenset(
    {"youtube_shorts", "tiktok", "twitch", "instagram_reels", "podcast_other"}
)
_CREATOR_AUDIENCE_SIZES = frozenset({"under_10k", "10k_50k", "50k_250k", "250k_plus"})
_CREATOR_CONTENT_FOCUS = frozenset({"ttrpg", "gm_advice", "grand_strategy", "military_sim"})
_CREATOR_PARTNERSHIP_TYPES = frozenset({"affiliate", "paid_sponsorship", "product_exchange"})


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
    return render_template(
        "landing.html",
        tiktok_feed=load_landing_tiktok_feed(),
        youtube_feed=load_landing_youtube_feed(),
    )


_DOCS_SECTIONS = frozenset(
    {
        "overview",
        "getting-started",
        "gm-hub",
        "player",
        "items",
        "roadmap",
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
    return redirect(url_for("main.access_request"))


@main_bp.route("/public-deck")
def public_deck():
    """Serve the public-facing deck PDF (not the investor data room)."""
    media_dir = Path(current_app.root_path) / "static" / "media"
    deck_path = media_dir / PUBLIC_DECK_FILENAME
    if not deck_path.is_file():
        flash("Public deck is not available yet. Please try again later.", "warning")
        return redirect(url_for("main.index"))
    return send_from_directory(
        media_dir,
        PUBLIC_DECK_FILENAME,
        mimetype="application/pdf",
        as_attachment=False,
        download_name="Econo-Forge-Public-Deck.pdf",
    )


def _email_domain(email: str) -> str:
    return email.rsplit("@", 1)[-1].lower().strip()


def _normalize_fund_website(raw: str) -> str | None:
    """Accept bare domains or http(s) URLs; returns normalized https URL or None if invalid."""
    value = (raw or "").strip()
    if not value:
        return None
    if len(value) > 500 or " " in value:
        return None
    if not value.startswith(("http://", "https://")):
        value = f"https://{value.lstrip('/')}"
    host = value.split("://", 1)[-1].split("/")[0].split("?")[0]
    if "." not in host or host.startswith(".") or host.endswith("."):
        return None
    return value


def _validate_investor_payload(form) -> dict | None:
    full_name = (form.get("full_name") or "").strip()
    email = (form.get("email") or "").strip().lower()
    company_fund_name = (form.get("company_fund_name") or "").strip()
    fund_website_raw = (form.get("fund_website") or "").strip()
    investor_status = (form.get("investor_status") or "").strip()
    check_size = (form.get("check_size") or "").strip()
    prior_saas_gaming_invest = (form.get("prior_saas_gaming_invest") or "").strip()
    confidentiality_ack = form.get("confidentiality_ack") == "yes"

    if not full_name or len(full_name) > 120:
        flash("Full name is required (max 120 characters).", "warning")
        return None
    if not email or "@" not in email or len(email) > 255:
        flash("A valid professional email address is required.", "warning")
        return None
    if not company_fund_name or len(company_fund_name) > 200:
        flash("Company / fund / syndicate name is required.", "warning")
        return None
    fund_website = _normalize_fund_website(fund_website_raw)
    if fund_website_raw and fund_website is None:
        flash("Fund website must be a valid domain or URL (e.g., yourfund.com).", "warning")
        return None
    if _email_domain(email) in _CONSUMER_EMAIL_DOMAINS and not fund_website:
        flash(
            "Personal email detected—add your fund website so we can verify your background, or use a work/fund address.",
            "warning",
        )
        return None
    if investor_status not in _INVESTOR_STATUSES:
        flash("Please select your investor status.", "warning")
        return None

    if check_size not in _CHECK_SIZES:
        flash("Please select a typical check size / investment range.", "warning")
        return None
    if prior_saas_gaming_invest not in {"yes", "no"}:
        flash("Please indicate whether you have previously invested in SaaS, gaming, or infrastructure technology.", "warning")
        return None
    if not confidentiality_ack:
        flash("You must acknowledge the confidentiality terms before submitting.", "warning")
        return None

    return {
        "full_name": full_name,
        "email": email,
        "company_fund_name": company_fund_name,
        "fund_website": fund_website or None,
        "investor_status": investor_status,
        "check_size": check_size,
        "prior_saas_gaming_invest": prior_saas_gaming_invest,
    }


@main_bp.route("/investor-deck-request", methods=["GET", "POST"])
@limiter.limit("5 per hour")
def investor_deck_request():
    if request.method == "POST":
        payload = _validate_investor_payload(request.form)
        if payload is None:
            return redirect(url_for("main.investor_deck_request"))

        try:
            send_investor_request_emails(payload)
        except Exception as exc:
            _ready_logger.warning("Investor deck email failed: %s", exc)
            flash(
                "We could not send your request right now. Please try again shortly or email iizzsoftstudios@gmail.com directly.",
                "error",
            )
            return redirect(url_for("main.investor_deck_request"))

        return redirect(url_for("main.investor_deck_thanks"))

    return render_template("investor_deck_request.html")


@main_bp.route("/investor-deck-thanks")
def investor_deck_thanks():
    return render_template("investor_deck_thanks.html")


def _validate_creator_payload(form) -> dict | None:
    full_name = (form.get("full_name") or "").strip()
    email = (form.get("email") or "").strip().lower()
    primary_platform = (form.get("primary_platform") or "").strip()
    channel_url = (form.get("channel_url") or "").strip()
    audience_size = (form.get("audience_size") or "").strip()
    content_focus = [v for v in form.getlist("content_focus") if v in _CREATOR_CONTENT_FOCUS]
    avg_views_note = (form.get("avg_views_note") or "").strip()
    partnership_type = (form.get("partnership_type") or "").strip()
    rate_or_cpm = (form.get("rate_or_cpm") or "").strip()
    campaign_pitch = (form.get("campaign_pitch") or "").strip()

    if not full_name or len(full_name) > 120:
        flash("Full name is required (max 120 characters).", "warning")
        return None
    if not email or "@" not in email or len(email) > 255:
        flash("A valid email address is required.", "warning")
        return None
    if primary_platform not in _CREATOR_PLATFORMS:
        flash("Please select your primary platform.", "warning")
        return None
    if not channel_url or len(channel_url) > 500:
        flash("Primary channel URL or handle is required.", "warning")
        return None
    if audience_size not in _CREATOR_AUDIENCE_SIZES:
        flash("Please select your audience size.", "warning")
        return None
    if not content_focus:
        flash("Select at least one primary content focus.", "warning")
        return None
    if not avg_views_note or len(avg_views_note) > 300:
        flash("Average views or concurrent viewers is required (max 300 characters).", "warning")
        return None
    if partnership_type not in _CREATOR_PARTNERSHIP_TYPES:
        flash("Please select a partnership type.", "warning")
        return None
    if partnership_type == "paid_sponsorship" and (not rate_or_cpm or len(rate_or_cpm) > 200):
        flash("Standard rate or base CPM is required for paid sponsorship requests.", "warning")
        return None
    if not campaign_pitch or len(campaign_pitch) > 2000:
        flash("Please describe how you plan to showcase Econo-Forge (max 2000 characters).", "warning")
        return None

    return {
        "full_name": full_name,
        "email": email,
        "primary_platform": primary_platform,
        "channel_url": channel_url,
        "audience_size": audience_size,
        "content_focus": content_focus,
        "avg_views_note": avg_views_note,
        "partnership_type": partnership_type,
        "rate_or_cpm": rate_or_cpm or None,
        "campaign_pitch": campaign_pitch,
    }


@main_bp.route("/creator-partnership", methods=["GET", "POST"])
@limiter.limit("5 per hour")
def creator_partnership_request():
    if request.method == "POST":
        payload = _validate_creator_payload(request.form)
        if payload is None:
            return redirect(url_for("main.creator_partnership_request"))

        try:
            send_creator_partnership_emails(payload)
        except Exception as exc:
            _ready_logger.warning("Creator partnership email failed: %s", exc)
            flash(
                "We could not send your request right now. Please try again shortly or email iizzsoftstudios@gmail.com directly.",
                "error",
            )
            return redirect(url_for("main.creator_partnership_request"))

        return redirect(url_for("main.creator_partnership_thanks"))

    return render_template("creator_partnership_request.html")


@main_bp.route("/creator-partnership-thanks")
def creator_partnership_thanks():
    return render_template("creator_partnership_thanks.html")


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
