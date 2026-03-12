"""Admin Bastion: key management. GM-only; 404 for non-admins; audit to file."""
import os
import logging
from logging.handlers import RotatingFileHandler
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import current_user

from app.extensions import db
from app.models.users import RegistrationKey
from app.services.key_generator import create_bulk_keys

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
    audit_logger.info(f"Keys view | Admin ID: {current_user.id}")
    return render_template(
        "admin/keys.html",
        keys=keys,
        stats=stats,
    )


def handle_generate_bulk():
    """Generate 1-50 keys; commit; audit; redirect."""
    try:
        count = int(request.form.get("count", 5))
    except (TypeError, ValueError):
        count = 5
    count = max(1, min(50, count))
    create_bulk_keys(count)
    db.session.commit()
    audit_logger.info(
        f"Keys generated | Admin ID: {current_user.id} | Count: {count}"
    )
    flash(f"Generated {count} new keys.", "success")
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
