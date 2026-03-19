"""Admin Bastion: key management. GM-only; 404 for non-admins; audit to file."""
import os
import logging
import json
from pathlib import Path
from logging.handlers import RotatingFileHandler
from flask import render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import current_user

from app.extensions import db
from app.models.users import RegistrationKey, AccessRequest
from app.services.key_generator import create_bulk_keys, generate_secure_code

# Dedicated admin audit logger; avoid duplicate handlers on reload.
# Create logs/ and file handler only when safe; do not crash at import (e.g. permission/read-only FS).
audit_logger = logging.getLogger("admin_audit")
audit_logger.setLevel(logging.INFO)
if not audit_logger.handlers:
    try:
        if not os.path.exists("logs"):
            os.makedirs("logs")
        handler = RotatingFileHandler(
            "logs/admin_audit.log",
            maxBytes=1_000_000,
            backupCount=5,
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )
        audit_logger.addHandler(handler)
    except OSError:
        # Directory creation or handler failed; app still runs, audit logs to file are skipped
        audit_logger.addHandler(logging.NullHandler())


def _debug_log(hypothesis_id, location, message, data, run_id="pre_fix"):
    """
    Minimal NDJSON logging for debug mode.
    Avoid secrets (vault keys) and personal data (emails).
    """
    # Repo-relative path (no machine-specific absolute Windows path).
    # File ends up at: <project_root>/debug-a4354b.log
    log_path = Path(__file__).resolve().parents[4] / "debug-a4354b.log"
    payload = {
        "sessionId": "a4354b",
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(__import__("time").time() * 1000),
    }
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass


def handle_admin_keys():
    """List all registration keys (newest first); stats; audit log view."""
    keys = RegistrationKey.query.order_by(
        RegistrationKey.created_at.desc()
    ).all()
    stats = {
        "total": len(keys),
        "used": sum(1 for k in keys if k.is_used),
        "available": sum(1 for k in keys if not k.is_used),
    }

    # Triage cards for access requests (Pending + Hold).
    access_requests = (
        AccessRequest.query.filter(AccessRequest.status.in_(["pending", "hold"]))
        .all()
    )
    role_order = {"GM": 0, "Both": 1, "Player": 2}

    def sort_key(r):
        status_priority = 0 if r.status == "pending" else 1  # pending first, hold bottom
        return (
            status_priority,
            r.primary_ruleset or "",
            role_order.get(r.user_role, 99),
            r.queue_sort_ts or r.created_at,
        )

    access_requests.sort(key=sort_key)

    audit_logger.info(f"Keys view | Admin ID: {current_user.id}")
    return render_template(
        "admin/keys.html",
        keys=keys,
        stats=stats,
        access_requests=access_requests,
    )


def handle_generate_bulk():
    """Generate 1-50 keys; commit; audit; redirect."""
    try:
        count = int(request.form.get("count", 5))
    except (TypeError, ValueError):
        count = 5
    count = max(1, min(50, count))
    # Legacy/bulk keys are not tied to an applicant email.
    create_bulk_keys(count, email=None)
    db.session.commit()
    audit_logger.info(
        f"Keys generated | Admin ID: {current_user.id} | Count: {count}"
    )
    flash(f"Generated {count} new keys.", "success")
    return redirect(url_for("admin.keys_overview"))


def handle_access_requests_overview():
    """
    List pending/hold access requests as triage cards.
    Sorting follows: primary_ruleset then role priority, with Hold always moved to bottom.
    """
    # Only show requests that are actionable right now.
    requests_q = (
        AccessRequest.query.filter(AccessRequest.status.in_(["pending", "hold"]))
        .order_by(
            AccessRequest.queue_sort_ts.asc(),
        )
        .all()
    )

    # Compute deterministic triage ordering in python to match the plan rules.
    role_order = {"GM": 0, "Both": 1, "Player": 2}

    def sort_key(r):
        status_priority = 0 if r.status == "pending" else 1  # pending first, hold bottom
        return (
            status_priority,
            r.primary_ruleset or "",
            role_order.get(r.user_role, 99),
            r.queue_sort_ts or r.created_at,
        )

    requests_q.sort(key=sort_key)

    return render_template(
        "admin/access_requests.html",
        access_requests=requests_q,
    )


def _generate_unique_vault_key():
    # Generate codes similar to FORGE-XXXX-XXXX style and ensure uniqueness in DB.
    while True:
        # Keep format compatible with the existing registration placeholder.
        code = generate_secure_code(prefix="FORGE", segments=2, segment_len=4)
        exists = (
            RegistrationKey.query.filter_by(key_code=code).first()
            or AccessRequest.query.filter_by(vault_key=code).first()
        )
        if not exists:
            return code


def handle_approve_access_request(request_id):
    """Approve: generate vault key, issue it to the applicant, and send email."""
    ar = AccessRequest.query.get_or_404(request_id)
    ar.status = "approved"

    # Generate vault key and store it.
    vault_key = _generate_unique_vault_key()
    ar.vault_key = vault_key
    ar.vault_key_used = False

    from datetime import datetime

    ar.processed_at = datetime.utcnow()

    # Create a usable registration key tied to applicant email.
    # This enables /register to validate that the used key matches the email submitted.
    reg_key = RegistrationKey(key_code=vault_key, email=ar.email, is_used=False)
    db.session.add(reg_key)

    # Commit key issuance before attempting email.
    db.session.commit()

    # Trigger approval email with pre-filled registration link.
    try:
        from flask_mailman import EmailMessage
        from app.extensions import mail

        sender = current_app.config.get("MAIL_DEFAULT_SENDER", "noreply@example.com")
        reg_link = url_for("main.register_alias", vault_key=vault_key, _external=True)
        subject = "Econo-Forge Access Approved"
        discord_link = "https://discord.gg/dkNVnBXMMB"
        body = f"""Request Received. We're currently prioritizing by Ruleset for our Early Acces. Join the Discord {discord_link} for real-time updates.\n\nYour vault key:\n{vault_key}\n\nRegister For Access link:\n{reg_link}\n\nStep-by-step:\n1) Click the Register For Access link in the email.\n2) Confirm the registration page is pre-filled with your vault key (or paste the key above).\n3) Verify the email address matches the one you entered in your request.\n4) Submit the registration form.\n5) After successful registration, proceed to Login.\n"""

        # #region agent log
        _debug_log(
            hypothesis_id="A",
            location="admin_handler:handle_approve_access_request:build_email_body",
            message="Approval email body constructed",
            data={
                "access_request_id": ar.id,
                "has_step_by_step": ("Step-by-step" in body),
                "has_discord_link": (discord_link in body),
                "has_early_acces_phrase": ("Early Acces" in body),
                "body_len": len(body),
                "applicant_email_set": bool(ar.email),
            },
        )
        # #endregion

        msg = EmailMessage(subject, body, sender, [ar.email])
        msg.send()

        # #region agent log
        _debug_log(
            hypothesis_id="B",
            location="admin_handler:handle_approve_access_request:send_email",
            message="Approval email send completed",
            data={"access_request_id": ar.id, "applicant_email_set": bool(ar.email)},
        )
        # #endregion
    except Exception as e:
        # #region agent log
        _debug_log(
            hypothesis_id="B",
            location="admin_handler:handle_approve_access_request:send_email_error",
            message="Approval email send failed",
            data={"access_request_id": ar.id, "error_type": e.__class__.__name__},
        )
        # #endregion
        audit_logger.warning(f"Approval email failed | AccessRequest ID: {ar.id} | Error: {e}")

    flash("Access request approved. Vault key issued.", "success")
    return redirect(url_for("admin.keys_overview"))


def handle_hold_access_request(request_id):
    """Hold: move the card to the bottom of current rank order (no email)."""
    ar = AccessRequest.query.get_or_404(request_id)
    ar.status = "hold"
    from datetime import datetime

    ar.queue_sort_ts = datetime.utcnow()
    db.session.commit()
    flash("Access request held (moved to bottom).", "info")
    return redirect(url_for("admin.keys_overview"))


def handle_reject_access_request(request_id):
    """Reject: remove from actionable list; do not send email."""
    ar = AccessRequest.query.get_or_404(request_id)
    ar.status = "rejected"
    from datetime import datetime

    ar.processed_at = datetime.utcnow()
    db.session.commit()
    flash("Access request rejected.", "warning")
    return redirect(url_for("admin.keys_overview"))


def handle_reveal_key(key_id):
    """Return key_code as JSON only for unused keys; audit each reveal."""
    key_row = RegistrationKey.query.get_or_404(key_id)
    audit_logger.info(
        f"Key Reveal | Admin ID: {current_user.id} | Key ID: {key_id}"
    )
    if key_row.is_used:
        return jsonify({"error": "Key already used"}), 400
    return jsonify({"key_code": key_row.key_code})
