"""Campaign counts for account menu display."""

from __future__ import annotations

from app.models import Campaign, Player
from app.services.user_capabilities import has_gm_capability


def get_campaign_counts(user) -> dict[str, int]:
    """Return GM-owned and player-joined campaign counts for ``user``."""
    gm_count = 0
    player_count = 0
    if user is None:
        return {"gm": 0, "player": 0}

    if has_gm_capability(user) and user.gm_profile:
        gm_count = Campaign.query.filter_by(gm_profile_id=user.gm_profile.id).count()

    player_campaign_ids = {
        row[0]
        for row in Player.query.filter(
            Player.user_id == user.id,
            Player.is_npc.is_(False),
            Player.campaign_id.isnot(None),
        )
        .with_entities(Player.campaign_id)
        .distinct()
        .all()
        if row[0] is not None
    }
    player_count = len(player_campaign_ids)
    return {"gm": gm_count, "player": player_count}
