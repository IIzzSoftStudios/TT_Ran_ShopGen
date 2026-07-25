"""Paid subscription Checkout, success bridge, Customer Portal, Stripe webhooks."""

from __future__ import annotations

import logging
import os

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from app.extensions import csrf, db, limiter
from app.models import RegistrationKey
from app.services.entitlements import (
    is_allowed_price,
    plan_slug_for_price,
    price_allowlist,
)
from app.services.stripe_client import (
    construct_webhook_event,
    create_billing_portal_session,
    create_checkout_session,
    publishable_key,
    retrieve_checkout_session,
)
from stripe import SignatureVerificationError
from app.services.stripe_webhooks import process_stripe_event

log = logging.getLogger(__name__)

billing_bp = Blueprint("billing", __name__)


def _price_catalog_for_template() -> list[dict]:
    allow = price_allowlist()
    labels = {
        "STRIPE_PRICE_TIER1_MONTHLY": ("Tier 1", "Monthly", "$10", "mo"),
        "STRIPE_PRICE_TIER1_YEARLY": ("Tier 1", "Yearly", "$100", "yr"),
        "STRIPE_PRICE_PRO_MONTHLY": ("Pro", "Monthly", "$30", "mo"),
        "STRIPE_PRICE_PRO_YEARLY": ("Pro", "Yearly", "$300", "yr"),
    }
    plans = []
    for env_key, (tier, interval, amount, per) in labels.items():
        pid = (os.getenv(env_key) or "").strip()
        if not pid or pid not in allow:
            continue
        slug = allow[pid]
        is_pro = slug == "pro"
        plans.append(
            {
                "price_id": pid,
                "tier": tier,
                "interval": interval,
                "interval_key": interval.lower(),
                "amount_label": amount,
                "amount_per": per,
                "plan_slug": slug,
                "featured": is_pro,
                "campaigns_label": "5 campaigns" if is_pro else "1 campaign",
                "seats_label": (
                    "Unlimited player seats" if is_pro else "5 player seats"
                ),
            }
        )
    return plans


@billing_bp.route("/subscribe", methods=["GET"])
def subscribe():
    plans = _price_catalog_for_template()
    return render_template(
        "subscribe.html",
        plans=plans,
        stripe_configured=bool((os.getenv("STRIPE_SECRET_KEY") or "").strip()),
        publishable_key=publishable_key(),
    )


@billing_bp.route("/create-checkout-session", methods=["POST"])
@limiter.limit("30 per hour; 10 per minute")
def create_checkout():
    price_id = (request.form.get("price_id") or "").strip()
    email = (request.form.get("email") or "").strip().lower() or None
    if not is_allowed_price(price_id):
        flash("Invalid plan selection.", "danger")
        return redirect(url_for("billing.subscribe"))
    if not (os.getenv("STRIPE_SECRET_KEY") or "").strip():
        flash("Billing is not configured yet. Please try again later.", "warning")
        return redirect(url_for("billing.subscribe"))

    plan_slug = plan_slug_for_price(price_id) or "tier1"
    success_url = url_for(
        "billing.subscribe_success",
        _external=True,
    ) + "?session_id={CHECKOUT_SESSION_ID}"
    cancel_url = url_for("billing.subscribe", _external=True)
    try:
        session_obj = create_checkout_session(
            price_id=price_id,
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=email,
            metadata={"price_id": price_id, "plan_slug": plan_slug},
        )
    except Exception:
        log.exception("create_checkout_session failed")
        flash("Could not start checkout. Please try again.", "danger")
        return redirect(url_for("billing.subscribe"))
    return redirect(session_obj.url, code=303)


@billing_bp.route("/subscribe/success", methods=["GET"])
def subscribe_success():
    session_id = (request.args.get("session_id") or "").strip()
    if not session_id:
        flash("Missing checkout session.", "warning")
        return redirect(url_for("billing.subscribe"))

    vault_key = None
    email = None
    try:
        sess = retrieve_checkout_session(session_id)
        email = (
            getattr(getattr(sess, "customer_details", None), "email", None)
            or getattr(sess, "customer_email", None)
            or ""
        )
        email = (email or "").strip().lower() or None
        key = RegistrationKey.query.filter_by(
            stripe_checkout_session_id=session_id
        ).first()
        if key is None:
            # Webhook may not have arrived yet — synthesize key from session.
            from app.services.entitlements import issue_paid_registration_key

            customer_id = sess.customer
            if hasattr(customer_id, "id"):
                customer_id = customer_id.id
            sub_id = sess.subscription
            if hasattr(sub_id, "id"):
                sub_id = sub_id.id
            meta = sess.metadata or {}
            price_id = meta.get("price_id") or ""
            plan_slug = meta.get("plan_slug") or plan_slug_for_price(price_id) or "tier1"
            if customer_id and sub_id:
                key = issue_paid_registration_key(
                    email=email or "",
                    plan_slug=plan_slug,
                    stripe_customer_id=str(customer_id),
                    stripe_subscription_id=str(sub_id),
                    stripe_price_id=str(price_id),
                    stripe_checkout_session_id=session_id,
                )
                db.session.commit()
        if key is not None:
            vault_key = key.key_code
            email = email or key.email
    except Exception:
        log.exception("subscribe_success session retrieve failed")
        flash(
            "Payment received, but we could not finish setup automatically. "
            "If you have a confirmation email, use that registration key.",
            "warning",
        )
        return redirect(url_for("auth.register"))

    if not vault_key:
        flash(
            "Payment is processing. You will receive a registration key shortly.",
            "info",
        )
        return redirect(url_for("auth.register"))

    return redirect(
        url_for("auth.register", vault_key=vault_key, email=email or "")
    )


@billing_bp.route("/create-portal-session", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def create_portal():
    customer_id = getattr(current_user, "stripe_customer_id", None)
    if not customer_id:
        flash("No billing account is linked to this login yet.", "warning")
        return redirect(url_for("billing.billing_settings"))
    try:
        portal = create_billing_portal_session(
            customer_id=customer_id,
            return_url=url_for("billing.billing_settings", _external=True),
        )
    except Exception:
        log.exception("create_billing_portal_session failed")
        flash("Could not open the billing portal. Please try again.", "danger")
        return redirect(url_for("billing.billing_settings"))
    return redirect(portal.url, code=303)


@billing_bp.route("/billing/settings", methods=["GET"])
@login_required
def billing_settings():
    from app.services.billing_rules import get_gm_limits, resolve_phase_slug
    from app.models import BillingSubscription
    from app.services.billing_rules import ACTIVE_SUB_STATUSES

    phase = resolve_phase_slug(current_user)
    cap, seats, label = get_gm_limits(current_user)
    sub = (
        BillingSubscription.query.filter(
            BillingSubscription.user_id == current_user.id,
            BillingSubscription.status.in_(tuple(ACTIVE_SUB_STATUSES)),
        )
        .order_by(BillingSubscription.updated_at.desc())
        .first()
    )
    return render_template(
        "billing_settings.html",
        phase_slug=phase,
        plan_label=label,
        campaign_limit=cap,
        seat_limit=seats,
        subscription=sub,
        plans=_price_catalog_for_template(),
        has_customer=bool(getattr(current_user, "stripe_customer_id", None)),
    )


@billing_bp.route("/webhook/stripe", methods=["POST"])
@csrf.exempt
@limiter.limit("120 per minute")
def stripe_webhook():
    payload = request.get_data(cache=False)
    sig = request.headers.get("Stripe-Signature", "")
    try:
        event = construct_webhook_event(payload, sig)
    except ValueError:
        return ("Invalid payload", 400)
    except SignatureVerificationError:
        return ("Invalid signature", 400)
    except RuntimeError as e:
        log.error("Webhook misconfigured: %s", e)
        return ("Webhook not configured", 503)
    try:
        process_stripe_event(event)
    except Exception:
        log.exception("Webhook processing failed")
        db.session.rollback()
        return ("Handler error", 500)
    return ("", 200)
