"""Per-campaign D&D 5e battle settings (gear popout in the Battle tab).

Unknown keys are dropped, enums validated, and booleans coerced so the
stored JSON always matches DEFAULT_SETTINGS' shape. Services flush; routes
commit.
"""

from __future__ import annotations

from app.extensions import db
from app.models import BattleSettings
from app.services.combat import CombatValidationError
from app.services.combat.dnd5e_rules import DIAGONAL_MODES

INITIATIVE_TIE_MODES = ("dex_then_random", "stable")
CRIT_MODES = ("double_dice",)
CONCENTRATION_CHECK_MODES = ("server_roll", "gm_entered", "server_and_gm")

DEFAULT_SETTINGS = {
    # Grid / movement
    "diagonal_mode": "five_ten_five",
    # Initiative
    "initiative_tie_mode": "dex_then_random",
    # Automation toggles
    "opportunity_attacks": True,
    "flanking": False,
    "cover": False,
    "death_saves": True,
    "concentration_checks": True,
    "conditions_enabled": True,
    "auto_apply_damage": True,
    # Resource tracking (optional per user requirement)
    "track_action_economy": True,
    "track_spell_slots": False,
    # Spell scope guardrails (encounter-snapshotted)
    "direct_numeric_auto_resolution": True,
    "manual_spell_slot_consumption": True,
    "concentration_tracking": True,
    "concentration_auto_replace": True,
    "concentration_cleanup_tracked_effects": True,
    "player_concentration_end": False,
    "concentration_check_mode": "server_and_gm",
    # Crits
    "crit_mode": "double_dice",
}

_ENUMS = {
    "diagonal_mode": DIAGONAL_MODES,
    "initiative_tie_mode": INITIATIVE_TIE_MODES,
    "crit_mode": CRIT_MODES,
    "concentration_check_mode": CONCENTRATION_CHECK_MODES,
}


def validate_settings(raw) -> dict:
    """Merge a client payload over defaults, rejecting bad enum values."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise CombatValidationError("Settings must be an object.")
    clean = dict(DEFAULT_SETTINGS)
    for key, default in DEFAULT_SETTINGS.items():
        if key not in raw:
            continue
        value = raw[key]
        if key in _ENUMS:
            if value not in _ENUMS[key]:
                raise CombatValidationError(
                    f"{key} must be one of: {', '.join(_ENUMS[key])}."
                )
            clean[key] = value
        elif isinstance(default, bool):
            clean[key] = bool(value)
    return clean


def get_settings(campaign_id: int) -> dict:
    """Stored settings merged over defaults (defaults if no row yet)."""
    row = BattleSettings.query.filter_by(campaign_id=campaign_id).first()
    stored = row.settings_json if row is not None else {}
    merged = dict(DEFAULT_SETTINGS)
    for key in DEFAULT_SETTINGS:
        if isinstance(stored, dict) and key in stored:
            merged[key] = stored[key]
    return merged


def save_settings(campaign_id: int, raw) -> dict:
    """Validate and upsert the campaign's settings row. Flushes, no commit."""
    clean = validate_settings(raw)
    row = BattleSettings.query.filter_by(campaign_id=campaign_id).first()
    if row is None:
        row = BattleSettings(campaign_id=campaign_id, settings_json=clean)
        db.session.add(row)
    else:
        row.settings_json = clean
    db.session.flush()
    return clean
