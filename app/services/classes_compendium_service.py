"""Campaign-scoped classes compendium stored in world settings JSON.

Base D&D 5e classes are seeded as editable mechanical shells with level 1–20
progression rows. GMs can add custom classes and edit progression text; no
book prose is copied here.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any, Optional

from sqlalchemy.orm.attributes import flag_modified

from app.extensions import db
from app.models import CampaignWorldConfig
from app.services.character_creation.dnd5e_catalog import (
    ALL_SKILL_KEYS,
    CORE_CLASSES,
)

_ABILITIES = ("str", "dex", "con", "int", "wis", "cha")
_MAX_NAME_LEN = 60
_MAX_SUMMARY_LEN = 500
_MAX_NOTES_LEN = 1000
_MAX_FEATURES_PER_LEVEL = 12
_MAX_FEATURE_NAME = 80
_MAX_FEATURE_DESC = 500
_MAX_RESOURCE_KEYS = 10
_MAX_SPELL_SLOT_KEYS = 10
_MAX_ENTRY_BYTES = 65536
_LEVELS = tuple(range(1, 21))


class ClassesValidationError(ValueError):
    """Raised when classes compendium input is invalid."""


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(name or "").strip().lower()).strip("-")
    return slug[:80] or "class"


def _proficiency_bonus(level: int) -> int:
    if level <= 0:
        return 2
    return 2 + ((level - 1) // 4)


def _default_progression_row(level: int) -> dict[str, Any]:
    return {
        "level": level,
        "proficiency_bonus": _proficiency_bonus(level),
        "features": [],
        "trait_keys": [],
        "spell_slots": {},
        "resources": {},
        "notes": "",
    }


def _default_class_entry(raw: dict[str, Any], *, source: str = "base") -> dict[str, Any]:
    skill_choices = raw.get("skill_choices") or {"count": 2, "options": []}
    return {
        "key": str(raw.get("key") or _slug(raw.get("name") or "class")),
        "name": str(raw.get("name") or "Class"),
        "source": source,
        "summary": str(raw.get("summary") or "")[:_MAX_SUMMARY_LEN],
        "hit_die": int(raw.get("hit_die") or 8),
        "save_proficiencies": list(raw.get("save_proficiencies") or []),
        "skill_choices": deepcopy(skill_choices),
        "trait_keys": list(raw.get("trait_keys") or []),
        "level_progression": [_default_progression_row(level) for level in _LEVELS],
        "is_hidden": bool(raw.get("is_hidden")),
        "secret": bool(raw.get("secret")),
        "visible_to_owner": bool(raw.get("visible_to_owner", True)),
        "notes": str(raw.get("notes") or "")[:_MAX_NOTES_LEN],
    }


def _config_for_campaign(campaign_id: int, *, lock: bool = False) -> CampaignWorldConfig:
    query = CampaignWorldConfig.query.filter_by(campaign_id=campaign_id)
    if lock:
        query = query.with_for_update()
    cfg = query.first()
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


def _normalize_entry(raw: dict[str, Any]) -> dict[str, Any]:
    source = str(raw.get("source") or "custom")
    base = _default_class_entry(raw, source=source)
    base.update(deepcopy(raw))
    base["key"] = str(raw.get("key") or base["key"])
    base["name"] = str(raw.get("name") or base["name"]).strip()
    base["save_proficiencies"] = _clean_save_proficiencies(
        base.get("save_proficiencies") or []
    )
    base["skill_choices"] = _clean_skill_choices(base.get("skill_choices") or {})
    base["trait_keys"] = _clean_trait_keys(base.get("trait_keys") or [])
    base["level_progression"] = _clean_level_progression(
        base.get("level_progression") or []
    )
    base["is_hidden"] = bool(base.get("is_hidden"))
    base["secret"] = bool(base.get("secret"))
    base["visible_to_owner"] = bool(base.get("visible_to_owner", True))
    base["notes"] = str(base.get("notes") or "")[:_MAX_NOTES_LEN]
    base["summary"] = str(base.get("summary") or "")[:_MAX_SUMMARY_LEN]
    try:
        hit_die = int(base.get("hit_die") or 8)
    except (TypeError, ValueError):
        hit_die = 8
    if hit_die not in (4, 6, 8, 10, 12):
        hit_die = 8
    base["hit_die"] = hit_die
    _assert_entry_size(base)
    return base


def _ensure_compendium(settings: dict[str, Any]) -> list[dict[str, Any]]:
    compendium = settings.get("classes_compendium")
    if not isinstance(compendium, list):
        compendium = []

    by_key: dict[str, dict[str, Any]] = {}
    for raw in compendium:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        key = str(raw.get("key") or _slug(name))
        entry = _normalize_entry({**raw, "key": key, "name": name})
        by_key[key] = entry

    for raw in CORE_CLASSES:
        key = str(raw["key"])
        if key not in by_key:
            by_key[key] = _normalize_entry({**deepcopy(raw), "source": "base"})
        else:
            existing = by_key[key]
            if existing.get("source") in (None, "default"):
                existing["source"] = "base"
            for field in ("summary", "hit_die", "save_proficiencies", "skill_choices"):
                if not existing.get(field) and raw.get(field):
                    existing[field] = deepcopy(raw[field])

    entries = sorted(
        by_key.values(),
        key=lambda row: (row.get("source") == "custom", row["name"].lower()),
    )
    settings["classes_compendium"] = entries
    return entries


def ensure_classes_compendium(campaign_id: int) -> list[dict[str, Any]]:
    from app.services.traits_compendium_service import ensure_traits_compendium

    ensure_traits_compendium(campaign_id)
    cfg = _config_for_campaign(campaign_id)
    settings = cfg.settings_json
    entries = _ensure_compendium(settings)
    cfg.settings_json = settings
    flag_modified(cfg, "settings_json")
    db.session.flush()
    return deepcopy(entries)


def list_classes(campaign_id: int) -> list[dict[str, Any]]:
    return ensure_classes_compendium(campaign_id)


def list_visible_classes(campaign_id: int) -> list[dict[str, Any]]:
    return [
        entry
        for entry in ensure_classes_compendium(campaign_id)
        if not entry.get("is_hidden") and not entry.get("secret")
    ]


def get_class_entry(campaign_id: int, key: str) -> Optional[dict[str, Any]]:
    needle = str(key or "").strip().lower()
    if not needle:
        return None
    for entry in ensure_classes_compendium(campaign_id):
        if str(entry.get("key") or "").lower() == needle:
            return deepcopy(entry)
    return None


def _clean_save_proficiencies(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        raise ClassesValidationError("save_proficiencies must be a list.")
    clean = []
    for item in raw[:2]:
        ability = str(item or "").strip().lower()
        if ability not in _ABILITIES:
            raise ClassesValidationError(f"Invalid save proficiency: {item}.")
        if ability not in clean:
            clean.append(ability)
    if len(clean) != 2:
        raise ClassesValidationError("Exactly two save proficiencies are required.")
    return clean


def _clean_skill_choices(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ClassesValidationError("skill_choices must be an object.")
    try:
        count = int(raw.get("count") or 0)
    except (TypeError, ValueError):
        raise ClassesValidationError("skill_choices.count must be an integer.")
    if not (0 <= count <= 4):
        raise ClassesValidationError("skill_choices.count must be between 0 and 4.")
    options_raw = raw.get("options")
    if options_raw == "any":
        options = "any"
    elif isinstance(options_raw, list):
        options = []
        for item in options_raw:
            key = str(item or "").strip().lower()
            if key not in ALL_SKILL_KEYS:
                raise ClassesValidationError(f"Invalid skill option: {item}.")
            if key not in options:
                options.append(key)
    else:
        raise ClassesValidationError(
            'skill_choices.options must be "any" or a list of skill keys.'
        )
    if options != "any" and count > len(options):
        raise ClassesValidationError(
            "skill_choices.count cannot exceed the number of listed options."
        )
    return {"count": count, "options": options}


def _clean_features(raw: Any) -> list[dict[str, str]]:
    if raw is None or raw == "":
        return []
    if not isinstance(raw, list) or len(raw) > _MAX_FEATURES_PER_LEVEL:
        raise ClassesValidationError(
            f"features must be a list of at most {_MAX_FEATURES_PER_LEVEL} entries."
        )
    clean = []
    for index, feature in enumerate(raw):
        if not isinstance(feature, dict):
            raise ClassesValidationError("Each feature must be an object.")
        name = str(feature.get("name") or f"Feature {index + 1}").strip()[
            :_MAX_FEATURE_NAME
        ]
        description = str(feature.get("description") or "").strip()[
            :_MAX_FEATURE_DESC
        ]
        if name or description:
            clean.append({"name": name, "description": description})
    return clean


def _clean_slot_map(raw: Any, *, label: str, max_keys: int) -> dict[str, int]:
    if raw is None or raw == "":
        return {}
    if not isinstance(raw, dict):
        raise ClassesValidationError(f"{label} must be an object.")
    if len(raw) > max_keys:
        raise ClassesValidationError(f"{label} has too many keys.")
    clean: dict[str, int] = {}
    for key, value in raw.items():
        slot_key = str(key).strip()
        if not slot_key or len(slot_key) > 8:
            raise ClassesValidationError(f"Invalid {label} key: {key}.")
        try:
            slots = int(value)
        except (TypeError, ValueError):
            raise ClassesValidationError(f"{label} values must be integers.")
        if slots < 0 or slots > 99:
            raise ClassesValidationError(f"{label} values must be between 0 and 99.")
        clean[slot_key] = slots
    return clean


def _clean_trait_keys(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        keys = [part.strip().lower() for part in raw.split(",") if part.strip()]
    elif isinstance(raw, list):
        keys = [str(part or "").strip().lower() for part in raw if str(part or "").strip()]
    else:
        raise ClassesValidationError("trait_keys must be a list or comma-separated string.")
    return keys[:24]


def _clean_progression_row(raw: Any, expected_level: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ClassesValidationError(f"Level {expected_level} progression must be an object.")
    try:
        level = int(raw.get("level") or expected_level)
    except (TypeError, ValueError):
        raise ClassesValidationError(f"Level {expected_level} must be an integer.")
    if level != expected_level:
        raise ClassesValidationError(
            f"Progression row level mismatch: expected {expected_level}, got {level}."
        )
    try:
        prof = int(raw.get("proficiency_bonus") or _proficiency_bonus(level))
    except (TypeError, ValueError):
        raise ClassesValidationError(
            f"Level {level} proficiency_bonus must be an integer."
        )
    if not (2 <= prof <= 12):
        raise ClassesValidationError(
            f"Level {level} proficiency_bonus must be between 2 and 12."
        )
    return {
        "level": level,
        "proficiency_bonus": prof,
        "features": _clean_features(raw.get("features") or []),
        "trait_keys": _clean_trait_keys(raw.get("trait_keys") or []),
        "spell_slots": _clean_slot_map(
            raw.get("spell_slots") or {}, label="spell_slots", max_keys=_MAX_SPELL_SLOT_KEYS
        ),
        "resources": _clean_slot_map(
            raw.get("resources") or {}, label="resources", max_keys=_MAX_RESOURCE_KEYS
        ),
        "notes": str(raw.get("notes") or "")[:_MAX_NOTES_LEN],
    }


def _clean_level_progression(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise ClassesValidationError("level_progression must be a list.")
    if len(raw) != 20:
        raise ClassesValidationError("level_progression must contain exactly 20 rows.")
    rows = []
    for level in _LEVELS:
        source_row = raw[level - 1] if level - 1 < len(raw) else {}
        rows.append(_clean_progression_row(source_row, level))
    return rows


def _assert_entry_size(entry: dict[str, Any]) -> None:
    try:
        size = len(json.dumps(entry, separators=(",", ":"), ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise ClassesValidationError("Class entry is not serializable.") from exc
    if size > _MAX_ENTRY_BYTES:
        raise ClassesValidationError("Class entry exceeds maximum serialized size.")


def _clean_class_patch(raw: dict[str, Any]) -> dict[str, Any]:
    name = str(raw.get("name") or "").strip()
    if not name or len(name) > _MAX_NAME_LEN:
        raise ClassesValidationError("Class name must be 1-60 characters.")
    try:
        hit_die = int(raw.get("hit_die") or 8)
    except (TypeError, ValueError):
        raise ClassesValidationError("hit_die must be an integer.")
    if hit_die not in (4, 6, 8, 10, 12):
        raise ClassesValidationError("hit_die must be one of 4, 6, 8, 10, or 12.")
    patch = {
        "name": name,
        "summary": str(raw.get("summary") or "").strip()[:_MAX_SUMMARY_LEN],
        "hit_die": hit_die,
        "save_proficiencies": _clean_save_proficiencies(raw.get("save_proficiencies") or []),
        "skill_choices": _clean_skill_choices(raw.get("skill_choices") or {}),
        "trait_keys": _clean_trait_keys(raw.get("trait_keys") or []),
        "level_progression": _clean_level_progression(raw.get("level_progression") or []),
        "is_hidden": bool(raw.get("is_hidden")),
        "secret": bool(raw.get("secret")),
        "visible_to_owner": bool(raw.get("visible_to_owner", True)),
        "notes": str(raw.get("notes") or "").strip()[:_MAX_NOTES_LEN],
    }
    _assert_entry_size(patch)
    return patch


def update_class(campaign_id: int, key: str, raw: dict[str, Any]) -> dict[str, Any]:
    cfg = _config_for_campaign(campaign_id, lock=True)
    settings = cfg.settings_json
    entries = _ensure_compendium(settings)
    clean = _clean_class_patch(raw)
    for entry in entries:
        if entry.get("key") == key:
            entry.update(clean)
            merged = _normalize_entry(entry)
            entry.clear()
            entry.update(merged)
            cfg.settings_json = settings
            flag_modified(cfg, "settings_json")
            db.session.flush()
            return deepcopy(entry)
    raise ClassesValidationError("Class entry not found.")


def create_class(campaign_id: int, raw: dict[str, Any]) -> dict[str, Any]:
    cfg = _config_for_campaign(campaign_id, lock=True)
    settings = cfg.settings_json
    entries = _ensure_compendium(settings)
    clean = _clean_class_patch(raw)
    existing_keys = {entry["key"] for entry in entries}
    base_key = _slug(clean["name"])
    new_key = base_key
    suffix = 2
    while new_key in existing_keys:
        new_key = f"{base_key}-{suffix}"
        suffix += 1
    entry = _normalize_entry(
        {
            "key": new_key,
            "source": "custom",
            **clean,
        }
    )
    entries.append(entry)
    settings["classes_compendium"] = sorted(
        entries,
        key=lambda row: (row.get("source") == "custom", row["name"].lower()),
    )
    cfg.settings_json = settings
    flag_modified(cfg, "settings_json")
    db.session.flush()
    return deepcopy(entry)


def _level_row(entry: dict[str, Any], level: int) -> Optional[dict[str, Any]]:
    try:
        level_int = max(1, min(20, int(level or 1)))
    except (TypeError, ValueError):
        level_int = 1
    progression = entry.get("level_progression") or []
    for row in progression:
        if isinstance(row, dict) and int(row.get("level") or 0) == level_int:
            return deepcopy(row)
    if progression and isinstance(progression[0], dict):
        return deepcopy(progression[min(level_int - 1, len(progression) - 1)])
    return None


def _player_may_view(entry: dict[str, Any], *, owner_class_key: Optional[str]) -> bool:
    if not entry.get("is_hidden") and not entry.get("secret"):
        return True
    owner_key = str(owner_class_key or "").strip().lower()
    entry_key = str(entry.get("key") or "").strip().lower()
    if owner_key and owner_key == entry_key and entry.get("visible_to_owner"):
        return True
    return False


def _find_entry_for_character(
    campaign_id: int,
    *,
    class_key: Optional[str],
    class_name_fallback: Optional[str],
) -> Optional[dict[str, Any]]:
    entries = ensure_classes_compendium(campaign_id)
    needle = str(class_key or "").strip().lower()
    if needle:
        for entry in entries:
            if str(entry.get("key") or "").lower() == needle:
                return entry
    # Legacy name fallback — do not match hidden/secret entries by name alone.
    fallback_name = str(class_name_fallback or "").strip().lower()
    if fallback_name:
        for entry in entries:
            if entry.get("is_hidden") or entry.get("secret"):
                continue
            if str(entry.get("name") or "").strip().lower() == fallback_name:
                return entry
    return None


def resolve_character_class_details(
    campaign_id: int,
    *,
    class_key: Optional[str],
    level: Optional[int],
    class_name_fallback: Optional[str] = None,
    owner_class_key: Optional[str] = None,
) -> dict[str, Any]:
    """Build read-only class details for the active character popout."""
    entry = _find_entry_for_character(
        campaign_id,
        class_key=class_key,
        class_name_fallback=class_name_fallback,
    )
    if entry is None:
        return {
            "available": False,
            "hidden_message": "Class details are not available for this character.",
            "name": class_name_fallback,
            "level": level,
        }
    if not _player_may_view(entry, owner_class_key=owner_class_key or class_key):
        return {
            "available": False,
            "hidden_message": "Class details are hidden by the GM.",
            "name": entry.get("name") or class_name_fallback,
            "level": level,
        }
    try:
        level_int = max(1, min(20, int(level or 1)))
    except (TypeError, ValueError):
        level_int = 1
    current_row = _level_row(entry, level_int)
    next_row = _level_row(entry, level_int + 1) if level_int < 20 else None
    return {
        "available": True,
        "hidden_message": None,
        "key": entry.get("key"),
        "name": entry.get("name"),
        "summary": entry.get("summary") or "",
        "hit_die": entry.get("hit_die"),
        "save_proficiencies": list(entry.get("save_proficiencies") or []),
        "source": entry.get("source"),
        "level": level_int,
        "current_level_row": current_row,
        "next_level_row": next_row,
    }


def class_referenced_by_sheets(campaign_id: int, class_key: str) -> bool:
    """Return True if any campaign sheet references ``class_key``."""
    from app.models import Player, PlayerCharacterSheet

    rows = (
        db.session.query(PlayerCharacterSheet)
        .join(Player, Player.id == PlayerCharacterSheet.player_id)
        .filter(
            PlayerCharacterSheet.campaign_id == campaign_id,
            Player.is_npc.is_(False),
        )
        .all()
    )
    needle = str(class_key or "").strip().lower()
    for row in rows:
        sheet = row.sheet_json if isinstance(row.sheet_json, dict) else {}
        creation = sheet.get("creation") or {}
        if str(creation.get("class_key") or "").strip().lower() == needle:
            return True
    return False
