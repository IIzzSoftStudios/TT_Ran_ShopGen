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
from app.services.character_creation.dnd5e_srd_class_progression import (
    CURRENT_SRD_SEED_VERSION,
    SRD_CLASS_PROGRESSIONS,
)
from app.services.character_creation.dnd5e_srd_subclasses import (
    CORE_SUBCLASSES_BY_CLASS,
    CURRENT_SRD_SUBCLASSES_SEED_VERSION,
)
from app.services.character_creation.progression_helpers import resolve_spell_slots_from_row

_ABILITIES = ("str", "dex", "con", "int", "wis", "cha")
_SPELLCASTING_TYPES = frozenset({"none", "full", "half", "third", "pact", "known"})
_PLAYER_CHOICE_TYPES = frozenset(
    {
        "ability_scores",
        "invocations",
        "pact_boon",
        "mystic_arcanum",
        "subclass",
        "feat",
        "custom",
        "spell",
        "spells",
        "cantrip",
        "cantrips",
        "trait_pick",
    }
)
_MAX_NAME_LEN = 60
_MAX_SUMMARY_LEN = 500
_MAX_NOTES_LEN = 1000
_MAX_FEATURES_PER_LEVEL = 12
_MAX_FEATURE_NAME = 80
_MAX_FEATURE_DESC = 500
_MAX_RESOURCE_KEYS = 10
_MAX_SPELL_SLOT_KEYS = 10
_MAX_ENTRY_BYTES = 65536
_MAX_SUBCLASSES_PER_CLASS = 12
_MAX_FEATURE_GRANTS = 8
_MAX_SUBCLASS_TAGLINE = 120
_MAX_SUBCLASS_NAME = 80
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


_ASI_LEVELS = frozenset({4, 8, 12, 16, 19})
_ASI_FEATURE = {
    "name": "Ability Score Improvement",
    "description": "Increase one ability score by 2, or two ability scores by 1 each.",
}


def _is_asi_feature_name(name: str) -> bool:
    lowered = str(name or "").lower()
    return "ability score" in lowered and ("improvement" in lowered or "increase" in lowered)


def _trait_catalog_for_campaign(campaign_id: int) -> dict[str, dict[str, Any]]:
    from app.services.traits_compendium_service import ensure_traits_compendium

    return {
        str(row.get("key") or "").strip().lower(): row
        for row in ensure_traits_compendium(campaign_id)
    }


def _sync_progression_features_from_traits(
    campaign_id: int,
    level_progression: list[dict[str, Any]],
) -> None:
    """Derive player-facing feature labels from per-level trait_keys."""
    catalog = _trait_catalog_for_campaign(campaign_id)
    for row in level_progression:
        if not isinstance(row, dict):
            continue
        trait_keys = row.get("trait_keys") or []
        if not trait_keys:
            continue
        derived: list[dict[str, str]] = []
        for key in trait_keys:
            clean = str(key or "").strip().lower()
            if not clean:
                continue
            trait = catalog.get(clean) or {}
            derived.append(
                {
                    "name": str(trait.get("name") or clean)[:_MAX_FEATURE_NAME],
                    "description": str(trait.get("summary") or trait.get("notes") or "")[
                        :_MAX_FEATURE_DESC
                    ],
                }
            )
        asi_feats = [
            feat
            for feat in row.get("features") or []
            if isinstance(feat, dict) and _is_asi_feature_name(feat.get("name"))
        ]
        if not asi_feats and int(row.get("level") or 0) in _ASI_LEVELS:
            asi_feats = [deepcopy(_ASI_FEATURE)]
        row["features"] = derived + asi_feats


def accumulated_class_trait_keys(
    class_entry: dict[str, Any] | None,
    level: int,
    *,
    sheet: dict[str, Any] | None = None,
) -> list[str]:
    """Trait keys granted by class-wide and per-level progression up to ``level``."""
    keys: list[str] = []
    seen: set[str] = set()

    def add(raw_keys: Any) -> None:
        if isinstance(raw_keys, str):
            parts = [part.strip().lower() for part in raw_keys.split(",") if part.strip()]
        elif isinstance(raw_keys, list):
            parts = [str(part or "").strip().lower() for part in raw_keys if str(part or "").strip()]
        else:
            parts = []
        for clean in parts:
            if clean and clean not in seen:
                seen.add(clean)
                keys.append(clean)

    try:
        level_int = max(1, min(20, int(level or 1)))
    except (TypeError, ValueError):
        level_int = 1

    if class_entry:
        add(class_entry.get("trait_keys"))
        for row in class_entry.get("level_progression") or []:
            if not isinstance(row, dict):
                continue
            try:
                row_level = int(row.get("level") or 0)
            except (TypeError, ValueError):
                continue
            if row_level <= level_int:
                add(row.get("trait_keys"))

    if isinstance(sheet, dict):
        selections = sheet.get("class_trait_selections")
        if isinstance(selections, dict):
            for lvl in range(1, level_int + 1):
                add(selections.get(str(lvl)) or selections.get(lvl))

        creation = sheet.get("creation") if isinstance(sheet.get("creation"), dict) else {}
        subclass_key = str(creation.get("subclass_key") or "").strip().lower()
        if subclass_key and class_entry:
            add(
                subclass_trait_keys_for_level(
                    class_entry,
                    subclass_key,
                    level_int,
                )
            )

    return keys


def subclass_trait_keys_for_level(
    class_entry: dict[str, Any],
    subclass_key: str,
    level: int,
) -> list[str]:
    """Trait keys from a subclass's feature_grants up to ``level``."""
    subclass = find_subclass_on_class(class_entry, subclass_key)
    if not subclass:
        return []
    try:
        level_int = max(1, min(20, int(level or 1)))
    except (TypeError, ValueError):
        level_int = 1
    keys: list[str] = []
    seen: set[str] = set()
    for grant in subclass.get("feature_grants") or []:
        if not isinstance(grant, dict):
            continue
        try:
            grant_level = int(grant.get("level") or 0)
        except (TypeError, ValueError):
            continue
        if grant_level > level_int:
            continue
        for raw_key in grant.get("trait_keys") or []:
            clean = str(raw_key or "").strip().lower()
            if clean and clean not in seen:
                seen.add(clean)
                keys.append(clean)
    return keys


def find_subclass_on_class(
    class_entry: dict[str, Any] | None,
    subclass_key: str,
) -> dict[str, Any] | None:
    if not class_entry:
        return None
    needle = str(subclass_key or "").strip().lower()
    if not needle:
        return None
    for row in class_entry.get("subclasses") or []:
        if isinstance(row, dict) and str(row.get("key") or "").strip().lower() == needle:
            return row
    return None


def list_visible_subclasses_for_class(
    class_entry: dict[str, Any] | None,
    *,
    owner_subclass_key: str | None = None,
) -> list[dict[str, Any]]:
    """Subclasses a player may pick or view for a class entry."""
    if not class_entry:
        return []
    owner_key = str(owner_subclass_key or "").strip().lower()
    visible: list[dict[str, Any]] = []
    for row in class_entry.get("subclasses") or []:
        if not isinstance(row, dict):
            continue
        row_key = str(row.get("key") or "").strip().lower()
        if row.get("is_hidden") or row.get("secret"):
            if not (owner_key and owner_key == row_key and row.get("visible_to_owner")):
                continue
        visible.append(deepcopy(row))
    return visible


def subclass_pick_level(class_entry: dict[str, Any] | None) -> int | None:
    """Default subclass pick level from configured subclasses or class progression."""
    if not class_entry:
        return None
    levels = [
        int(row.get("pick_level") or 0)
        for row in (class_entry.get("subclasses") or [])
        if isinstance(row, dict) and int(row.get("pick_level") or 0) > 0
    ]
    if levels:
        return min(levels)
    return None


def _default_progression_row(level: int) -> dict[str, Any]:
    features: list[dict[str, str]] = []
    if level in _ASI_LEVELS:
        features = [deepcopy(_ASI_FEATURE)]
    return {
        "level": level,
        "proficiency_bonus": _proficiency_bonus(level),
        "features": features,
        "trait_keys": [],
        "spell_slots": {},
        "pact_magic": None,
        "resources": {},
        "cantrips_known": None,
        "spells_known": None,
        "spells_prepared": None,
        "invocations_known": None,
        "player_choices": [],
        "progression_stats": {},
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
        "spellcasting": _default_spellcasting(raw),
        "progression_columns": list(raw.get("progression_columns") or []),
        "level_progression": [_default_progression_row(level) for level in _LEVELS],
        "srd_seed_version": int(raw.get("srd_seed_version") or 0),
        "progression_customized": bool(raw.get("progression_customized")),
        "is_hidden": bool(raw.get("is_hidden")),
        "secret": bool(raw.get("secret")),
        "visible_to_owner": bool(raw.get("visible_to_owner", True)),
        "notes": str(raw.get("notes") or "")[:_MAX_NOTES_LEN],
        "subclasses": list(raw.get("subclasses") or []),
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
    base["spellcasting"] = _clean_spellcasting(base.get("spellcasting") or {})
    base["progression_columns"] = _clean_progression_columns(base.get("progression_columns") or [])
    base["level_progression"] = _clean_level_progression(
        base.get("level_progression") or []
    )
    base["srd_seed_version"] = int(base.get("srd_seed_version") or 0)
    base["progression_customized"] = bool(base.get("progression_customized"))
    base["is_hidden"] = bool(base.get("is_hidden"))
    base["secret"] = bool(base.get("secret"))
    base["visible_to_owner"] = bool(base.get("visible_to_owner", True))
    base["notes"] = str(base.get("notes") or "")[:_MAX_NOTES_LEN]
    base["summary"] = str(base.get("summary") or "")[:_MAX_SUMMARY_LEN]
    base["subclasses"] = _clean_subclasses(base.get("subclasses") or [])
    try:
        hit_die = int(base.get("hit_die") or 8)
    except (TypeError, ValueError):
        hit_die = 8
    if hit_die not in (4, 6, 8, 10, 12):
        hit_die = 8
    base["hit_die"] = hit_die
    _assert_entry_size(base)
    return base


def _apply_srd_progression_seed(entry: dict[str, Any]) -> None:
    """Replace spellcasting, columns, and level progression from SRD tables."""
    key = str(entry.get("key") or "").strip().lower()
    seed = SRD_CLASS_PROGRESSIONS.get(key)
    if not seed:
        return
    if seed.get("spellcasting"):
        entry["spellcasting"] = deepcopy(seed["spellcasting"])
    if seed.get("progression_columns"):
        entry["progression_columns"] = deepcopy(seed["progression_columns"])
    seeded_rows = seed.get("level_progression") or []
    if len(seeded_rows) != 20:
        return
    entry["level_progression"] = [deepcopy(row) for row in seeded_rows]


def _apply_srd_subclasses_seed(entry: dict[str, Any]) -> None:
    """Merge SRD subclass shells into a base class when not GM-customized."""
    key = str(entry.get("key") or "").strip().lower()
    seeds = CORE_SUBCLASSES_BY_CLASS.get(key)
    if not seeds:
        return
    existing = entry.get("subclasses")
    if not isinstance(existing, list):
        existing = []
    by_sub_key: dict[str, dict[str, Any]] = {}
    for raw in existing:
        if not isinstance(raw, dict):
            continue
        sub_key = str(raw.get("key") or _slug(raw.get("name") or "subclass"))
        by_sub_key[sub_key] = raw
    for seed in seeds:
        sub_key = str(seed.get("key") or "")
        current = by_sub_key.get(sub_key)
        if current is None:
            by_sub_key[sub_key] = deepcopy(seed)
            continue
        if current.get("gm_edited"):
            continue
        current_version = int(current.get("srd_seed_version") or 0)
        seed_version = int(seed.get("srd_seed_version") or CURRENT_SRD_SUBCLASSES_SEED_VERSION)
        if current_version < seed_version:
            merged = deepcopy(seed)
            merged["notes"] = current.get("notes") or ""
            by_sub_key[sub_key] = merged
    entry["subclasses"] = sorted(
        [_normalize_subclass(row) for row in by_sub_key.values()],
        key=lambda row: (row.get("source") == "custom", row["name"].lower()),
    )
    _ensure_subclass_player_choice(entry)


def _ensure_subclass_player_choice(entry: dict[str, Any]) -> None:
    """Inject a subclass player choice at pick_level when subclasses exist."""
    subclasses = [
        row
        for row in (entry.get("subclasses") or [])
        if isinstance(row, dict) and not row.get("is_hidden") and not row.get("secret")
    ]
    if not subclasses:
        return
    pick_level = min(int(row.get("pick_level") or 3) for row in subclasses)
    progression = entry.get("level_progression") or []
    for row in progression:
        if not isinstance(row, dict) or int(row.get("level") or 0) != pick_level:
            continue
        choices = list(row.get("player_choices") or [])
        if any(str(c.get("type") or "").strip().lower() == "subclass" for c in choices if isinstance(c, dict)):
            return
        choices.append(
            {
                "type": "subclass",
                "title": "Choose Subclass",
                "description": "Select your subclass specialization.",
            }
        )
        row["player_choices"] = choices
        return


def _apply_srd_seed_to_entry(entry: dict[str, Any]) -> None:
    """Merge SRD progression into a base class when not GM-customized."""
    if entry.get("progression_customized"):
        _apply_srd_subclasses_seed(entry)
        return
    if str(entry.get("source") or "") != "base":
        return
    key = str(entry.get("key") or "").strip().lower()
    if not SRD_CLASS_PROGRESSIONS.get(key):
        _apply_srd_subclasses_seed(entry)
        return
    current_version = int(entry.get("srd_seed_version") or 0)
    if current_version >= CURRENT_SRD_SEED_VERSION:
        _apply_srd_subclasses_seed(entry)
        return
    _apply_srd_progression_seed(entry)
    entry["srd_seed_version"] = CURRENT_SRD_SEED_VERSION
    _apply_srd_subclasses_seed(entry)


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
            _apply_srd_seed_to_entry(existing)

    for entry in by_key.values():
        if str(entry.get("source") or "") == "base":
            _apply_srd_seed_to_entry(entry)

    entries = sorted(
        by_key.values(),
        key=lambda row: (row.get("source") == "custom", row["name"].lower()),
    )
    settings["classes_compendium"] = entries
    return entries


def ensure_classes_compendium(campaign_id: int) -> list[dict[str, Any]]:
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


def _clean_slot_map(raw: Any, *, label: str, max_keys: int, max_key_len: int = 8) -> dict[str, int]:
    if raw is None or raw == "":
        return {}
    if not isinstance(raw, dict):
        raise ClassesValidationError(f"{label} must be an object.")
    if len(raw) > max_keys:
        raise ClassesValidationError(f"{label} has too many keys.")
    clean: dict[str, int] = {}
    for key, value in raw.items():
        slot_key = str(key).strip()
        if not slot_key or len(slot_key) > max_key_len:
            raise ClassesValidationError(f"Invalid {label} key: {key}.")
        try:
            slots = int(value)
        except (TypeError, ValueError):
            raise ClassesValidationError(f"{label} values must be integers.")
        if slots < 0 or slots > 99:
            raise ClassesValidationError(f"{label} values must be between 0 and 99.")
        clean[slot_key] = slots
    return clean


def _default_spellcasting(raw: dict[str, Any]) -> dict[str, str]:
    spellcasting = raw.get("spellcasting")
    if isinstance(spellcasting, dict) and spellcasting.get("type"):
        return {
            "type": str(spellcasting.get("type") or "none"),
            "ability": str(spellcasting.get("ability") or "int"),
        }
    return {"type": "none", "ability": "int"}


def _clean_spellcasting(raw: Any) -> dict[str, str]:
    if raw is None or raw == "":
        return {"type": "none", "ability": "int"}
    if not isinstance(raw, dict):
        raise ClassesValidationError("spellcasting must be an object.")
    spell_type = str(raw.get("type") or "none").strip().lower()
    if spell_type not in _SPELLCASTING_TYPES:
        raise ClassesValidationError(f"Invalid spellcasting.type: {spell_type}.")
    ability = str(raw.get("ability") or "int").strip().lower()
    if ability not in _ABILITIES:
        raise ClassesValidationError(f"Invalid spellcasting.ability: {ability}.")
    return {"type": spell_type, "ability": ability}


def _clean_progression_columns(raw: Any) -> list[dict[str, str]]:
    if raw is None or raw == "":
        return []
    if not isinstance(raw, list) or len(raw) > 8:
        raise ClassesValidationError("progression_columns must be a list of at most 8 entries.")
    clean: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        if isinstance(item, str):
            key = item.strip().lower()[:32]
            label = key.replace("_", " ").title()
        elif isinstance(item, dict):
            key = str(item.get("key") or "").strip().lower()[:32]
            label = str(item.get("label") or key).strip()[:40]
        else:
            raise ClassesValidationError("Each progression_columns entry must be an object or string.")
        if not key or key in seen:
            continue
        seen.add(key)
        clean.append({"key": key, "label": label or key})
    return clean


def _clean_optional_count(
    raw: Any,
    *,
    label: str,
    max_value: int,
) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ClassesValidationError(f"{label} must be an integer.")
    if value < 0 or value > max_value:
        raise ClassesValidationError(f"{label} must be between 0 and {max_value}.")
    return value


def _clean_pact_magic(raw: Any) -> dict[str, int] | None:
    if raw is None or raw == "":
        return None
    if not isinstance(raw, dict):
        raise ClassesValidationError("pact_magic must be an object.")
    try:
        slots = int(raw.get("slots") or 0)
        slot_level = int(raw.get("slot_level") or 1)
    except (TypeError, ValueError):
        raise ClassesValidationError("pact_magic slots and slot_level must be integers.")
    if slots < 0 or slots > 99:
        raise ClassesValidationError("pact_magic.slots must be between 0 and 99.")
    if slot_level < 1 or slot_level > 9:
        raise ClassesValidationError("pact_magic.slot_level must be between 1 and 9.")
    if slots == 0:
        return None
    return {"slots": slots, "slot_level": slot_level}


def _clean_trait_pools(raw: Any) -> list[dict[str, Any]]:
    if raw is None or raw == "":
        return []
    if not isinstance(raw, list) or len(raw) > 4:
        raise ClassesValidationError("trait_pools must be a list of at most 4 entries.")
    clean: list[dict[str, Any]] = []
    for pool in raw:
        if not isinstance(pool, dict):
            raise ClassesValidationError("Each trait_pool must be an object.")
        title = str(pool.get("title") or "Class feature choice").strip()[:80]
        pool_tag = str(pool.get("pool_tag") or "").strip().lower()
        if not pool_tag or not re.match(r"^[a-z0-9][a-z0-9-]{0,39}$", pool_tag):
            raise ClassesValidationError(f"Invalid trait_pool pool_tag: {pool_tag!r}.")
        entry: dict[str, Any] = {"title": title, "pool_tag": pool_tag}
        description = str(pool.get("description") or "").strip()[:500]
        if description:
            entry["description"] = description
        cap_field = str(pool.get("cap_field") or "").strip()
        if cap_field:
            entry["cap_field"] = cap_field[:32]
        if pool.get("pick") not in (None, ""):
            try:
                pick = int(pool.get("pick"))
            except (TypeError, ValueError):
                raise ClassesValidationError("trait_pool pick must be an integer.") from None
            if pick < 1 or pick > 20:
                raise ClassesValidationError("trait_pool pick must be between 1 and 20.")
            entry["pick"] = pick
        clean.append(entry)
    return clean


def _clean_player_choices(raw: Any) -> list[dict[str, str]]:
    if raw is None or raw == "":
        return []
    if not isinstance(raw, list) or len(raw) > 8:
        raise ClassesValidationError("player_choices must be a list of at most 8 entries.")
    clean: list[dict[str, str]] = []
    for choice in raw:
        if not isinstance(choice, dict):
            raise ClassesValidationError("Each player_choice must be an object.")
        choice_type = str(choice.get("type") or "custom").strip().lower()
        if choice_type not in _PLAYER_CHOICE_TYPES:
            raise ClassesValidationError(f"Invalid player_choice type: {choice_type}.")
        title = str(choice.get("title") or choice.get("name") or "Choice").strip()[:80]
        description = str(choice.get("description") or "").strip()[:500]
        if title:
            clean.append({"type": choice_type, "title": title, "description": description})
    return clean


def _clean_progression_stats(raw: Any) -> dict[str, int]:
    return _clean_slot_map(raw, label="progression_stats", max_keys=8, max_key_len=32)


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


def _default_subclass_entry(raw: dict[str, Any], *, source: str = "custom") -> dict[str, Any]:
    return {
        "key": str(raw.get("key") or _slug(raw.get("name") or "subclass")),
        "name": str(raw.get("name") or "Subclass")[:_MAX_SUBCLASS_NAME],
        "source": source,
        "tagline": str(raw.get("tagline") or "")[:_MAX_SUBCLASS_TAGLINE],
        "summary": str(raw.get("summary") or "")[:_MAX_SUMMARY_LEN],
        "pick_level": int(raw.get("pick_level") or 3),
        "feature_grants": list(raw.get("feature_grants") or []),
        "is_hidden": bool(raw.get("is_hidden")),
        "secret": bool(raw.get("secret")),
        "visible_to_owner": bool(raw.get("visible_to_owner", True)),
        "srd_seed_version": int(raw.get("srd_seed_version") or 0),
        "gm_edited": bool(raw.get("gm_edited")),
        "notes": str(raw.get("notes") or "")[:_MAX_NOTES_LEN],
    }


def _clean_feature_grants(raw: Any) -> list[dict[str, Any]]:
    if raw is None or raw == "":
        return []
    if not isinstance(raw, list) or len(raw) > _MAX_FEATURE_GRANTS:
        raise ClassesValidationError(
            f"feature_grants must be a list of at most {_MAX_FEATURE_GRANTS} entries."
        )
    clean: list[dict[str, Any]] = []
    for grant in raw:
        if not isinstance(grant, dict):
            raise ClassesValidationError("Each feature_grant must be an object.")
        try:
            level = int(grant.get("level") or 0)
        except (TypeError, ValueError):
            raise ClassesValidationError("feature_grant level must be an integer.") from None
        if not (1 <= level <= 20):
            raise ClassesValidationError("feature_grant level must be between 1 and 20.")
        name = str(grant.get("name") or "").strip()[:_MAX_FEATURE_NAME]
        if not name:
            raise ClassesValidationError("Each feature_grant requires a name.")
        entry: dict[str, Any] = {
            "level": level,
            "name": name,
            "trait_keys": _clean_trait_keys(grant.get("trait_keys") or []),
        }
        summary = str(grant.get("summary") or "").strip()[:_MAX_FEATURE_DESC]
        if summary:
            entry["summary"] = summary
        clean.append(entry)
    return clean


def _normalize_subclass(raw: dict[str, Any]) -> dict[str, Any]:
    source = str(raw.get("source") or "custom")
    base = _default_subclass_entry(raw, source=source)
    base.update(deepcopy(raw))
    base["key"] = str(raw.get("key") or base["key"])
    base["name"] = str(raw.get("name") or base["name"]).strip()[:_MAX_SUBCLASS_NAME]
    try:
        pick_level = int(base.get("pick_level") or 3)
    except (TypeError, ValueError):
        pick_level = 3
    if not (1 <= pick_level <= 20):
        pick_level = 3
    base["pick_level"] = pick_level
    base["tagline"] = str(base.get("tagline") or "")[:_MAX_SUBCLASS_TAGLINE]
    base["summary"] = str(base.get("summary") or "")[:_MAX_SUMMARY_LEN]
    base["feature_grants"] = _clean_feature_grants(base.get("feature_grants") or [])
    base["is_hidden"] = bool(base.get("is_hidden"))
    base["secret"] = bool(base.get("secret"))
    base["visible_to_owner"] = bool(base.get("visible_to_owner", True))
    base["srd_seed_version"] = int(base.get("srd_seed_version") or 0)
    base["gm_edited"] = bool(base.get("gm_edited"))
    base["notes"] = str(base.get("notes") or "")[:_MAX_NOTES_LEN]
    return base


def _clean_subclasses(raw: Any) -> list[dict[str, Any]]:
    if raw is None or raw == "":
        return []
    if not isinstance(raw, list) or len(raw) > _MAX_SUBCLASSES_PER_CLASS:
        raise ClassesValidationError(
            f"subclasses must be a list of at most {_MAX_SUBCLASSES_PER_CLASS} entries."
        )
    clean: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in raw:
        if not isinstance(row, dict):
            raise ClassesValidationError("Each subclass must be an object.")
        normalized = _normalize_subclass(row)
        sub_key = str(normalized.get("key") or "")
        if sub_key in seen:
            raise ClassesValidationError(f"Duplicate subclass key: {sub_key}.")
        seen.add(sub_key)
        clean.append(normalized)
    return clean


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
        "pact_magic": _clean_pact_magic(raw.get("pact_magic")),
        "resources": _clean_slot_map(
            raw.get("resources") or {}, label="resources", max_keys=_MAX_RESOURCE_KEYS, max_key_len=24
        ),
        "cantrips_known": _clean_optional_count(
            raw.get("cantrips_known"), label="cantrips_known", max_value=20
        ),
        "spells_known": _clean_optional_count(
            raw.get("spells_known"), label="spells_known", max_value=50
        ),
        "spells_prepared": _clean_optional_count(
            raw.get("spells_prepared"), label="spells_prepared", max_value=50
        ),
        "invocations_known": _clean_optional_count(
            raw.get("invocations_known"), label="invocations_known", max_value=20
        ),
        "player_choices": _clean_player_choices(raw.get("player_choices") or []),
        "trait_pools": _clean_trait_pools(raw.get("trait_pools") or []),
        "progression_stats": _clean_progression_stats(raw.get("progression_stats") or {}),
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
        "spellcasting": _clean_spellcasting(raw.get("spellcasting") or {}),
        "progression_columns": _clean_progression_columns(raw.get("progression_columns") or []),
        "level_progression": _clean_level_progression(raw.get("level_progression") or []),
        "progression_customized": True,
        "is_hidden": bool(raw.get("is_hidden")),
        "secret": bool(raw.get("secret")),
        "visible_to_owner": bool(raw.get("visible_to_owner", True)),
        "notes": str(raw.get("notes") or "").strip()[:_MAX_NOTES_LEN],
        "subclasses": _clean_subclasses(raw.get("subclasses") or []),
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
            _ensure_subclass_player_choice(entry)
            _sync_progression_features_from_traits(
                campaign_id,
                entry.get("level_progression") or [],
            )
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
    _sync_progression_features_from_traits(
        campaign_id,
        entry.get("level_progression") or [],
    )
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
    subclass_key: Optional[str] = None,
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
    spellcasting = entry.get("spellcasting") or {}
    subclass_block: dict[str, Any] | None = None
    sub_key = str(subclass_key or "").strip().lower()
    if sub_key:
        subclass_row = find_subclass_on_class(entry, sub_key)
        if subclass_row and _player_may_view_subclass(
            subclass_row,
            owner_subclass_key=sub_key,
        ):
            grants = [
                deepcopy(grant)
                for grant in (subclass_row.get("feature_grants") or [])
                if isinstance(grant, dict)
                and int(grant.get("level") or 0) <= level_int
            ]
            subclass_block = {
                "key": subclass_row.get("key"),
                "name": subclass_row.get("name"),
                "tagline": subclass_row.get("tagline") or "",
                "summary": subclass_row.get("summary") or "",
                "feature_grants": grants,
            }
    return {
        "available": True,
        "hidden_message": None,
        "key": entry.get("key"),
        "name": entry.get("name"),
        "summary": entry.get("summary") or "",
        "hit_die": entry.get("hit_die"),
        "save_proficiencies": list(entry.get("save_proficiencies") or []),
        "source": entry.get("source"),
        "spellcasting": deepcopy(spellcasting),
        "level": level_int,
        "current_level_row": current_row,
        "next_level_row": next_row,
        "resolved_spell_slots": resolve_spell_slots_from_row(current_row or {}),
        "next_resolved_spell_slots": resolve_spell_slots_from_row(next_row or {}),
        "subclass": subclass_block,
        "available_subclasses": list_visible_subclasses_for_class(
            entry,
            owner_subclass_key=sub_key or None,
        ),
    }


def _player_may_view_subclass(
    subclass_entry: dict[str, Any],
    *,
    owner_subclass_key: Optional[str],
) -> bool:
    if not subclass_entry.get("is_hidden") and not subclass_entry.get("secret"):
        return True
    owner_key = str(owner_subclass_key or "").strip().lower()
    entry_key = str(subclass_entry.get("key") or "").strip().lower()
    if owner_key and owner_key == entry_key and subclass_entry.get("visible_to_owner"):
        return True
    return False


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
