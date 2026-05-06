"""Resolve which Player row belongs to the logged-in user for the active campaign.

After the ``(user_id, gm_profile_id)`` uniqueness change, a User may have
multiple Player rows (one per GM). Session ``campaign_id`` selects the GM
via ``Campaign.gm_profile_id``.
"""

from __future__ import annotations

from typing import Optional

from flask import session

from app.extensions import db
from app.models import Campaign, CampaignPlayer, Player


def user_has_player_profile(user) -> bool:
    """True if this login has at least one non-NPC Player row."""
    if user is None or getattr(user, "role", None) != "Player":
        return False
    return (
        db.session.query(Player.id)
        .filter(Player.user_id == user.id, Player.is_npc.is_(False))
        .first()
        is not None
    )


def get_active_player(user, *, campaign_id: Optional[int] = None) -> Optional[Player]:
    """Player row for ``user`` scoped to session campaign (or unambiguous single row).

    When ``session['campaign_id']`` is set, resolves the Player whose
    ``gm_profile_id`` matches that campaign's GM and who has an active
    ``CampaignPlayer`` for that campaign.

    When session has no campaign, returns the sole Player row if exactly one
    exists; otherwise ``None`` (caller should send the user to campaign pick).
    """
    if user is None or getattr(user, "role", None) != "Player":
        return None

    cid = campaign_id if campaign_id is not None else session.get("campaign_id")
    if cid is not None:
        camp = db.session.get(Campaign, int(cid))
        if camp is None:
            return None
        pl = (
            Player.query.filter_by(
                user_id=user.id,
                gm_profile_id=camp.gm_profile_id,
                is_npc=False,
            ).first()
        )
        if pl is None:
            return None
        mem = CampaignPlayer.query.filter_by(
            campaign_id=int(cid),
            player_id=pl.id,
            is_active=True,
        ).first()
        return pl if mem is not None else None

    rows = Player.query.filter_by(user_id=user.id, is_npc=False).all()
    if len(rows) == 1:
        return rows[0]
    return None


def all_player_ids_for_user(user) -> list[int]:
    """All non-NPC Player PKs for this user (for aggregating memberships)."""
    if user is None or getattr(user, "role", None) != "Player":
        return []
    return [
        r.id
        for r in Player.query.filter_by(user_id=user.id, is_npc=False).all()
    ]
