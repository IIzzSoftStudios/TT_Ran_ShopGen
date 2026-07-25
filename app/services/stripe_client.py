"""Stripe SDK helpers for Managed Payments Checkout and Customer Portal."""

from __future__ import annotations

import os
from typing import Any, Optional

import stripe
from flask import current_app

# Request-level API version for Managed Payments (blueprint).
MANAGED_PAYMENTS_STRIPE_VERSION = "2026-02-25.preview"


def _secret_key() -> str:
    key = (os.getenv("STRIPE_SECRET_KEY") or "").strip()
    if not key:
        raise RuntimeError("STRIPE_SECRET_KEY is not configured")
    return key


def get_stripe() -> stripe:
    """Configure and return the stripe module (global API key; no default API version)."""
    stripe.api_key = _secret_key()
    return stripe


def create_checkout_session(
    *,
    price_id: str,
    success_url: str,
    cancel_url: str,
    customer_email: Optional[str] = None,
    client_reference_id: Optional[str] = None,
    metadata: Optional[dict[str, str]] = None,
) -> Any:
    """Create a subscription Checkout Session with Managed Payments enabled."""
    get_stripe()
    params: dict[str, Any] = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "managed_payments": {"enabled": True},
    }
    if customer_email:
        params["customer_email"] = customer_email
    if client_reference_id:
        params["client_reference_id"] = client_reference_id
    if metadata:
        params["metadata"] = metadata
    return stripe.checkout.Session.create(
        **params,
        stripe_version=MANAGED_PAYMENTS_STRIPE_VERSION,
    )


def retrieve_checkout_session(session_id: str) -> Any:
    get_stripe()
    return stripe.checkout.Session.retrieve(
        session_id,
        expand=["subscription", "customer"],
    )


def create_billing_portal_session(*, customer_id: str, return_url: str) -> Any:
    get_stripe()
    return stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )


def construct_webhook_event(payload: bytes, sig_header: str) -> Any:
    secret = (os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip()
    if not secret:
        raise RuntimeError("STRIPE_WEBHOOK_SECRET is not configured")
    get_stripe()
    return stripe.Webhook.construct_event(payload, sig_header, secret)


def publishable_key() -> str:
    return (os.getenv("STRIPE_PUBLISHABLE_KEY") or "").strip()
