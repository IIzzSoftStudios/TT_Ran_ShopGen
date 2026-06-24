"""Campaign-level D&D 5e character creation settings stored in world config JSON."""

from __future__ import annotations

import uuid
from copy import deepcopy
from typing import Any, Optional

from sqlalchemy.orm.attributes import flag_modified

from app.extensions import db
from app.models import CampaignWorldConfig

SCHEMA_VERSION = 1
DEFAULT_ABILITY_METHOD = "point_buy"
DEFAULT_POINT_BUY_BUDGET = 27
MIN_POINT_BUY_BUDGET = 0
MAX_POINT_BUY_BUDGET = 54
DEFAULT_RANDOM_REROLLS = 0
MIN_RANDOM_REROLLS = 0
MAX_RANDOM_REROLLS = 5
DEFAULT_MAX_PLAYER_LEVEL = 20
MIN_MAX_PLAYER_LEVEL = 1
MAX_MAX_PLAYER_LEVEL = 20
MAX_CUSTOM_LIST = 50
MAX_NAME_LEN = 60
MAX_TEXT_LEN = 1000
MAX_TRAITS = 12
MIN_ABILITY_MOD = -10
MAX_ABILITY_MOD = 10

VALID_ABILITY_METHODS = frozenset({"point_buy", "random_roll", "player_set"})


class CharacterCreationSettingsError(ValueError):
    """Raised when GM character creation settings are invalid."""


def     solo_default_creation_settings() -> dict[str, Any]:
    """Platform defaults for solo vault creation (no campaign context)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "ability_method": DEFAULT_ABILITY_METHOD,
        "point_buy_budget": DEFAULT_POINT_BUY_BUDGET,
        "random_rerolls_per_ability": DEFAULT_RANDOM_REROLLS,
        "max_player_level": DEFAULT_MAX_PLAYER_LEVEL,
        "settings_version": "solo-default",
        "scope": "solo",
    }


def _config_for_campaign(campaign_id: int) -> CampaignWorldConfig:
    cfg = CampaignWorldConfig.query.filter_by(campaign_id=campaign_id).first()
    if cfg is None:
        cfg = CampaignWorldConfig(
            campaign_id=campaign_id,
            settings_json={},
            schema_version=1,
        )
        db.session.add(cfg)
        db.session.flush()
    if not isinstance(cfg.settings_json, dict):
        cfg.settings_json = {}
    return cfg


def _clamp_budget(raw: Any) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_POINT_BUY_BUDGET
    return max(MIN_POINT_BUY_BUDGET, min(MAX_POINT_BUY_BUDGET, value))


def _clamp_rerolls(raw: Any) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_RANDOM_REROLLS
    return max(MIN_RANDOM_REROLLS, min(MAX_RANDOM_REROLLS, value))


def _clamp_max_player_level(raw: Any) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_MAX_PLAYER_LEVEL
    return max(MIN_MAX_PLAYER_LEVEL, min(MAX_MAX_PLAYER_LEVEL, value))


def get_max_player_level(campaign_id: Optional[int]) -> int:
    """Campaign cap for player character level (1–20). Solo/vault uses SRD max."""
    if campaign_id is None:
        return DEFAULT_MAX_PLAYER_LEVEL
    return _clamp_max_player_level(get_creation_settings(campaign_id).get("max_player_level"))


def normalize_creation_settings(raw: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Return normalized character_creation settings with defaults."""
    data = raw if isinstance(raw, dict) else {}
    method = str(data.get("ability_method") or DEFAULT_ABILITY_METHOD).strip().lower()
    if method not in VALID_ABILITY_METHODS:
        method = DEFAULT_ABILITY_METHOD
    settings_version = str(data.get("settings_version") or "").strip() or str(uuid.uuid4())
    return {
        "schema_version": SCHEMA_VERSION,
        "ability_method": method,
        "point_buy_budget": _clamp_budget(data.get("point_buy_budget")),
        "random_rerolls_per_ability": _clamp_rerolls(data.get("random_rerolls_per_ability")),
        "max_player_level": _clamp_max_player_level(data.get("max_player_level")),
        "settings_version": settings_version,
    }


def get_creation_settings(campaign_id: Optional[int]) -> dict[str, Any]:
    if campaign_id is None:
        return solo_default_creation_settings()
    cfg = CampaignWorldConfig.query.filter_by(campaign_id=campaign_id).first()
    if cfg is None or not isinstance(cfg.settings_json, dict):
        out = normalize_creation_settings({})
        out["scope"] = "campaign"
        return out
    raw = cfg.settings_json.get("character_creation")
    out = normalize_creation_settings(raw if isinstance(raw, dict) else {})
    out["scope"] = "campaign"
    return out


def _normalize_character_options(raw: Optional[dict[str, Any]]) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    species = []
    for row in (data.get("species") or [])[:MAX_CUSTOM_LIST]:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()[:MAX_NAME_LEN]
        if not name:
            continue
        key = str(row.get("key") or name.lower().replace(" ", "-"))[:80]
        mods = row.get("ability_modifiers") or {}
        clean_mods = {}
        for ability in ("str", "dex", "con", "int", "wis", "cha"):
            try:
                val = int(mods.get(ability, 0) or 0)
            except (TypeError, ValueError):
                raise CharacterCreationSettingsError(
                    f"{ability.upper()} modifier must be an integer."
                )
            if not (MIN_ABILITY_MOD <= val <= MAX_ABILITY_MOD):
                raise CharacterCreationSettingsError(
                    f"{ability.upper()} modifier must be between {MIN_ABILITY_MOD} and {MAX_ABILITY_MOD}."
                )
            clean_mods[ability] = val
        species.append(
            {
                "key": key,
                "name": name,
                "summary": str(row.get("summary") or "")[:MAX_TEXT_LEN],
                "ability_modifiers": clean_mods,
                "source": "gm_custom",
            }
        )
    backgrounds = []
    for row in (data.get("backgrounds") or [])[:MAX_CUSTOM_LIST]:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()[:MAX_NAME_LEN]
        if not name:
            continue
        key = str(row.get("key") or name.lower().replace(" ", "-"))[:80]
        skills = [
            str(s).strip().lower()
            for s in (row.get("skill_proficiencies") or [])[:4]
            if str(s).strip()
        ]
        backgrounds.append(
            {
                "key": key,
                "name": name,
                "summary": str(row.get("summary") or "")[:MAX_TEXT_LEN],
                "skill_proficiencies": skills,
                "source": "gm_custom",
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "species": species,
        "backgrounds": backgrounds,
    }


def get_character_options(campaign_id: int) -> dict[str, Any]:
    cfg = CampaignWorldConfig.query.filter_by(campaign_id=campaign_id).first()
    if cfg is None or not isinstance(cfg.settings_json, dict):
        return _normalize_character_options({})
    raw = cfg.settings_json.get("character_options")
    return _normalize_character_options(raw if isinstance(raw, dict) else {})


def update_creation_settings(campaign_id: int, patch: dict[str, Any]) -> dict[str, Any]:
    """Update GM stat-generation settings for a campaign."""
    cfg = _config_for_campaign(campaign_id)
    settings = cfg.settings_json
    current = normalize_creation_settings(settings.get("character_creation"))
    method = str(patch.get("ability_method") or current["ability_method"]).strip().lower()
    if method not in VALID_ABILITY_METHODS:
        raise CharacterCreationSettingsError("Invalid ability generation method.")
    budget = _clamp_budget(patch.get("point_buy_budget", current["point_buy_budget"]))
    rerolls = _clamp_rerolls(
        patch.get("random_rerolls_per_ability", current["random_rerolls_per_ability"])
    )
    max_player_level = _clamp_max_player_level(
        patch.get("max_player_level", current["max_player_level"])
    )
    changed = (
        method != current["ability_method"]
        or budget != current["point_buy_budget"]
        or rerolls != current["random_rerolls_per_ability"]
        or max_player_level != current["max_player_level"]
    )
    updated = {
        "schema_version": SCHEMA_VERSION,
        "ability_method": method,
        "point_buy_budget": budget,
        "random_rerolls_per_ability": rerolls,
        "max_player_level": max_player_level,
        "settings_version": str(uuid.uuid4()) if changed else current["settings_version"],
    }
    settings["character_creation"] = updated
    cfg.settings_json = settings
    flag_modified(cfg, "settings_json")
    db.session.flush()
    out = deepcopy(updated)
    out["scope"] = "campaign"
    return out
