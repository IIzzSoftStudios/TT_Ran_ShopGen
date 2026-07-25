"""Public Demo entry: lead gate, anonymous snapshot restore + analytics beacon."""

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from app.extensions import db, limiter
from app.services.demo_analytics import (
    EVENT_DEMO_START,
    EVENT_STEP_VIEW,
    current_demo_run_id,
    mint_demo_run_id,
    record_demo_event,
)
from app.services.demo_leads import (
    normalize_contact_name,
    normalize_email,
    session_has_demo_lead,
    touch_last_step,
    upsert_demo_lead,
)
from app.services.demo_session import (
    _anon_id_for_session,
    active_demo_mode_for_user,
    start_anonymous_demo,
)

demo_bp = Blueprint("demo", __name__)


@demo_bp.route("/demo", methods=["GET"])
@limiter.limit("20 per hour; 5 per minute")
def start():
    """Require lead capture, then provision Demo and open GM home."""
    if not session_has_demo_lead():
        if not current_demo_run_id():
            mint_demo_run_id()
        return render_template("demo_lead.html")

    try:
        _campaign, setup_redirect, err = start_anonymous_demo()
    except Exception:
        from app.services.logging_config import gm_logger

        gm_logger.exception("Anonymous Demo start failed")
        flash("Could not start the Demo. Please try again.", "danger")
        return redirect(url_for("main.index"))

    if err:
        flash(err, "warning")
        return redirect(url_for("main.index"))

    if setup_redirect is not None:
        return setup_redirect
    return redirect(url_for("gm.home"), code=303)


@demo_bp.route("/demo/lead", methods=["POST"])
@limiter.limit("20 per hour; 5 per minute")
def capture_lead():
    raw_name = request.form.get("contact_name")
    raw_email = request.form.get("email")
    name_blank = raw_name is None or not str(raw_name).strip()
    email_blank = raw_email is None or not str(raw_email).strip()

    contact_name = "" if name_blank else normalize_contact_name(raw_name)
    if not name_blank and contact_name is None:
        flash("Enter a name up to 120 characters, or leave it blank.", "warning")
        return render_template(
            "demo_lead.html",
            contact_name=raw_name or "",
            email=raw_email or "",
        ), 400

    if email_blank:
        email = ""
    else:
        email = normalize_email(raw_email)
        if email is None:
            flash("Enter a valid email, or leave it blank.", "warning")
            return render_template(
                "demo_lead.html",
                contact_name=raw_name or "",
                email=raw_email or "",
            ), 400

    run_id = current_demo_run_id() or mint_demo_run_id()
    anon_id = session.get("demo_anon_id") or _anon_id_for_session()
    upsert_demo_lead(
        demo_run_id=run_id,
        demo_anon_id=str(anon_id),
        contact_name=contact_name or "",
        email=email or "",
    )
    db.session.commit()
    return redirect(url_for("demo.start"))


@demo_bp.route("/demo/analytics/event", methods=["POST"])
@login_required
@limiter.limit("120 per minute; 2000 per hour")
def analytics_event():
    """Record allowlisted Demo walkthrough events (step views / Register clicks)."""
    if not active_demo_mode_for_user(current_user):
        return jsonify({"ok": False, "error": "demo_mode_required"}), 403

    payload = request.get_json(silent=True) or {}
    event_type = (payload.get("event_type") or request.form.get("event_type") or "").strip()
    step_key = payload.get("step_key") or request.form.get("step_key")
    surface = (
        payload.get("surface")
        or request.form.get("surface")
        or "gm_tutorial"
    )

    if event_type == EVENT_DEMO_START:
        return jsonify({"ok": False, "error": "event_not_allowed"}), 400

    run_id = current_demo_run_id()
    if not run_id:
        return jsonify({"ok": False, "error": "missing_demo_run"}), 400

    anon_id = session.get("demo_anon_id") or _anon_id_for_session()
    row = record_demo_event(
        event_type=event_type,
        demo_run_id=run_id,
        demo_anon_id=str(anon_id),
        user_id=getattr(current_user, "id", None),
        step_key=step_key,
        surface=surface,
        commit=False,
    )
    if row is None:
        db.session.rollback()
        return jsonify({"ok": False, "error": "invalid_event"}), 400

    if event_type == EVENT_STEP_VIEW:
        touch_last_step(demo_run_id=run_id, step_key=step_key)

    db.session.commit()
    return jsonify({"ok": True, "id": row.id}), 200
