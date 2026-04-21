from typing import Tuple

from app.models import Campaign, CampaignPlayer

FREE_CAMPAIGN_LIMIT = 1
FREE_SEAT_LIMIT = 3


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
