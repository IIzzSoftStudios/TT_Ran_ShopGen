import os
from typing import Tuple

from flask import current_app, has_app_context

from app.extensions import db
from app.models import Campaign, CampaignPlayer, Player

FREE_SEAT_LIMIT = 3


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


def get_gm_limits(user):
    """Return (campaign_limit, seat_limit, label) for billing; never None."""
    phase_slug = "default"
    key = getattr(user, "registration_key_used", None) if user is not None else None
    if key is not None and getattr(key, "key_phase", None):
        phase_slug = key.key_phase
    if has_app_context() and current_app.extensions.get("phase_config") is not None:
        cfg = current_app.extensions["phase_config"].get_phase(phase_slug)
        return cfg["campaign_limit"], cfg["seat_limit"], cfg["label"]
    return FREE_CAMPAIGN_LIMIT, FREE_SEAT_LIMIT, "default"


def can_create_campaign(gm_profile) -> Tuple[bool, str]:
    user = gm_profile.user
    cap, _seats, label = get_gm_limits(user)
    existing_count = Campaign.query.filter_by(gm_profile_id=gm_profile.id).count()
    if existing_count >= cap:
        return (
            False,
            f"You have reached the free campaign limit ({cap}) for {label}. "
            "Additional campaigns will require a paid plan in the future.",
        )
    return True, ""


def can_add_player_profile(user) -> Tuple[bool, str]:
    """Enforce max non-NPC Player rows per login (mirrors GM ``campaign_limit`` for the same key phase)."""
    if user is None or getattr(user, "role", None) != "Player":
        return True, ""
    cap, _seats, label = get_gm_limits(user)
    n = (
        db.session.query(Player.id)
        .filter(Player.user_id == user.id, Player.is_npc.is_(False))
        .count()
    )
    if n >= cap:
        return (
            False,
            f"You have reached the player profile limit ({cap}) for {label}. "
            "Additional profiles will require a paid plan in the future.",
        )
    return True, ""


def can_add_player_to_campaign(campaign: Campaign) -> Tuple[bool, str]:
    gm_user = campaign.gm_profile.user
    _cap, seat_limit, label = get_gm_limits(gm_user)
    active_seats = (
        db.session.query(CampaignPlayer)
        .join(Player, Player.id == CampaignPlayer.player_id)
        .filter(
            CampaignPlayer.campaign_id == campaign.id,
            CampaignPlayer.is_active.is_(True),
            Player.is_npc.is_(False),
        )
        .count()
    )
    if active_seats >= seat_limit:
        return (
            False,
            f"This campaign has reached the free seat limit ({seat_limit} players) for {label}. "
            "Additional seats will require a paid plan in the future.",
        )
    return True, ""
