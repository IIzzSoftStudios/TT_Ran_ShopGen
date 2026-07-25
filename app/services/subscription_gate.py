"""Server-side mutation gate for canceled / lapsed Stripe subscribers."""

from __future__ import annotations

from typing import Any

from flask import flash, jsonify, redirect, request, url_for
from flask_login import current_user

from app.services.billing_rules import requires_resubscribe_gate
from app.services.demo_session import active_demo_mode_for_user

# Endpoints that must stay usable so the user can resubscribe or leave.
_MUTATION_ALLOWLIST = frozenset(
    {
        "billing.create_checkout",
        "billing.create_portal",
        "billing.stripe_webhook",
        "billing.subscribe",
        "billing.subscribe_success",
        "billing.billing_settings",
        "auth.logout",
        "auth.login",
        "auth.register",
        "auth.forgot_password",
        "auth.reset_password",
        "main.healthz",
        "main.ready",
    }
)

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

LAPSED_JSON_MESSAGE = (
    "Your subscription is no longer active. Subscribe again to continue."
)
LAPSED_FLASH_MESSAGE = (
    "Your subscription ended. Subscribe again to keep using your campaigns."
)


def subscription_lapsed_for_request() -> bool:
    """Whether the current request should treat the user as subscription-lapsed."""
    if not getattr(current_user, "is_authenticated", False):
        return False
    if active_demo_mode_for_user(current_user):
        return False
    return requires_resubscribe_gate(current_user)


def resubscribe_cta_url() -> str:
    if getattr(current_user, "stripe_customer_id", None):
        return url_for("billing.billing_settings")
    return url_for("billing.subscribe")


def maybe_block_lapsed_mutation() -> Any:
    """
    Block non-safe HTTP methods for lapsed subscribers except billing/auth allowlist.
    Returns a response to short-circuit the request, or None to continue.
    """
    if request.method in _SAFE_METHODS:
        return None
    endpoint = request.endpoint or ""
    if endpoint in _MUTATION_ALLOWLIST or endpoint.startswith("static"):
        return None
    if not subscription_lapsed_for_request():
        return None

    wants_json = (
        request.path.startswith("/api/")
        or request.accept_mimetypes.best == "application/json"
        or (
            request.content_type
            and "application/json" in request.content_type
        )
    )
    if wants_json or request.path.startswith("/api/"):
        return jsonify(
            {
                "error": LAPSED_JSON_MESSAGE,
                "code": "subscription_lapsed",
                "subscribe_url": resubscribe_cta_url(),
            }
        ), 403

    flash(LAPSED_FLASH_MESSAGE, "warning")
    return redirect(resubscribe_cta_url())
