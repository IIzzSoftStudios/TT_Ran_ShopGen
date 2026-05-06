"""Admin vault: registration keys and access request triage."""
from __future__ import annotations

import logging
from datetime import datetime

from flask import (
    render_template,
    redirect,
    url_for,
    flash,
    request,
    jsonify,
    current_app,
)
from flask_login import current_user

from app.extensions import db
from app.models import RegistrationKey, AccessRequest
from app.services.key_generator import create_bulk_keys, generate_secure_code

audit_logger = logging.getLogger("admin_audit")


def handle_admin_keys():
    keys = (
        RegistrationKey.query.filter_by(is_admin_test_key=False)
        .order_by(RegistrationKey.created_at.desc())
        .all()
    )
    admin_keys = (
        RegistrationKey.query.filter_by(is_admin_test_key=True)
        .order_by(RegistrationKey.created_at.desc())
        .all()
    )
    stats = {
        "total": len(keys),
        "used": sum(1 for k in keys if k.is_used),
        "available": sum(1 for k in keys if not k.is_used),
    }
    admin_stats = {
        "total": len(admin_keys),
        "used": sum(1 for k in admin_keys if k.is_used),
        "available": sum(1 for k in admin_keys if not k.is_used),
    }
    access_requests = (
        AccessRequest.query.filter(AccessRequest.status.in_(["pending", "hold"])).all()
    )
    role_order = {"GM": 0, "Both": 1, "Player": 2}

    def sort_key(r):
        status_priority = 0 if r.status == "pending" else 1
        return (
            status_priority,
            r.primary_ruleset or "",
            role_order.get(r.user_role, 99),
            r.queue_sort_ts or r.created_at,
        )

    access_requests.sort(key=sort_key)
    pc = current_app.extensions["phase_config"]
    vault_phase_slugs = pc.list_phases(include_internal=False)
    all_phase_slugs = pc.list_phases(include_internal=True)
    audit_logger.info("Keys view | Admin ID: %s", current_user.id)
    return render_template(
        "admin/keys.html",
        keys=keys,
        admin_keys=admin_keys,
        stats=stats,
        admin_stats=admin_stats,
        access_requests=access_requests,
        vault_phase_slugs=vault_phase_slugs,
        all_phase_slugs=all_phase_slugs,
    )


def _validate_phase_slug(selected: str | None) -> str | None:
    """Return normalized slug or None if invalid."""
    if not selected or not str(selected).strip():
        return None
    slug = str(selected).strip()
    pc = current_app.extensions["phase_config"]
    if slug not in pc.list_phases(include_internal=True):
        return None
    return slug


def handle_generate_bulk():
    selected_phase = _validate_phase_slug(request.form.get("key_phase"))
    if selected_phase is None:
        flash("Invalid phase selection.", "error")
        return redirect(url_for("admin.keys_overview"))
    try:
        count = int(request.form.get("count", 5))
    except (TypeError, ValueError):
        count = 5
    count = max(1, min(50, count))
    try:
        create_bulk_keys(count, email=None, is_admin_test_key=False, phase_slug=selected_phase)
    except ValueError:
        flash("Invalid phase selection.", "error")
        return redirect(url_for("admin.keys_overview"))
    db.session.commit()
    audit_logger.info(
        "Keys generated | Admin ID: %s | Count: %s | Phase: %s",
        current_user.id,
        count,
        selected_phase,
    )
    flash(f"Generated {count} new keys ({selected_phase}).", "success")
    return redirect(url_for("admin.keys_overview"))


def handle_generate_admin_test_keys():
    try:
        count = int(request.form.get("count", 3))
    except (TypeError, ValueError):
        count = 3
    count = max(1, min(20, count))
    create_bulk_keys(count, email=None, is_admin_test_key=True)
    db.session.commit()
    audit_logger.info(
        "Admin test keys generated | Admin ID: %s | Count: %s", current_user.id, count
    )
    flash(f"Generated {count} admin test key(s).", "success")
    return redirect(url_for("admin.keys_overview"))


def _generate_unique_vault_key(phase_slug: str) -> str:
    pc = current_app.extensions["phase_config"]
    row = pc.get_phase(phase_slug)
    prefix = row["prefix"]
    while True:
        code = generate_secure_code(prefix=prefix, segments=2, segment_len=4)
        exists = RegistrationKey.query.filter_by(key_code=code).first() or AccessRequest.query.filter_by(
            vault_key=code
        ).first()
        if not exists:
            return code


def handle_approve_access_request(request_id):
    ar = AccessRequest.query.get_or_404(request_id)
    selected_phase = _validate_phase_slug(request.form.get("key_phase"))
    if selected_phase is None:
        flash("Invalid phase selection.", "error")
        return redirect(url_for("admin.keys_overview"))

    ar.status = "approved"
    vault_key = _generate_unique_vault_key(selected_phase)
    ar.vault_key = vault_key
    ar.vault_key_used = False
    ar.processed_at = datetime.utcnow()
    reg_key = RegistrationKey(
        key_code=vault_key,
        email=ar.email,
        is_used=False,
        key_phase=selected_phase,
        is_admin_test_key=False,
    )
    db.session.add(reg_key)
    db.session.commit()

    try:
        from flask_mailman import EmailMessage

        sender = current_app.config.get("MAIL_DEFAULT_SENDER", "noreply@example.com")
        reg_link = url_for("main.register_alias", vault_key=vault_key, _external=True)
        subject = "Econo-Forge Access Approved"
        discord_link = "https://discord.gg/dkNVnBXMMB"
        body = (
            f"Request Received. We're currently prioritizing by Ruleset for our Early Acces. "
            f"Join the Discord {discord_link} for real-time updates.\n\nYour vault key:\n{vault_key}\n\n"
            f"Register For Access link:\n{reg_link}\n"
        )
        msg = EmailMessage(subject, body, sender, [ar.email])
        msg.send()
    except Exception as e:
        audit_logger.warning("Approval email failed | AccessRequest ID: %s | Error: %s", ar.id, e)

    flash("Access request approved. Vault key issued.", "success")
    return redirect(url_for("admin.keys_overview"))


def handle_hold_access_request(request_id):
    ar = AccessRequest.query.get_or_404(request_id)
    ar.status = "hold"
    ar.queue_sort_ts = datetime.utcnow()
    db.session.commit()
    flash("Access request held (moved to bottom).", "info")
    return redirect(url_for("admin.keys_overview"))


def handle_reject_access_request(request_id):
    ar = AccessRequest.query.get_or_404(request_id)
    ar.status = "rejected"
    ar.processed_at = datetime.utcnow()
    db.session.commit()
    flash("Access request rejected.", "warning")
    return redirect(url_for("admin.keys_overview"))


def handle_reveal_key(key_id):
    key_row = RegistrationKey.query.get_or_404(key_id)
    audit_logger.info("Key Reveal | Admin ID: %s | Key ID: %s", current_user.id, key_id)
    if key_row.is_used:
        return jsonify({"error": "Key already used"}), 400
    return jsonify({"key_code": key_row.key_code})
