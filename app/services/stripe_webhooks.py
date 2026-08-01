"""Stripe webhook handlers — idempotent entitlement sync."""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from app.extensions import db
from app.models import BillingSubscription, StripeWebhookEvent, User
from app.services.entitlements import (
    extract_price_id_from_subscription,
    issue_paid_registration_key,
    plan_slug_for_price,
    upsert_billing_subscription,
)
from app.services.stripe_client import expects_live_mode

log = logging.getLogger(__name__)


def _already_processed(event_id: str) -> bool:
    return db.session.get(StripeWebhookEvent, event_id) is not None


def _mark_processed(event_id: str, event_type: str) -> None:
    db.session.add(StripeWebhookEvent(id=event_id, event_type=event_type))


def _event_livemode(event: Any) -> Optional[bool]:
    value = (
        event.get("livemode")
        if isinstance(event, dict)
        else getattr(event, "livemode", None)
    )
    return None if value is None else bool(value)


def _obj(data: Any) -> dict:
    if isinstance(data, dict):
        return data
    if hasattr(data, "to_dict"):
        return data.to_dict()
    return dict(data)


def handle_checkout_session_completed(session_obj: Any) -> None:
    sess = _obj(session_obj)
    session_id = sess.get("id")
    customer_id = sess.get("customer")
    if isinstance(customer_id, dict):
        customer_id = customer_id.get("id")
    subscription_id = sess.get("subscription")
    if isinstance(subscription_id, dict):
        subscription_id = subscription_id.get("id")
    email = (
        (sess.get("customer_details") or {}).get("email")
        or sess.get("customer_email")
        or ""
    )
    email = (email or "").strip().lower()
    metadata = sess.get("metadata") or {}
    price_id = metadata.get("price_id")
    plan_slug = metadata.get("plan_slug") or plan_slug_for_price(price_id)

    if not plan_slug and subscription_id:
        # Best-effort: subscription sync may fill later.
        plan_slug = plan_slug_for_price(price_id)

    if not session_id or not customer_id or not subscription_id:
        log.warning(
            "checkout.session.completed missing ids session=%s customer=%s sub=%s",
            session_id,
            customer_id,
            subscription_id,
        )
        return

    if not plan_slug:
        plan_slug = "tier1"
    if not price_id:
        price_id = metadata.get("price_id") or ""

    issue_paid_registration_key(
        email=email,
        plan_slug=plan_slug,
        stripe_customer_id=str(customer_id),
        stripe_subscription_id=str(subscription_id),
        stripe_price_id=str(price_id or ""),
        stripe_checkout_session_id=str(session_id),
    )
    upsert_billing_subscription(
        stripe_subscription_id=str(subscription_id),
        stripe_customer_id=str(customer_id),
        stripe_price_id=str(price_id or "unknown"),
        plan_slug=plan_slug,
        status="active",
        user_id=None,
    )


def handle_subscription_event(sub_obj: Any, *, deleted: bool = False) -> None:
    sub = _obj(sub_obj)
    sub_id = sub.get("id")
    customer_id = sub.get("customer")
    if isinstance(customer_id, dict):
        customer_id = customer_id.get("id")
    price_id = extract_price_id_from_subscription(sub)
    plan_slug = plan_slug_for_price(price_id) or "tier1"
    status = "canceled" if deleted else (sub.get("status") or "incomplete")
    period_end = sub.get("current_period_end")

    user_id = None
    if customer_id:
        user = User.query.filter_by(stripe_customer_id=str(customer_id)).first()
        if user is not None:
            user_id = user.id

    if not sub_id or not customer_id:
        return

    upsert_billing_subscription(
        stripe_subscription_id=str(sub_id),
        stripe_customer_id=str(customer_id),
        stripe_price_id=str(price_id or "unknown"),
        plan_slug=plan_slug,
        status=status,
        current_period_end=period_end,
        user_id=user_id,
    )


def handle_invoice_payment_failed(invoice_obj: Any) -> None:
    inv = _obj(invoice_obj)
    sub_id = inv.get("subscription")
    if isinstance(sub_id, dict):
        sub_id = sub_id.get("id")
    if not sub_id:
        return
    row = BillingSubscription.query.filter_by(
        stripe_subscription_id=str(sub_id)
    ).first()
    if row is not None:
        row.status = "past_due"


def process_stripe_event(event: Any) -> bool:
    """
    Process a verified Stripe event.
    Returns False if the event is a duplicate or was rejected for mode mismatch,
    True if handled (or acknowledged).
    """
    event_id = event["id"] if isinstance(event, dict) else event.id
    event_type = event["type"] if isinstance(event, dict) else event.type
    data_object = (
        event["data"]["object"]
        if isinstance(event, dict)
        else event.data.object
    )

    livemode = _event_livemode(event)
    if livemode is not None and livemode is not expects_live_mode():
        # A sandbox/test event must never grant paid entitlements in production,
        # and a live event must never be replayed into a non-production stack.
        # Swallow it (caller returns 200) so Stripe stops retrying.
        log.critical(
            "Rejected Stripe event id=%s type=%s: livemode=%s does not match "
            "FLASK_ENV=%s. No entitlements granted.",
            event_id,
            event_type,
            livemode,
            os.getenv("FLASK_ENV", "development"),
        )
        return False

    if _already_processed(str(event_id)):
        return False

    if event_type == "checkout.session.completed":
        handle_checkout_session_completed(data_object)
    elif event_type in (
        "customer.subscription.created",
        "customer.subscription.updated",
    ):
        handle_subscription_event(data_object, deleted=False)
    elif event_type == "customer.subscription.deleted":
        handle_subscription_event(data_object, deleted=True)
    elif event_type == "invoice.payment_failed":
        handle_invoice_payment_failed(data_object)
    else:
        log.info("Ignoring Stripe event type=%s id=%s", event_type, event_id)

    _mark_processed(str(event_id), str(event_type))
    db.session.commit()
    return True
