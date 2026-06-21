"""Campaign / Player join codes: Crockford-style body, redemption, reveal logging."""

from __future__ import annotations

import logging
import re
import secrets
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy.exc import IntegrityError, NoResultFound

from app.extensions import db
from app.models import Campaign, Player, PlayerCharacterSheet, User
from app.services.billing_rules import (
    can_add_player_profile,
    can_add_player_to_campaign,
)

log = logging.getLogger(__name__)

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
MAX_GENERATE_RETRIES = 5

CAMPAIGN_PREFIX = "CAMP"
PLAYER_PREFIX = "PLY"
_KNOWN_CODE_PREFIX_TOKENS = frozenset({CAMPAIGN_PREFIX, PLAYER_PREFIX})

REDEMPTION_SOURCE_REGISTRATION = "registration"
REDEMPTION_SOURCE_REGISTRATION_WITH_KEY = "registration_with_key"
REDEMPTION_SOURCE_PLAYER_JOIN = "player_join"
REDEMPTION_SOURCE_CAMPAIGN_SELECTION = "campaign_selection"


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


class ProfileLimitError(JoinCodeError):
    """Too many Player rows for this account (phase ``campaign_limit``)."""


class SystemMismatchError(JoinCodeError):
    """Character vault ruleset does not match campaign ``system_type``."""


class CodeGenerationExhausted(JoinCodeError):
    pass


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def mask_join_code(join_code: Optional[str]) -> str:
    """Mask a join code for admin display (never log or store full codes in telemetry)."""
    if not join_code:
        return "CAMP-****-****"
    s = join_code.strip().upper()
    if len(s) <= 6:
        return f"{s}****"
    return f"{s[:6]}****-****"


def _record_campaign_code_redemption(
    *,
    campaign: Campaign,
    user: User,
    player: Player,
    source: str,
) -> None:
    from app.models import CampaignCodeRedemption

    db.session.add(
        CampaignCodeRedemption(
            campaign_id=campaign.id,
            user_id=user.id,
            player_id=player.id,
            source=(source or "unknown").strip() or "unknown",
            redeemed_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
    )


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


def _fold_crockford_homoglyphs(s: str) -> str:
    return s.replace("I", "1").replace("L", "1").replace("O", "0")


def normalize_code(raw: Optional[str]) -> str:
    """Uppercase / tidy; apply I/L/O folding only to payload after ``CAMP-`` or ``PLY-``."""
    if not raw:
        return ""
    s = raw.strip().upper().replace("_", "-")
    s = re.sub(r"\s+", "", s)
    if "-" in s:
        head, _, tail = s.partition("-")
        if head in _KNOWN_CODE_PREFIX_TOKENS:
            return f"{head}-{_fold_crockford_homoglyphs(tail)}"
    return _fold_crockford_homoglyphs(s)


def generate_raw_code(prefix: str) -> str:
    """Return e.g. CAMP-XXXX-XXXX-XXXX (12 Crockford body chars)."""
    if prefix not in (CAMPAIGN_PREFIX, PLAYER_PREFIX):
        raise ValueError("invalid prefix")
    parts = [
        "".join(secrets.choice(CROCKFORD) for _ in range(4)) for _ in range(3)
    ]
    return f"{prefix}-{'-'.join(parts)}"


def _parse_prefixed(normalized: str) -> Tuple[Optional[str], str]:
    """Return (CAMPAIGN|PLAYER|None role, normalized full string)."""
    n = normalized
    if n.startswith("CAMP-"):
        return "CAMPAIGN", n
    if n.startswith("PLY-"):
        return "PLAYER", n
    return None, n


def find_campaign_by_join_code(normalized: str) -> Optional[Campaign]:
    """Resolve campaign by ``CAMP-…`` join_code."""
    prefix, _ = _parse_prefixed(normalized)
    if prefix != "CAMPAIGN":
        return None
    return Campaign.query.filter_by(join_code=normalized).first()


def find_player_by_join_code(normalized: str) -> Optional[Player]:
    prefix, _ = _parse_prefixed(normalized)
    if prefix != "PLAYER":
        return None
    return Player.query.filter_by(join_code=normalized, is_npc=False).first()


def _normalized_sheet_system_type(raw: Optional[str]) -> Optional[str]:
    s = (raw or "").strip().lower()
    if not s or s == "generic":
        return None
    return s


def effective_character_system_type_for_join(player: Player) -> Optional[str]:
    """Return concrete stored ``system_type`` for join validation, or None if generic/unset."""
    vault = (
        PlayerCharacterSheet.query.filter(
            PlayerCharacterSheet.player_id == player.id,
            PlayerCharacterSheet.campaign_id.is_(None),
        )
        .order_by(PlayerCharacterSheet.updated_at.desc())
        .first()
    )
    if vault and isinstance(vault.sheet_json, dict):
        st = _normalized_sheet_system_type(vault.sheet_json.get("system_type"))
        if st:
            return st
    row = (
        PlayerCharacterSheet.query.filter(
            PlayerCharacterSheet.player_id == player.id,
            PlayerCharacterSheet.campaign_id.isnot(None),
        )
        .order_by(PlayerCharacterSheet.updated_at.desc())
        .first()
    )
    if row and isinstance(row.sheet_json, dict):
        st = _normalized_sheet_system_type(row.sheet_json.get("system_type"))
        if st:
            return st
    return None


def assert_character_system_matches_campaign(player: Player, campaign: Campaign) -> None:
    char_st = effective_character_system_type_for_join(player)
    if char_st is None:
        return
    camp_raw = (getattr(campaign, "system_type", None) or "").strip().lower()
    if not camp_raw or camp_raw == "generic":
        return
    if char_st != camp_raw:
        raise SystemMismatchError(
            "This character is built for a different game system than this campaign. "
            "Update your character vault to match the campaign's system, or join a "
            "campaign that uses your ruleset."
        )


def redeem_campaign_code(
    user: User,
    raw_code: str,
    *,
    player_id: Optional[int] = None,
    source: str = "unknown",
    _commit: bool = True,
) -> Campaign:
    """Attach the player's character to ``campaign`` by setting ``Player.campaign_id``.

    Locks the Campaign row (PostgreSQL ``FOR UPDATE``) while checking seat cap.
    When ``_commit`` is False, only flushes — caller commits (e.g. registration).

    ``player_id`` is the optional id of the specific character row this
    redemption is scoped to (e.g. the solo character whose dashboard the
    player is on). When provided, that exact character is joined to the
    campaign or the operation fails. Without ``player_id``, the user's
    single solo (``campaign_id IS NULL``) character is promoted, or a new
    Player row is created when billing allows.
    """
    from app.services.user_capabilities import can_redeem_campaign_code

    if not can_redeem_campaign_code(user):
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

        if player_id is not None:
            requested = Player.query.filter_by(
                id=int(player_id),
                user_id=user.id,
                is_npc=False,
            ).with_for_update().first()
            if requested is None:
                raise InvalidCodeError("Character not found.")
            if requested.campaign_id is not None and requested.campaign_id != campaign.id:
                raise CrossGMError("This character already belongs to a different campaign.")
            player = requested
        else:
            already_in = Player.query.filter_by(
                user_id=user.id,
                campaign_id=campaign.id,
                is_npc=False,
            ).first()
            if already_in is not None:
                _finish()
                return campaign

            solo = Player.query.filter(
                Player.user_id == user.id,
                Player.campaign_id.is_(None),
                Player.is_npc.is_(False),
            ).first()
            if solo is not None:
                player = Player.query.filter_by(id=solo.id).with_for_update().one()
            else:
                ok_prof, msg_prof = can_add_player_profile(user)
                if not ok_prof:
                    db.session.rollback()
                    raise ProfileLimitError(msg_prof or "Player profile limit reached.")
                player = Player(
                    user_id=user.id,
                    campaign_id=None,
                    currency=0,
                    is_npc=False,
                )
                db.session.add(player)
                db.session.flush()

        if player.campaign_id == campaign.id:
            _finish()
            return campaign

        assert_character_system_matches_campaign(player, campaign)

        ok, msg = can_add_player_to_campaign(campaign)
        if not ok:
            db.session.rollback()
            raise SeatCapError(msg or "Campaign is full.")

        player.campaign_id = campaign.id
        from app.services.character_creation.creation_service import (
            copy_vault_sheet_to_campaign,
        )

        copy_vault_sheet_to_campaign(player.id, campaign.id)
        _record_campaign_code_redemption(
            campaign=campaign,
            user=user,
            player=player,
            source=source,
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
) -> Player:
    """GM adds an existing player character to ``campaign`` by its PLY- code."""
    normalized = normalize_code(raw_code)
    player = find_player_by_join_code(normalized)
    if not player or player.is_npc:
        raise InvalidCodeError("Invalid or unknown player code.")

    if campaign.gm_profile_id != gm_profile_id:
        raise CrossGMError("Campaign does not belong to this GM.")

    if player.campaign_id is not None and player.campaign_id != campaign.id:
        raise CrossGMError("That player is already in a different campaign.")

    def _finish():
        if _commit:
            db.session.commit()
        else:
            db.session.flush()

    try:
        locked = Campaign.query.filter_by(id=campaign.id).with_for_update().one()
        Player.query.filter_by(id=player.id).with_for_update().one()

        if player.campaign_id == locked.id:
            _finish()
            return player

        assert_character_system_matches_campaign(player, locked)

        ok, msg = can_add_player_to_campaign(locked)
        if not ok:
            db.session.rollback()
            raise SeatCapError(msg or "Campaign is full.")

        player.campaign_id = locked.id
        _finish()
        return player

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


def ensure_campaign_join_code_for_campaign(campaign: Campaign) -> str:
    """Return ``campaign.join_code``, assigning a new ``CAMP-…`` value if missing.

    Clears polluted values (anything that does not normalize to ``CAMP-…``).
    Performs at least one :meth:`flush` when a new code is assigned; caller must
    :meth:`commit` the session for durability. Retries on rare ``join_code``
    uniqueness collisions.

    Pollution is re-checked on every retry iteration because :meth:`rollback`
    after ``IntegrityError`` can restore a previously cleared non-``CAMP-`` value
    in the same transaction.
    """
    camp_pk = campaign.id
    gm_id = campaign.gm_profile_id
    for _ in range(MAX_GENERATE_RETRIES):
        fresh = Campaign.query.filter_by(id=camp_pk, gm_profile_id=gm_id).first()
        if not fresh:
            raise InvalidCodeError("Campaign not found.")
        if fresh.join_code:
            if normalize_code(fresh.join_code).startswith("CAMP-"):
                return fresh.join_code
            fresh.join_code = None
            db.session.flush()
        fresh.join_code = generate_raw_code(CAMPAIGN_PREFIX)
        try:
            db.session.flush()
            return fresh.join_code
        except IntegrityError:
            db.session.rollback()
    raise CodeGenerationExhausted("Could not assign a unique campaign join code.")


def reveal_campaign_code_for_gm(*, gm_profile_id: int, campaign_id: int) -> str:
    camp = Campaign.query.filter_by(
        id=campaign_id, gm_profile_id=gm_profile_id
    ).first()
    if not camp:
        raise InvalidCodeError("Campaign not found.")
    return ensure_campaign_join_code_for_campaign(camp)


def reveal_player_code_for_player(*, user_id: int, player: Player) -> str:
    if player.user_id != user_id or player.is_npc:
        raise WrongRoleError("Not your player profile.")
    if not player.join_code:
        raise InvalidCodeError("No join code assigned.")
    return player.join_code
