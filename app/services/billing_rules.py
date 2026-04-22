import os
from typing import Tuple

from app.models import Campaign, CampaignPlayer

FREE_SEAT_LIMIT = 3


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


# Default 1 free campaign; set FREE_CAMPAIGN_LIMIT in config.env for local testing (e.g. 5).
FREE_CAMPAIGN_LIMIT = _int_env("FREE_CAMPAIGN_LIMIT", 1)


def can_create_campaign(gm_profile) -> Tuple[bool, str]:
    existing_count = Campaign.query.filter_by(gm_profile_id=gm_profile.id).count()
    if existing_count >= FREE_CAMPAIGN_LIMIT:
        return (
            False,
            "You have reached the free campaign limit (1). Additional campaigns will require a paid plan in the future.",
        )
    return True, ""


def can_add_player_to_campaign(campaign: Campaign) -> Tuple[bool, str]:
    active_seats = (
        CampaignPlayer.query.filter_by(campaign_id=campaign.id, is_active=True).count()
    )
    if active_seats >= FREE_SEAT_LIMIT:
        return (
            False,
            "This campaign has reached the free seat limit (3 players). Additional seats will require a paid plan in the future.",
        )
    return True, ""
