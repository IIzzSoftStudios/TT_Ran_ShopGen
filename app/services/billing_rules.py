import os
from typing import Optional, Tuple

from flask import current_app, has_app_context

from app.extensions import db
from app.models import BillingSubscription, Campaign, Player

FREE_SEAT_LIMIT = 3
ACTIVE_SUB_STATUSES = frozenset({"active", "trialing", "past_due"})


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


# Legacy env override when phase_config is unavailable (e.g. isolated unit tests).
FREE_CAMPAIGN_LIMIT = _int_env("FREE_CAMPAIGN_LIMIT", 1)


def _active_subscription(user) -> Optional[BillingSubscription]:
    if user is None:
        return None
    user_id = getattr(user, "id", None)
    if not isinstance(user_id, int):
        return None
    try:
        return (
            BillingSubscription.query.filter(
                BillingSubscription.user_id == user_id,
                BillingSubscription.status.in_(tuple(ACTIVE_SUB_STATUSES)),
            )
            .order_by(BillingSubscription.updated_at.desc())
            .first()
        )
    except Exception:
        # Lightweight test apps / missing table — fall back to key phase.
        return None


def _had_stripe_billing(user) -> bool:
    """True when this login was linked to Stripe (customer and/or sub row)."""
    if user is None:
        return False
    if getattr(user, "stripe_customer_id", None):
        return True
    user_id = getattr(user, "id", None)
    if not isinstance(user_id, int):
        return False
    try:
        return (
            BillingSubscription.query.filter(
                BillingSubscription.user_id == user_id
            ).first()
            is not None
        )
    except Exception:
        return False


def requires_resubscribe_gate(user) -> bool:
    """
    True when the user previously had paid Stripe billing but no longer has an
    active/trialing/past_due subscription. Never-paid free accounts stay unlocked;
    vault keepers and admin-test keys are exempt.
    """
    if user is None:
        return False
    if getattr(user, "role", None) == "vault_keeper":
        return False
    key = getattr(user, "registration_key_used", None)
    if key is not None and getattr(key, "is_admin_test_key", False):
        return False
    if _active_subscription(user) is not None:
        return False
    return _had_stripe_billing(user)


def resolve_phase_slug(user) -> str:
    """Prefer live Stripe subscription plan; else registration key phase."""
    sub = _active_subscription(user)
    if sub is not None and sub.plan_slug:
        return str(sub.plan_slug)
    # Canceled/lapsed paid users must not keep key_phase entitlements.
    if requires_resubscribe_gate(user):
        return "default"
    key = getattr(user, "registration_key_used", None) if user is not None else None
    if key is not None and getattr(key, "key_phase", None):
        return str(key.key_phase)
    return "default"


def get_gm_limits(user):
    """Return (campaign_limit, seat_limit|None, label). seat_limit None = unlimited."""
    phase_slug = resolve_phase_slug(user)
    if has_app_context() and current_app.extensions.get("phase_config") is not None:
        cfg = current_app.extensions["phase_config"].get_phase(phase_slug)
        return cfg["campaign_limit"], cfg.get("seat_limit"), cfg["label"]
    return FREE_CAMPAIGN_LIMIT, FREE_SEAT_LIMIT, "default"


def _limit_message(kind: str, cap: int, label: str) -> str:
    return (
        f"You have reached the {kind} limit ({cap}) for {label}. "
        "Upgrade your plan in Billing settings to continue."
    )


def can_create_campaign(gm_profile) -> Tuple[bool, str]:
    user = gm_profile.user
    cap, _seats, label = get_gm_limits(user)
    existing_count = Campaign.query.filter_by(
        gm_profile_id=gm_profile.id,
        is_active=True,
    ).count()
    if existing_count >= cap:
        return False, _limit_message("campaign", cap, label)
    return True, ""


def can_add_player_profile(user) -> Tuple[bool, str]:
    """Enforce max non-NPC Player rows per login (mirrors GM campaign_limit)."""
    if user is None or getattr(user, "role", None) not in ("Player", "Both"):
        return True, ""
    cap, _seats, label = get_gm_limits(user)
    n = (
        db.session.query(Player.id)
        .filter(Player.user_id == user.id, Player.is_npc.is_(False))
        .count()
    )
    if n >= cap:
        return False, _limit_message("player profile", cap, label)
    return True, ""


def can_add_player_to_campaign(campaign: Campaign) -> Tuple[bool, str]:
    gm_user = campaign.gm_profile.user
    _cap, seat_limit, label = get_gm_limits(gm_user)
    if seat_limit is None:
        return True, ""
    active_seats = (
        db.session.query(Player.id)
        .filter(
            Player.campaign_id == campaign.id,
            Player.is_npc.is_(False),
        )
        .count()
    )
    if active_seats >= seat_limit:
        return False, _limit_message("player seat", seat_limit, label)
    return True, ""
