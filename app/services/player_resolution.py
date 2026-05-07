"""Resolve which Player row belongs to the logged-in user for the active campaign.

A User may have multiple Player rows (one per character). ``Player.campaign_id``
is the sole campaign tenancy column: NULL means a solo vault character, set
means a character joined to that campaign.
"""

from __future__ import annotations

from typing import Optional

from flask import session

from app.extensions import db
from app.models import Player


def ensure_solo_player_profile(user) -> Optional[Player]:
    """Create a solo vault ``Player`` row when this login has none and billing allows.

    Does not run when the user already has one or more non-NPC rows (ambiguous
    multi-character state is left to ``get_active_player`` / character pick).
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
    p = Player(user_id=user.id, campaign_id=None, currency=0, is_npc=False)
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
    session.pop("player_id", None)
    session.modified = True


def _clear_stale_player_session() -> None:
    """Drop only ``session['player_id']``; keep the campaign loaded."""
    session.pop("player_id", None)
    session.modified = True


def _resolve_without_session_campaign(user) -> Optional[Player]:
    rows = Player.query.filter_by(user_id=user.id, is_npc=False).all()
    if len(rows) == 1:
        return rows[0]
    return None


def _resolve_session_player(user, cid: Optional[int]) -> Optional[Player]:
    """Honor ``session['player_id']`` as the active character when valid.

    Validation: the player row must be owned by ``user``, non-NPC, and (if
    ``cid`` is set) belong to that campaign. A mismatch clears
    ``session['player_id']`` and returns ``None`` so the caller can fall back
    to the campaign-only filter.
    """
    raw = session.get("player_id")
    if raw is None:
        return None
    try:
        pid = int(raw)
    except (TypeError, ValueError):
        _clear_stale_player_session()
        return None
    q = Player.query.filter(
        Player.id == pid,
        Player.user_id == user.id,
        Player.is_npc.is_(False),
    )
    if cid is not None:
        q = q.filter(Player.campaign_id == int(cid))
    pl = q.first()
    if pl is None:
        _clear_stale_player_session()
    return pl


def get_active_player(user, *, campaign_id: Optional[int] = None) -> Optional[Player]:
    """Player row for ``user`` scoped to session campaign + character pick.

    Resolution order:
      1. If ``session['player_id']`` is set and refers to a character owned by
         this user (and, when a campaign is loaded, belongs to it), use it.
         This is what lets a user with 2+ characters in the same campaign
         pick which one is active.
      2. Otherwise, when ``session['campaign_id']`` is set, return the (single)
         character matching that campaign. With multiple matches the call
         returns ``None`` rather than guess; the chooser page is responsible
         for forcing a pick.
      3. Otherwise, fall back to the unambiguous single-row case.
    Stale state (deleted character, wrong owner) clears the offending session
    key and falls through to the next step.
    """
    if user is None or getattr(user, "role", None) != "Player":
        return None

    cid = campaign_id if campaign_id is not None else session.get("campaign_id")

    pinned = _resolve_session_player(user, cid)
    if pinned is not None:
        return pinned

    if cid is not None:
        rows = (
            Player.query.filter(
                Player.user_id == user.id,
                Player.is_npc.is_(False),
                Player.campaign_id == int(cid),
            )
            .all()
        )
        if len(rows) == 1:
            return rows[0]
        if len(rows) == 0:
            _clear_stale_campaign_session()
            return _resolve_without_session_campaign(user)
        # Multiple characters in this campaign and no pin: the chooser route
        # must be used. Returning None forces the caller to redirect.
        return None

    return _resolve_without_session_campaign(user)


def all_player_ids_for_user(user) -> list[int]:
    """All non-NPC Player PKs for this user (for aggregating memberships)."""
    if user is None or getattr(user, "role", None) != "Player":
        return []
    return [
        r.id
        for r in Player.query.filter_by(user_id=user.id, is_npc=False).all()
    ]


def list_user_characters(user) -> list[Player]:
    """All non-NPC Player rows owned by ``user`` (each row = one character).

    Ordered by id ascending so the oldest character renders first in lists.
    """
    if user is None or getattr(user, "role", None) != "Player":
        return []
    return (
        Player.query.filter_by(user_id=user.id, is_npc=False)
        .order_by(Player.id.asc())
        .all()
    )


def get_character_for_user(user, player_id: int) -> Optional[Player]:
    """Strict owner lookup used by /character/<id> routes (blocks IDOR).

    Returns the Player row only when it belongs to ``user`` and is not an NPC.
    """
    if user is None or getattr(user, "role", None) != "Player":
        return None
    try:
        pid = int(player_id)
    except (TypeError, ValueError):
        return None
    return Player.query.filter_by(
        id=pid, user_id=user.id, is_npc=False
    ).first()
