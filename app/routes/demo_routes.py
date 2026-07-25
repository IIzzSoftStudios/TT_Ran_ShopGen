"""Public Demo entry: anonymous snapshot restore."""

from flask import Blueprint, flash, redirect, url_for

from app.extensions import limiter
from app.services.demo_session import start_anonymous_demo

demo_bp = Blueprint("demo", __name__)


@demo_bp.route("/demo", methods=["GET"])
@limiter.limit("20 per hour; 5 per minute")
def start():
    """Provision a private Demo from the immutable snapshot and open GM home."""
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
