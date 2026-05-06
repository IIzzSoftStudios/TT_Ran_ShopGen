"""Campaign / Player join codes: Crockford-style body, redemption, reveal logging."""

from __future__ import annotations

import logging
import re
import secrets
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy.exc import IntegrityError, NoResultFound

from app.extensions import db
from app.models import Campaign, CampaignPlayer, Player, User
from app.services.billing_rules import can_add_player_to_campaign

log = logging.getLogger(__name__)

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
MAX_GENERATE_RETRIES = 5

CAMPAIGN_PREFIX = "CAMP"
PLAYER_PREFIX = "PLY"


class JoinCodeError(Exception):
    """Base class for join-code failures (never embed raw codes in messages)."""


class InvalidCodeError(JoinCodeError):
    pass


class WrongRoleError(JoinCodeError):
    pass


class SeatCapError(JoinCodeError):
    pass


class CrossGMError(JoinCodeError):
    pass


class CodeGenerationExhausted(JoinCodeError):
    pass


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log_reveal(*, user_id: int, action: str, target_id: int, ip: str) -> None:
    """Audit line: never log the join code itself."""
    log.info(
        "%s | user_id=%s | action=%s | target_id=%s | ip=%s",
        _utc_iso(),
        user_id,
        action,
        target_id,
        ip or "-",
    )


def normalize_code(raw: Optional[str]) -> str:
    if not raw:
        return ""
    s = raw.strip().upper().replace("_", "-")
    s = s.replace("I", "1").replace("L", "1")
    s = s.replace("O", "0")
    s = re.sub(r"\s+", "", s)
    return s


def generate_raw_code(prefix: str) -> str:
    """Return e.g. CAMP-XXXX-XXXX-XXXX (12 Crockford body chars)."""
    if prefix not in (CAMPAIGN_PREFIX, PLAYER_PREFIX):
        raise ValueError("invalid prefix")
    parts = [
        "".join(secrets.choice(CROCKFORD) for _ in range(4)) for _ in range(3)
    ]
    return f"{prefix}-{'-'.join(parts)}"


def _parse_prefixed(normalized: str) -> Tuple[Optional[str], str]:
    """Return (CAMPAIGN|PLAYER|None prefix token, normalized full string)."""
    n = normalized
    if n.startswith("CAMP-"):
        return "CAMPAIGN", n
    if n.startswith("PLY-"):
        return "PLAYER", n
    return None, n


def find_campaign_by_join_code(normalized: str) -> Optional[Campaign]:
    prefix, _ = _parse_prefixed(normalized)
    if prefix != "CAMPAIGN":
        return None
    return Campaign.query.filter_by(join_code=normalized).first()


def find_player_by_join_code(normalized: str) -> Optional[Player]:
    prefix, _ = _parse_prefixed(normalized)
    if prefix != "PLAYER":
        return None
    return Player.query.filter_by(join_code=normalized, is_npc=False).first()


def redeem_campaign_code(user: User, raw_code: str, *, _commit: bool = True) -> Campaign:
    """Attach ``user`` to ``campaign`` via join code; reuse (user, gm) Player row.

    Locks the Campaign row (PostgreSQL ``FOR UPDATE``) while checking seat cap.
    When ``_commit`` is False, only flushes — caller commits (e.g. registration).
    """
    if getattr(user, "role", None) != "Player":
        raise WrongRoleError("Only player accounts can redeem a campaign code.")

    normalized = normalize_code(raw_code)
    campaign = find_campaign_by_join_code(normalized)
    if not campaign:
        raise InvalidCodeError("Invalid or unknown campaign code.")

    def _finish():
        if _commit:
            db.session.commit()
        else:
            db.session.flush()

    try:
        campaign = (
            Campaign.query.filter_by(id=campaign.id).with_for_update().one()
        )

        existing = Player.query.filter_by(
            user_id=user.id,
            gm_profile_id=campaign.gm_profile_id,
            is_npc=False,
        ).first()
        if existing is None:
            player = Player(
                user_id=user.id,
                gm_profile_id=campaign.gm_profile_id,
                currency=0,
                is_npc=False,
            )
            db.session.add(player)
            db.session.flush()
        else:
            player = existing

        dup = CampaignPlayer.query.filter_by(
            campaign_id=campaign.id,
            player_id=player.id,
        ).first()
        if dup is not None:
            if dup.is_active:
                _finish()
                return campaign
            dup.is_active = True
            dup.status = "active"
            _finish()
            return campaign

        ok, msg = can_add_player_to_campaign(campaign)
        if not ok:
            db.session.rollback()
            raise SeatCapError(msg or "Campaign is full.")

        db.session.add(
            CampaignPlayer(
                campaign_id=campaign.id,
                player_id=player.id,
                status="active",
                is_active=True,
            )
        )
        _finish()
        return campaign

    except SeatCapError:
        raise
    except JoinCodeError:
        db.session.rollback()
        raise
    except NoResultFound:
        db.session.rollback()
        raise InvalidCodeError("Invalid or unknown campaign code.") from None
    except IntegrityError:
        db.session.rollback()
        raise InvalidCodeError("Could not join campaign (conflict).") from None


def redeem_player_code(
    *,
    gm_profile_id: int,
    campaign: Campaign,
    raw_code: str,
    _commit: bool = True,
) -> CampaignPlayer:
    """GM adds an existing player to ``campaign`` by that player's PLY- code."""
    normalized = normalize_code(raw_code)
    player = find_player_by_join_code(normalized)
    if not player or player.is_npc:
        raise InvalidCodeError("Invalid or unknown player code.")

    if player.gm_profile_id != gm_profile_id:
        raise CrossGMError("That player code belongs to a different GM.")

    if player.gm_profile_id != campaign.gm_profile_id:
        raise CrossGMError("Campaign and player are not under the same GM.")

    def _finish():
        if _commit:
            db.session.commit()
        else:
            db.session.flush()

    try:
        # Lock campaign (seat cap) then player row; same order as other paths that
        # take the campaign lock, to reduce deadlock risk.
        locked = Campaign.query.filter_by(id=campaign.id).with_for_update().one()
        Player.query.filter_by(id=player.id).with_for_update().one()

        dup = CampaignPlayer.query.filter_by(
            campaign_id=locked.id,
            player_id=player.id,
        ).first()
        if dup is not None:
            if dup.is_active:
                _finish()
                return dup
            dup.is_active = True
            dup.status = "active"
            _finish()
            return dup

        ok, msg = can_add_player_to_campaign(locked)
        if not ok:
            db.session.rollback()
            raise SeatCapError(msg or "Campaign is full.")

        row = CampaignPlayer(
            campaign_id=locked.id,
            player_id=player.id,
            status="active",
            is_active=True,
        )
        db.session.add(row)
        _finish()
        return row

    except SeatCapError:
        raise
    except JoinCodeError:
        db.session.rollback()
        raise
    except NoResultFound:
        db.session.rollback()
        raise InvalidCodeError(
            "Could not add player (campaign or player no longer exists)."
        ) from None
    except IntegrityError:
        db.session.rollback()
        raise InvalidCodeError("Could not add player (conflict).") from None


def reveal_campaign_code_for_gm(*, gm_profile_id: int, campaign_id: int) -> str:
    camp = Campaign.query.filter_by(
        id=campaign_id, gm_profile_id=gm_profile_id
    ).first()
    if not camp or not camp.join_code:
        raise InvalidCodeError("Campaign not found.")
    return camp.join_code


def reveal_player_code_for_player(*, user_id: int, player: Player) -> str:
    if player.user_id != user_id or player.is_npc:
        raise WrongRoleError("Not your player profile.")
    if not player.join_code:
        raise InvalidCodeError("No join code assigned.")
    return player.join_code
