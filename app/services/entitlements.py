"""Map Stripe prices to plan slugs and sync BillingSubscription rows."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

from flask import current_app, has_app_context

from app.extensions import db
from app.models import BillingSubscription, RegistrationKey, User
from app.services.key_generator import generate_secure_code

PLAN_TIER1 = "tier1"
PLAN_ADVENTURER = "adventurer"
PLAN_PRO = "pro"
PLAN_SLUGS = frozenset({PLAN_TIER1, PLAN_ADVENTURER, PLAN_PRO})

# Env var → plan slug (Checkout allowlist + webhook resolution).
PRICE_ENV_KEYS = (
    ("STRIPE_PRICE_TIER1_MONTHLY", PLAN_TIER1),
    ("STRIPE_PRICE_TIER1_YEARLY", PLAN_TIER1),
    ("STRIPE_PRICE_ADVENTURER_MONTHLY", PLAN_ADVENTURER),
    ("STRIPE_PRICE_ADVENTURER_YEARLY", PLAN_ADVENTURER),
    ("STRIPE_PRICE_PRO_MONTHLY", PLAN_PRO),
    ("STRIPE_PRICE_PRO_YEARLY", PLAN_PRO),
)

# Display metadata for /subscribe (amount labels are cosmetic; Stripe charges the Price).
PRICE_DISPLAY_CATALOG = (
    ("STRIPE_PRICE_TIER1_MONTHLY", PLAN_TIER1, "Casual Tier", "Monthly", "$6.99", "mo"),
    ("STRIPE_PRICE_TIER1_YEARLY", PLAN_TIER1, "Casual Tier", "Yearly", "$69.99", "yr"),
    (
        "STRIPE_PRICE_ADVENTURER_MONTHLY",
        PLAN_ADVENTURER,
        "Adventurer Plan",
        "Monthly",
        "$10",
        "mo",
    ),
    (
        "STRIPE_PRICE_ADVENTURER_YEARLY",
        PLAN_ADVENTURER,
        "Adventurer Plan",
        "Yearly",
        "$100",
        "yr",
    ),
    ("STRIPE_PRICE_PRO_MONTHLY", PLAN_PRO, "Pro Tier", "Monthly", "$30", "mo"),
    ("STRIPE_PRICE_PRO_YEARLY", PLAN_PRO, "Pro Tier", "Yearly", "$300", "yr"),
)


def price_allowlist() -> dict[str, str]:
    """Return {price_id: plan_slug} from env (empty entries skipped)."""
    out: dict[str, str] = {}
    for env_key, slug in PRICE_ENV_KEYS:
        pid = (os.getenv(env_key) or "").strip()
        if pid:
            out[pid] = slug
    return out


def plan_slug_for_price(price_id: str | None) -> Optional[str]:
    if not price_id:
        return None
    return price_allowlist().get(str(price_id).strip())


def is_allowed_price(price_id: str | None) -> bool:
    return plan_slug_for_price(price_id) is not None


def _campaigns_label(campaign_limit: int) -> str:
    n = int(campaign_limit or 0)
    word = "campaign" if n == 1 else "campaigns"
    return f"{n} {word}"


def _seats_label(seat_limit: int | None) -> str:
    if seat_limit is None:
        return "Unlimited player seats"
    n = int(seat_limit)
    word = "seat" if n == 1 else "seats"
    return f"{n} player {word} per campaign"


def subscription_plans_for_display() -> list[dict[str, Any]]:
    """Build subscribe-page plan cards from env price IDs + phase entitlements."""
    allow = price_allowlist()
    pc = (
        current_app.extensions.get("phase_config")
        if has_app_context()
        else None
    )
    plans: list[dict[str, Any]] = []
    for (
        env_key,
        slug,
        tier,
        interval,
        amount,
        per,
    ) in PRICE_DISPLAY_CATALOG:
        pid = (os.getenv(env_key) or "").strip()
        if not pid or pid not in allow:
            continue
        if pc is not None:
            phase = pc.get_phase(slug)
            cap = int(phase.get("campaign_limit") or 1)
            seats = phase.get("seat_limit")
        elif slug == PLAN_PRO:
            cap, seats = 5, None
        elif slug == PLAN_ADVENTURER:
            cap, seats = 3, 7
        else:
            cap, seats = 1, 5
        plans.append(
            {
                "price_id": pid,
                "tier": tier,
                "interval": interval,
                "interval_key": interval.lower(),
                "amount_label": amount,
                "amount_per": per,
                "plan_slug": slug,
                "featured": slug == PLAN_PRO,
                "campaigns_label": _campaigns_label(cap),
                "seats_label": _seats_label(seats),
            }
        )
    return plans


def _ts_to_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError, OSError):
        return None


def upsert_billing_subscription(
    *,
    stripe_subscription_id: str,
    stripe_customer_id: str,
    stripe_price_id: str,
    plan_slug: str,
    status: str,
    current_period_end: Any = None,
    user_id: Optional[int] = None,
) -> BillingSubscription:
    row = BillingSubscription.query.filter_by(
        stripe_subscription_id=stripe_subscription_id
    ).first()
    if row is None:
        row = BillingSubscription(
            stripe_subscription_id=stripe_subscription_id,
            stripe_customer_id=stripe_customer_id,
            stripe_price_id=stripe_price_id,
            plan_slug=plan_slug,
            status=status or "incomplete",
        )
        db.session.add(row)
    else:
        row.stripe_customer_id = stripe_customer_id
        row.stripe_price_id = stripe_price_id
        row.plan_slug = plan_slug
        row.status = status or row.status
    if user_id is not None:
        row.user_id = user_id
    pe = _ts_to_dt(current_period_end)
    if pe is not None:
        row.current_period_end = pe
    row.updated_at = datetime.utcnow()
    return row


def issue_paid_registration_key(
    *,
    email: str,
    plan_slug: str,
    stripe_customer_id: str,
    stripe_subscription_id: str,
    stripe_price_id: str,
    stripe_checkout_session_id: str,
) -> RegistrationKey:
    """Create an unused RegistrationKey for post-Checkout account creation."""
    from flask import current_app

    existing = RegistrationKey.query.filter_by(
        stripe_checkout_session_id=stripe_checkout_session_id
    ).first()
    if existing is not None:
        return existing

    pc = current_app.extensions["phase_config"]
    row = pc.get_phase(plan_slug)
    prefix = row.get("prefix") or "TIER1"
    while True:
        code = generate_secure_code(prefix=prefix, segments=2, segment_len=4)
        if RegistrationKey.query.filter_by(key_code=code).first() is None:
            break
    key = RegistrationKey(
        key_code=code,
        email=(email or "").strip().lower() or None,
        key_phase=plan_slug,
        is_admin_test_key=False,
        is_used=False,
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
        stripe_price_id=stripe_price_id,
        stripe_checkout_session_id=stripe_checkout_session_id,
    )
    db.session.add(key)
    return key


def attach_subscription_to_user(user: User, key_row: RegistrationKey) -> None:
    """Copy Stripe IDs from a paid key onto the user and subscription row."""
    if key_row.stripe_customer_id:
        user.stripe_customer_id = key_row.stripe_customer_id
    if key_row.stripe_subscription_id and key_row.stripe_price_id:
        plan = key_row.key_phase if key_row.key_phase in PLAN_SLUGS else (
            plan_slug_for_price(key_row.stripe_price_id) or PLAN_TIER1
        )
        upsert_billing_subscription(
            stripe_subscription_id=key_row.stripe_subscription_id,
            stripe_customer_id=key_row.stripe_customer_id or "",
            stripe_price_id=key_row.stripe_price_id,
            plan_slug=plan,
            status="active",
            user_id=user.id,
        )


def extract_price_id_from_subscription(sub: Any) -> Optional[str]:
    try:
        items = sub.get("items", {}) if isinstance(sub, dict) else getattr(sub, "items", None)
        if items is None:
            return None
        data = items.get("data") if isinstance(items, dict) else getattr(items, "data", None)
        if not data:
            return None
        first = data[0]
        price = first.get("price") if isinstance(first, dict) else getattr(first, "price", None)
        if price is None:
            return None
        if isinstance(price, str):
            return price
        return price.get("id") if isinstance(price, dict) else getattr(price, "id", None)
    except (AttributeError, IndexError, KeyError, TypeError):
        return None
