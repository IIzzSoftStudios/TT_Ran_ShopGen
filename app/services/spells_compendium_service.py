"""Campaign-scoped spell compendium stored in world settings JSON."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any, Optional

from sqlalchemy.orm.attributes import flag_modified

from app.extensions import db
from app.models import CampaignWorldConfig
from app.services.character_creation.dnd5e_spells import CORE_SPELLS, combat_snapshot_fields, spell_slug

_SCHOOLS = (
    "abjuration",
    "conjuration",
    "divination",
    "enchantment",
    "evocation",
    "illusion",
    "necromancy",
    "transmutation",
)
_ATTACK_TYPES = ("spell_attack", "save", None)
_SAVE_ABILITIES = ("str", "dex", "con", "int", "wis", "cha", None)

# Service-owned automation modes (single source of truth for routes/serializers/UI/tests).
AUTOMATION_MANUAL = "manual"
AUTOMATION_DIRECT_NUMERIC = "direct_numeric"
AUTOMATION_LEGACY_AUTO = "auto"  # Accepted on input; normalized to direct_numeric.

_AUTOMATION_INPUT = (AUTOMATION_MANUAL, AUTOMATION_DIRECT_NUMERIC, AUTOMATION_LEGACY_AUTO)

_UNSUPPORTED_SUMMARY_RE = re.compile(
    r"\b("
    r"summon(?:s|ed|ing)?|conjure[sd]?|create[sd]?\s+creature|"
    r"charm(?:ed|s)?|dominat(?:e|ed|ion)|counterspell|"
    r"reaction|terrain|long[\s-]?rest|multiclass|"
    r"polymorph|animate\s+dead|raise\s+dead|resurrect|"
    r"planar|teleport(?:ation)?\s+creature|"
    r"material\s+component.*consum|consumes?\s+a\s+material"
    r")\b",
    re.I,
)
_MULTI_TARGET_SUMMARY_RE = re.compile(
    r"\b("
    r"multiple\s+targets?|each\s+creature|all\s+creatures|"
    r"any\s+number\s+of|up\s+to\s+\d+\s+creatures|"
    r"two\s+creatures|three\s+creatures|four\s+creatures|"
    r"\d+\s+creatures|"
    r"three\s+darts?|\d+\s+darts?|"
    r"three\s+ranged\s+spell\s+attacks?|\d+\s+ranged\s+spell\s+attacks?|"
    r"each\s+target|additional\s+target"
    r")\b",
    re.I,
)
_MAX_NAME_LEN = 80
_MAX_SUMMARY_LEN = 500
_MAX_NOTES_LEN = 1000
_MAX_TEXT_LEN = 120
_MAX_CLASSES = 12
_MAX_CONDITIONS = 8
_MAX_ENTRY_BYTES = 65536
_LORE_DENY = re.compile(
    r"\b(bigby|melf|mordenkainen|nystul|otiluke|leomund|drawmij|otto|tasha|tenser|evard)\b",
    re.I,
)


class SpellsValidationError(ValueError):
    """Raised when spell compendium input is invalid."""


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


def _default_spell_entry(raw: dict[str, Any], *, source: str = "base") -> dict[str, Any]:
    return {
        "key": str(raw.get("key") or spell_slug(raw.get("name") or "spell")),
        "name": str(raw.get("name") or "Spell"),
        "source": source,
        "level": int(raw.get("level") or 0),
        "school": str(raw.get("school") or "evocation"),
        "casting_time": str(raw.get("casting_time") or "1 action"),
        "range_text": str(raw.get("range_text") or "60 feet"),
        "range_ft": int(raw.get("range_ft") or 60),
        "components": str(raw.get("components") or "V, S"),
        "material_component": str(raw.get("material_component") or ""),
        "duration": str(raw.get("duration") or "Instantaneous"),
        "concentration": bool(raw.get("concentration")),
        "ritual": bool(raw.get("ritual")),
        "classes": list(raw.get("classes") or []),
        "attack_type": raw.get("attack_type"),
        "save_ability": raw.get("save_ability"),
        "damage": raw.get("damage"),
        "damage_type": raw.get("damage_type"),
        "healing": raw.get("healing"),
        "area": raw.get("area"),
        "conditions": list(raw.get("conditions") or []),
        "upcast": dict(raw.get("upcast") or {}),
        "automation": str(raw.get("automation") or "manual"),
        "summary": str(raw.get("summary") or "")[:_MAX_SUMMARY_LEN],
        "srd_reference": str(raw.get("srd_reference") or "SRD 5.1"),
        "is_hidden": bool(raw.get("is_hidden")),
        "secret": bool(raw.get("secret")),
        "visible_to_owner": bool(raw.get("visible_to_owner", True)),
        "notes": str(raw.get("notes") or "")[:_MAX_NOTES_LEN],
    }


def _clean_text(value: Any, *, label: str, max_len: int) -> str:
    text = str(value or "").strip()
    if len(text) > max_len:
        raise SpellsValidationError(f"{label} must be at most {max_len} characters.")
    return text


def _clean_level(value: Any) -> int:
    try:
        level = int(value)
    except (TypeError, ValueError):
        raise SpellsValidationError("level must be an integer.")
    if not (0 <= level <= 9):
        raise SpellsValidationError("level must be between 0 and 9.")
    return level


def _clean_area(raw: Any) -> Optional[dict[str, Any]]:
    if raw in (None, "", {}):
        return None
    if not isinstance(raw, dict):
        raise SpellsValidationError("area must be an object.")
    shape = _clean_text(raw.get("shape"), label="area.shape", max_len=20).lower()
    try:
        size_ft = int(raw.get("size_ft") or 0)
    except (TypeError, ValueError):
        raise SpellsValidationError("area.size_ft must be an integer.")
    if size_ft < 0 or size_ft > 500:
        raise SpellsValidationError("area.size_ft must be between 0 and 500.")
    return {"shape": shape, "size_ft": size_ft}


def _clean_upcast(raw: Any) -> dict[str, str]:
    if raw in (None, "", {}):
        return {}
    if not isinstance(raw, dict):
        raise SpellsValidationError("upcast must be an object.")
    clean: dict[str, str] = {}
    for key, value in raw.items():
        slot_key = _clean_text(key, label="upcast key", max_len=40)
        clean[slot_key] = _clean_text(value, label="upcast value", max_len=40)
    return clean


def normalize_automation(value: Any) -> str:
    """Normalize client/seed automation values to service-owned modes."""
    raw = str(value or AUTOMATION_MANUAL).strip().lower()
    if raw == AUTOMATION_LEGACY_AUTO:
        return AUTOMATION_DIRECT_NUMERIC
    if raw in (AUTOMATION_MANUAL, AUTOMATION_DIRECT_NUMERIC):
        return raw
    return AUTOMATION_MANUAL


def is_direct_numeric_automation(value: Any) -> bool:
    return normalize_automation(value) == AUTOMATION_DIRECT_NUMERIC


def _forces_manual_automation(entry: dict[str, Any]) -> bool:
    """Unsupported subsystems and multi-target/area spells stay manual for MVP."""
    if entry.get("area"):
        return True
    if entry.get("conditions"):
        return True
    summary = str(entry.get("summary") or "")
    if _UNSUPPORTED_SUMMARY_RE.search(summary):
        return True
    if _MULTI_TARGET_SUMMARY_RE.search(summary):
        return True
    range_text = str(entry.get("range_text") or "")
    if re.search(r"\b(line|cone|cube|sphere|cylinder|radius|emanation)\b", range_text, re.I):
        return True
    return False


def _infer_automation(entry: dict[str, Any]) -> str:
    requested = normalize_automation(entry.get("automation"))
    if _forces_manual_automation(entry):
        return AUTOMATION_MANUAL
    if requested == AUTOMATION_DIRECT_NUMERIC and not (
        entry.get("attack_type")
        or entry.get("save_ability")
        or entry.get("damage")
        or entry.get("healing")
    ):
        return AUTOMATION_MANUAL
    return requested


def _assert_entry_size(entry: dict[str, Any]) -> None:
    try:
        size = len(json.dumps(entry, separators=(",", ":"), ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise SpellsValidationError("Spell entry is not serializable.") from exc
    if size > _MAX_ENTRY_BYTES:
        raise SpellsValidationError("Spell entry exceeds maximum serialized size.")


def _normalize_entry(raw: dict[str, Any]) -> dict[str, Any]:
    source = str(raw.get("source") or "custom")
    base = _default_spell_entry(raw, source=source)
    base.update(deepcopy(raw))

    name = _clean_text(base.get("name"), label="name", max_len=_MAX_NAME_LEN)
    if _LORE_DENY.search(name):
        raise SpellsValidationError("Spell name contains Product Identity terms.")

    level = _clean_level(base.get("level"))
    school = _clean_text(base.get("school"), label="school", max_len=20).lower()
    if school not in _SCHOOLS:
        raise SpellsValidationError(f"Invalid school: {school}.")

    attack_type = base.get("attack_type")
    if attack_type not in _ATTACK_TYPES:
        raise SpellsValidationError("attack_type must be spell_attack, save, or null.")

    save_ability = base.get("save_ability")
    if save_ability is not None:
        save_ability = str(save_ability).strip().lower()
        if save_ability not in _SAVE_ABILITIES[:-1]:
            raise SpellsValidationError("Invalid save_ability.")
    else:
        save_ability = None

    classes = base.get("classes") or []
    if not isinstance(classes, list) or len(classes) > _MAX_CLASSES:
        raise SpellsValidationError("classes must be a list with at most 12 entries.")
    clean_classes = []
    for item in classes:
        cls = _clean_text(item, label="class", max_len=20).lower()
        if cls and cls not in clean_classes:
            clean_classes.append(cls)

    conditions = base.get("conditions") or []
    if not isinstance(conditions, list) or len(conditions) > _MAX_CONDITIONS:
        raise SpellsValidationError("conditions must be a list with at most 8 entries.")
    clean_conditions = [
        _clean_text(item, label="condition", max_len=30).lower()
        for item in conditions
        if str(item or "").strip()
    ]

    try:
        range_ft = int(base.get("range_ft") or 0)
    except (TypeError, ValueError):
        raise SpellsValidationError("range_ft must be an integer.")
    if range_ft < 0 or range_ft > 1000:
        raise SpellsValidationError("range_ft must be between 0 and 1000.")

    entry = {
        "key": str(base.get("key") or spell_slug(name)),
        "name": name,
        "source": source,
        "level": level,
        "school": school,
        "casting_time": _clean_text(base.get("casting_time"), label="casting_time", max_len=_MAX_TEXT_LEN),
        "range_text": _clean_text(base.get("range_text"), label="range_text", max_len=_MAX_TEXT_LEN),
        "range_ft": range_ft,
        "components": _clean_text(base.get("components"), label="components", max_len=_MAX_TEXT_LEN),
        "material_component": _clean_text(
            base.get("material_component"), label="material_component", max_len=_MAX_TEXT_LEN
        ),
        "duration": _clean_text(base.get("duration"), label="duration", max_len=_MAX_TEXT_LEN),
        "concentration": bool(base.get("concentration")),
        "ritual": bool(base.get("ritual")),
        "classes": clean_classes,
        "attack_type": attack_type,
        "save_ability": save_ability,
        "damage": base.get("damage") if base.get("damage") in (None, "") else _clean_text(base.get("damage"), label="damage", max_len=20),
        "damage_type": base.get("damage_type") if base.get("damage_type") in (None, "") else _clean_text(base.get("damage_type"), label="damage_type", max_len=20).lower(),
        "healing": base.get("healing") if base.get("healing") in (None, "") else _clean_text(base.get("healing"), label="healing", max_len=20),
        "area": _clean_area(base.get("area")),
        "conditions": clean_conditions,
        "upcast": _clean_upcast(base.get("upcast")),
        "summary": _clean_text(base.get("summary"), label="summary", max_len=_MAX_SUMMARY_LEN),
        "srd_reference": _clean_text(base.get("srd_reference"), label="srd_reference", max_len=40),
        "is_hidden": bool(base.get("is_hidden")),
        "secret": bool(base.get("secret")),
        "visible_to_owner": bool(base.get("visible_to_owner", True)),
        "notes": _clean_text(base.get("notes"), label="notes", max_len=_MAX_NOTES_LEN),
    }
    entry["automation"] = _infer_automation({**entry, "automation": base.get("automation")})
    _assert_entry_size(entry)
    return entry


def _ensure_compendium(settings: dict[str, Any]) -> list[dict[str, Any]]:
    compendium = settings.get("spells_compendium")
    if not isinstance(compendium, list):
        compendium = []

    by_key: dict[str, dict[str, Any]] = {}
    for raw in compendium:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        key = str(raw.get("key") or spell_slug(name))
        entry = _normalize_entry({**raw, "key": key, "name": name})
        by_key[key] = entry

    for raw in CORE_SPELLS:
        key = str(raw["key"])
        if key not in by_key:
            by_key[key] = _normalize_entry({**deepcopy(raw), "source": "base"})
        else:
            existing = by_key[key]
            if existing.get("source") in (None, "default"):
                existing["source"] = "base"
            for field in (
                "summary",
                "school",
                "classes",
                "automation",
                "damage",
                "healing",
                "attack_type",
            ):
                if not existing.get(field) and raw.get(field):
                    existing[field] = deepcopy(raw[field])

    entries = sorted(
        by_key.values(),
        key=lambda row: (row.get("level", 0), row["name"].lower()),
    )
    settings["spells_compendium"] = entries
    return entries


def ensure_spells_compendium(campaign_id: int) -> list[dict[str, Any]]:
    cfg = _config_for_campaign(campaign_id)
    settings = cfg.settings_json
    entries = _ensure_compendium(settings)
    cfg.settings_json = settings
    flag_modified(cfg, "settings_json")
    db.session.flush()
    return deepcopy(entries)


def list_spells(campaign_id: int) -> list[dict[str, Any]]:
    return ensure_spells_compendium(campaign_id)


def list_visible_spells(campaign_id: int) -> list[dict[str, Any]]:
    return [
        entry
        for entry in ensure_spells_compendium(campaign_id)
        if not entry.get("is_hidden") and not entry.get("secret")
    ]


def get_spell_entry(campaign_id: int, key: str) -> Optional[dict[str, Any]]:
    needle = str(key or "").strip().lower()
    if not needle:
        return None
    for entry in ensure_spells_compendium(campaign_id):
        if str(entry.get("key") or "").lower() == needle:
            return deepcopy(entry)
    return None


def _clean_spell_patch(raw: dict[str, Any]) -> dict[str, Any]:
    patch = _normalize_entry({**raw, "source": raw.get("source") or "custom"})
    return patch


def update_spell(campaign_id: int, key: str, raw: dict[str, Any]) -> dict[str, Any]:
    cfg = _config_for_campaign(campaign_id, lock=True)
    settings = cfg.settings_json
    entries = _ensure_compendium(settings)
    clean = _clean_spell_patch(raw)
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
    raise SpellsValidationError("Spell entry not found.")


def create_spell(campaign_id: int, raw: dict[str, Any]) -> dict[str, Any]:
    cfg = _config_for_campaign(campaign_id, lock=True)
    settings = cfg.settings_json
    entries = _ensure_compendium(settings)
    clean = _clean_spell_patch(raw)
    existing_keys = {entry["key"] for entry in entries}
    base_key = spell_slug(clean["name"])
    new_key = base_key
    suffix = 2
    while new_key in existing_keys:
        new_key = f"{base_key}_{suffix}"
        suffix += 1
    entry = _normalize_entry(
        {
            "key": new_key,
            "source": "custom",
            **clean,
        }
    )
    entries.append(entry)
    settings["spells_compendium"] = sorted(
        entries,
        key=lambda row: (row.get("level", 0), row["name"].lower()),
    )
    cfg.settings_json = settings
    flag_modified(cfg, "settings_json")
    db.session.flush()
    return deepcopy(entry)


def _player_may_view(entry: dict[str, Any], *, owner_spell_keys: Optional[set[str]] = None) -> bool:
    if not entry.get("is_hidden") and not entry.get("secret"):
        return True
    owner_keys = {str(k or "").lower() for k in (owner_spell_keys or set())}
    entry_key = str(entry.get("key") or "").strip().lower()
    if entry_key in owner_keys and entry.get("visible_to_owner"):
        return True
    return False


def resolve_spell_keys(
    campaign_id: int,
    keys: list[str],
    *,
    owner_spell_keys: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
    """Resolve spell keys to player-safe definitions."""
    resolved = []
    owner = {str(k or "").lower() for k in (owner_spell_keys or keys or [])}
    for key in keys:
        entry = get_spell_entry(campaign_id, key)
        if entry is None:
            continue
        if not _player_may_view(entry, owner_spell_keys=owner):
            continue
        resolved.append(entry)
    return resolved


def resolve_character_spells(
    campaign_id: int,
    sheet: dict[str, Any],
) -> dict[str, Any]:
    """Build spell details for character views from sheet spell keys."""
    spells_state = sheet.get("spells") if isinstance(sheet.get("spells"), dict) else {}
    known = [str(k) for k in (spells_state.get("known") or []) if str(k).strip()]
    prepared = [str(k) for k in (spells_state.get("prepared") or []) if str(k).strip()]
    cantrips = [str(k) for k in (spells_state.get("cantrips") or []) if str(k).strip()]
    owner_keys = set(known) | set(prepared) | set(cantrips)

    return {
        "known": resolve_spell_keys(campaign_id, known, owner_spell_keys=owner_keys),
        "prepared": resolve_spell_keys(campaign_id, prepared, owner_spell_keys=owner_keys),
        "cantrips": resolve_spell_keys(campaign_id, cantrips, owner_spell_keys=owner_keys),
        "slots_used": dict(spells_state.get("slots_used") or {}),
    }


def combat_spell_snapshots(
    campaign_id: int,
    spell_keys: list[str],
) -> list[dict[str, Any]]:
    """Snapshot combat-relevant spell metadata for encounter combatants."""
    snapshots = []
    for key in spell_keys:
        entry = get_spell_entry(campaign_id, key)
        if entry is None:
            continue
        snap = combat_snapshot_fields(entry)
        snap["automation"] = _infer_automation(snap)
        snapshots.append(snap)
    return snapshots
