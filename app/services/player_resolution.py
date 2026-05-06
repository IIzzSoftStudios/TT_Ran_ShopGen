"""Resolve which Player row belongs to the logged-in user for the active campaign.

After the ``(user_id, gm_profile_id)`` uniqueness change, a User may have
multiple Player rows (one per GM). Session ``campaign_id`` selects the GM
via ``Campaign.gm_profile_id``. A nullable ``gm_profile_id`` denotes a solo
vault profile before any campaign membership.
"""

from __future__ import annotations

from typing import Optional

from flask import session

from app.extensions import db
from app.models import Campaign, CampaignPlayer, Player


def ensure_solo_player_profile(user) -> Optional[Player]:
    """Create a solo vault ``Player`` row when this login has none and billing allows.

    Does not run when the user already has one or more non-NPC rows (ambiguous
    multi-GM state is left to ``get_active_player`` / campaign pick).
    """
    if user is None or getattr(user, "role", None) != "Player":
        return None
    if (
        db.session.query(Player.id)
        .filter(Player.user_id == user.id, Player.is_npc.is_(False))
        .first()
        is not None
    ):
        return None
    from app.services.billing_rules import can_add_player_profile

    ok, _msg = can_add_player_profile(user)
    if not ok:
        return None
    p = Player(user_id=user.id, gm_profile_id=None, currency=0, is_npc=False)
    db.session.add(p)
    db.session.commit()
    return p


def get_active_player_or_ensure_solo(user) -> Optional[Player]:
    """Like ``get_active_player``, but lazily creates a solo profile when there are zero rows."""
    p = get_active_player(user)
    if p is not None:
        return p
    ensure_solo_player_profile(user)
    return get_active_player(user)


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


def _clear_stale_campaign_session() -> None:
    session.pop("campaign_id", None)
    session.pop("system_type", None)
    session.modified = True


def _resolve_without_session_campaign(user) -> Optional[Player]:
    rows = Player.query.filter_by(user_id=user.id, is_npc=False).all()
    if len(rows) == 1:
        return rows[0]
    return None


def get_active_player(user, *, campaign_id: Optional[int] = None) -> Optional[Player]:
    """Player row for ``user`` scoped to session campaign (or unambiguous single row).

    When ``session['campaign_id']`` is set, resolves the Player whose
    ``gm_profile_id`` matches that campaign's GM and who has an active
    ``CampaignPlayer`` for that campaign. Stale session (no membership) clears
    ``campaign_id`` and falls back.

    When session has no campaign (or after clearing stale session), returns the
    sole non-NPC Player row if exactly one exists (including a single solo vault
    row); otherwise ``None``.
    """
    if user is None or getattr(user, "role", None) != "Player":
        return None

    cid = campaign_id if campaign_id is not None else session.get("campaign_id")
    if cid is not None:
        camp = db.session.get(Campaign, int(cid))
        if camp is None:
            _clear_stale_campaign_session()
            return _resolve_without_session_campaign(user)
        pl = Player.query.filter_by(
            user_id=user.id,
            gm_profile_id=camp.gm_profile_id,
            is_npc=False,
        ).first()
        if pl is None:
            _clear_stale_campaign_session()
            return _resolve_without_session_campaign(user)
        mem = CampaignPlayer.query.filter_by(
            campaign_id=int(cid),
            player_id=pl.id,
            is_active=True,
        ).first()
        if mem is not None:
            return pl
        _clear_stale_campaign_session()
        return _resolve_without_session_campaign(user)

    return _resolve_without_session_campaign(user)


def all_player_ids_for_user(user) -> list[int]:
    """All non-NPC Player PKs for this user (for aggregating memberships)."""
    if user is None or getattr(user, "role", None) != "Player":
        return []
    return [
        r.id
        for r in Player.query.filter_by(user_id=user.id, is_npc=False).all()
    ]
