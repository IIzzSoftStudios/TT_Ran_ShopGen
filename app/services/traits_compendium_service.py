"""Campaign-scoped trait compendium (settings JSON).

Mechanical traits (speed, resistances, senses) for species, monsters, and classes.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from app.extensions import db
from app.models import CampaignWorldConfig
from app.services.character_creation.dnd5e_traits import CORE_TRAITS, CORE_TRAITS_BY_KEY

_CATEGORIES = frozenset(
    {
        "sense",
        "movement",
        "defense",
        "save",
        "attack",
        "resource",
        "condition",
        "other",
    }
)
_DAMAGE_TYPES = frozenset(
    {
        "acid", "bludgeoning", "cold", "fire", "force", "lightning", "necrotic",
        "piercing", "poison", "psychic", "radiant", "slashing", "thunder",
    }
)
_CONDITIONS = frozenset(
    {
        "blinded", "charmed", "deafened", "frightened", "grappled", "incapacitated",
        "invisible", "paralyzed", "petrified", "poisoned", "prone", "restrained",
        "stunned", "unconscious",
    }
)
_MAX_NAME_LEN = 80
_MAX_NOTES_LEN = 500
_MAX_SUMMARY_LEN = 500
_MAX_RULES_TEXT_LEN = 4000
_MAX_TRAIT_KEYS = 24
_MAX_PREREQ_TRAIT_KEYS = 12
_MAX_PREREQ_SPELL_KEYS = 8
_MAX_ENTRY_BYTES = 16384
_ABILITIES = frozenset({"str", "dex", "con", "int", "wis", "cha"})
_SLUG_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
_SPELL_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")


class TraitsValidationError(ValueError):
    """Raised when trait compendium input is invalid."""


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(name or "").strip().lower()).strip("-")
    return slug[:80] or "trait"


def _config_for_campaign(campaign_id: int, *, lock: bool = False) -> CampaignWorldConfig:
    query = CampaignWorldConfig.query.filter_by(campaign_id=campaign_id)
    if lock:
        query = query.with_for_update()
    cfg = query.first()
    if cfg is None:
        cfg = CampaignWorldConfig(campaign_id=campaign_id, settings_json={}, schema_version=1)
        db.session.add(cfg)
        db.session.flush()
    if not isinstance(cfg.settings_json, dict):
        cfg.settings_json = {}
    return cfg


def _default_trait_entry(raw: dict[str, Any], *, source: str = "custom") -> dict[str, Any]:
    return {
        "key": str(raw.get("key") or _slug(raw.get("name") or "trait")),
        "name": str(raw.get("name") or "Trait")[: _MAX_NAME_LEN],
        "source": source,
        "origin_template_key": raw.get("origin_template_key"),
        "category": str(raw.get("category") or "other"),
        "effects": dict(raw.get("effects") or {}),
        "prerequisites": dict(raw.get("prerequisites") or {}),
        "tags": list(raw.get("tags") or []),
        "stacking": str(raw.get("stacking") or "max"),
        "notes": str(raw.get("notes") or "")[:_MAX_NOTES_LEN],
        "summary": str(raw.get("summary") or "")[:_MAX_SUMMARY_LEN],
        "rules_text": str(raw.get("rules_text") or "")[:_MAX_RULES_TEXT_LEN],
        "srd_reference": str(raw.get("srd_reference") or "")[:40],
        "content_source": str(raw.get("content_source") or "")[:40],
        "gm_edited": bool(raw.get("gm_edited")),
        "srd_seed_version": int(raw.get("srd_seed_version") or 0),
    }


def _clean_string_list(raw: Any, *, allowed: frozenset[str], label: str, max_items: int) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        items = [part.strip().lower() for part in raw.split(",") if part.strip()]
    elif isinstance(raw, list):
        items = [str(part or "").strip().lower() for part in raw if str(part or "").strip()]
    else:
        raise TraitsValidationError(f"{label} must be a list or comma-separated string.")
    clean = []
    for item in items[:max_items]:
        if item not in allowed:
            raise TraitsValidationError(f"Invalid {label} value: {item!r}.")
        if item not in clean:
            clean.append(item)
    return clean


def clean_trait_effects(raw: Any) -> dict[str, Any]:
    """Public wrapper for validating sparse combat effect objects."""
    return _clean_effects(raw)


def _clean_effects(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise TraitsValidationError("effects must be an object.")
    effects: dict[str, Any] = {}
    if "speed_ft" in raw and raw["speed_ft"] not in (None, ""):
        try:
            speed = int(raw["speed_ft"])
        except (TypeError, ValueError):
            raise TraitsValidationError("effects.speed_ft must be an integer.")
        if not (0 <= speed <= 120):
            raise TraitsValidationError("effects.speed_ft must be between 0 and 120.")
        effects["speed_ft"] = speed
    if "size" in raw and str(raw["size"] or "").strip():
        size = str(raw["size"]).strip().lower()
        if size not in ("tiny", "small", "medium", "large", "huge", "gargantuan"):
            raise TraitsValidationError("effects.size is invalid.")
        effects["size"] = size
    if "darkvision_ft" in raw and raw["darkvision_ft"] not in (None, ""):
        try:
            dv = int(raw["darkvision_ft"])
        except (TypeError, ValueError):
            raise TraitsValidationError("effects.darkvision_ft must be an integer.")
        if not (0 <= dv <= 240):
            raise TraitsValidationError("effects.darkvision_ft must be between 0 and 240.")
        effects["darkvision_ft"] = dv
    for list_key, allowed in (
        ("damage_resistances", _DAMAGE_TYPES),
        ("damage_immunities", _DAMAGE_TYPES),
        ("damage_vulnerabilities", _DAMAGE_TYPES),
        ("save_advantage_vs_conditions", _CONDITIONS),
    ):
        if list_key in raw:
            effects[list_key] = _clean_string_list(raw[list_key], allowed=allowed, label=list_key, max_items=12)
    if "save_advantage_vs_magic" in raw:
        effects["save_advantage_vs_magic"] = _clean_string_list(
            raw["save_advantage_vs_magic"],
            allowed=frozenset({"str", "dex", "con", "int", "wis", "cha"}),
            label="save_advantage_vs_magic",
            max_items=6,
        )
    if "condition_immunities" in raw:
        effects["condition_immunities"] = _clean_string_list(
            raw["condition_immunities"],
            allowed=_CONDITIONS,
            label="condition_immunities",
            max_items=12,
        )
    if "save_bonuses" in raw and isinstance(raw["save_bonuses"], dict):
        bonuses = {}
        for ability, value in raw["save_bonuses"].items():
            ab = str(ability or "").strip().lower()
            if ab not in {"str", "dex", "con", "int", "wis", "cha"}:
                continue
            try:
                bonuses[ab] = int(value)
            except (TypeError, ValueError):
                raise TraitsValidationError(f"save_bonuses.{ab} must be an integer.")
        if bonuses:
            effects["save_bonuses"] = bonuses
    for flag in ("lucky", "savage_attacks", "relentless_endurance", "relentless_rage"):
        if flag in raw:
            effects[flag] = bool(raw[flag])
    if "speed_bonus_ft" in raw and raw["speed_bonus_ft"] not in (None, ""):
        try:
            bonus = int(raw["speed_bonus_ft"])
        except (TypeError, ValueError):
            raise TraitsValidationError("effects.speed_bonus_ft must be an integer.")
        if not (0 <= bonus <= 60):
            raise TraitsValidationError("effects.speed_bonus_ft must be between 0 and 60.")
        effects["speed_bonus_ft"] = bonus
    if "unarmored_ac_add_ability" in raw and str(raw["unarmored_ac_add_ability"] or "").strip():
        ability = str(raw["unarmored_ac_add_ability"]).strip().lower()
        if ability not in {"str", "dex", "con", "int", "wis", "cha"}:
            raise TraitsValidationError("effects.unarmored_ac_add_ability is invalid.")
        effects["unarmored_ac_add_ability"] = ability
    if "unarmored_defense" in raw:
        effects["unarmored_defense"] = bool(raw["unarmored_defense"])
    if "unarmored_defense_allows_shield" in raw:
        effects["unarmored_defense_allows_shield"] = bool(raw["unarmored_defense_allows_shield"])
    if "extra_attacks_per_action" in raw and raw["extra_attacks_per_action"] not in (None, ""):
        try:
            count = int(raw["extra_attacks_per_action"])
        except (TypeError, ValueError):
            raise TraitsValidationError("effects.extra_attacks_per_action must be an integer.")
        if not (2 <= count <= 4):
            raise TraitsValidationError("effects.extra_attacks_per_action must be between 2 and 4.")
        effects["extra_attacks_per_action"] = count
    if "action_surge" in raw:
        effects["action_surge"] = bool(raw["action_surge"])
    if "action_surge_additional_actions" in raw and raw["action_surge_additional_actions"] not in (
        None,
        "",
    ):
        try:
            count = int(raw["action_surge_additional_actions"])
        except (TypeError, ValueError):
            raise TraitsValidationError("effects.action_surge_additional_actions must be an integer.")
        if not (1 <= count <= 2):
            raise TraitsValidationError("effects.action_surge_additional_actions must be 1 or 2.")
        effects["action_surge_additional_actions"] = count
    if "reach_cells" in raw and raw["reach_cells"] not in (None, ""):
        try:
            reach = int(raw["reach_cells"])
        except (TypeError, ValueError):
            raise TraitsValidationError("effects.reach_cells must be an integer.")
        if not (1 <= reach <= 4):
            raise TraitsValidationError("effects.reach_cells must be between 1 and 4.")
        effects["reach_cells"] = reach
    return effects


def _clean_slug_keys(raw: Any, *, label: str, max_items: int, pattern: re.Pattern[str] | None = None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        items = [part.strip().lower() for part in raw.split(",") if part.strip()]
    elif isinstance(raw, list):
        items = [str(part or "").strip().lower() for part in raw if str(part or "").strip()]
    else:
        raise TraitsValidationError(f"{label} must be a list or comma-separated string.")
    matcher = pattern or _SLUG_KEY_RE
    clean: list[str] = []
    for item in items[:max_items]:
        if not matcher.match(item):
            raise TraitsValidationError(f"Invalid {label} value: {item!r}.")
        if item not in clean:
            clean.append(item)
    return clean


def _clean_ability_score_mins(raw: Any) -> dict[str, int]:
    if raw in (None, "", {}):
        return {}
    if isinstance(raw, str):
        parsed: dict[str, Any] = {}
        for chunk in raw.split(","):
            part = chunk.strip()
            if not part:
                continue
            eq = part.index("=") if "=" in part else -1
            if eq <= 0:
                raise TraitsValidationError("ability_scores must use ability=score pairs.")
            parsed[part[:eq].strip()] = part[eq + 1 :].strip()
        raw = parsed
    if not isinstance(raw, dict):
        raise TraitsValidationError("ability_scores must be an object or comma-separated pairs.")
    clean: dict[str, int] = {}
    for ability, value in raw.items():
        ab = str(ability or "").strip().lower()
        if ab not in _ABILITIES:
            raise TraitsValidationError(f"Invalid ability_scores ability: {ability!r}.")
        try:
            score = int(value)
        except (TypeError, ValueError):
            raise TraitsValidationError(f"ability_scores.{ab} must be an integer.") from None
        if not (1 <= score <= 30):
            raise TraitsValidationError(f"ability_scores.{ab} must be between 1 and 30.")
        clean[ab] = score
    return clean


def _clean_prerequisites(raw: Any) -> dict[str, Any]:
    if raw in (None, "", {}):
        return {}
    if not isinstance(raw, dict):
        raise TraitsValidationError("prerequisites must be an object.")
    out: dict[str, Any] = {}
    for level_key in ("min_level", "max_level"):
        if level_key not in raw or raw[level_key] in (None, ""):
            continue
        try:
            level = int(raw[level_key])
        except (TypeError, ValueError):
            raise TraitsValidationError(f"prerequisites.{level_key} must be an integer.") from None
        if not (1 <= level <= 20):
            raise TraitsValidationError(f"prerequisites.{level_key} must be between 1 and 20.")
        out[level_key] = level
    if out.get("min_level") and out.get("max_level") and out["min_level"] > out["max_level"]:
        raise TraitsValidationError("prerequisites.min_level cannot exceed max_level.")
    if "class_keys" in raw:
        out["class_keys"] = _clean_slug_keys(raw["class_keys"], label="class_keys", max_items=8)
    if "subclass_keys" in raw:
        out["subclass_keys"] = _clean_slug_keys(
            raw["subclass_keys"], label="subclass_keys", max_items=8
        )
    if "species_keys" in raw:
        out["species_keys"] = _clean_slug_keys(raw["species_keys"], label="species_keys", max_items=8)
    if "trait_keys" in raw:
        out["trait_keys"] = _clean_slug_keys(
            raw["trait_keys"], label="prerequisites.trait_keys", max_items=_MAX_PREREQ_TRAIT_KEYS
        )
    if "ability_scores" in raw:
        scores = _clean_ability_score_mins(raw["ability_scores"])
        if scores:
            out["ability_scores"] = scores
    if "spell_keys" in raw:
        out["spell_keys"] = _clean_slug_keys(
            raw["spell_keys"],
            label="prerequisites.spell_keys",
            max_items=_MAX_PREREQ_SPELL_KEYS,
            pattern=_SPELL_KEY_RE,
        )
    return out


def _prerequisites_met(prerequisites: dict[str, Any] | None, context: dict[str, Any]) -> bool:
    prereqs = prerequisites or {}
    if not prereqs:
        return True
    try:
        level = max(1, int(context.get("level") or 1))
    except (TypeError, ValueError):
        level = 1
    min_level = prereqs.get("min_level")
    if min_level is not None and level < int(min_level):
        return False
    max_level = prereqs.get("max_level")
    if max_level is not None and level > int(max_level):
        return False
    class_key = str(context.get("class_key") or "").strip().lower()
    required_classes = prereqs.get("class_keys") or []
    if required_classes and class_key not in required_classes:
        return False
    subclass_key = str(context.get("subclass_key") or "").strip().lower()
    required_subclasses = prereqs.get("subclass_keys") or []
    if required_subclasses and subclass_key not in required_subclasses:
        return False
    species_key = str(context.get("species_key") or "").strip().lower()
    required_species = prereqs.get("species_keys") or []
    if required_species and species_key not in required_species:
        return False
    granted = {
        str(key).strip().lower()
        for key in (context.get("granted_trait_keys") or [])
        if str(key).strip()
    }
    for required in prereqs.get("trait_keys") or []:
        if required not in granted:
            return False
    spell_keys = {
        str(key).strip().lower()
        for key in (context.get("spell_keys") or [])
        if str(key).strip()
    }
    for required_spell in prereqs.get("spell_keys") or []:
        if required_spell not in spell_keys:
            return False
    abilities = context.get("abilities") if isinstance(context.get("abilities"), dict) else {}
    for ability, minimum in (prereqs.get("ability_scores") or {}).items():
        try:
            score = int(abilities.get(ability, 0))
        except (TypeError, ValueError):
            score = 0
        if score < int(minimum):
            return False
    return True


def _normalize_trait(raw: dict[str, Any]) -> dict[str, Any]:
    entry = _default_trait_entry(raw, source=str(raw.get("source") or "custom"))
    category = str(entry["category"] or "other").lower()
    if category == "class_feature":
        category = "other"
    if category not in _CATEGORIES:
        category = "other"
    entry["category"] = category
    entry["effects"] = _clean_effects(entry.get("effects") or {})
    entry["prerequisites"] = _clean_prerequisites(entry.get("prerequisites") or {})
    entry["tags"] = [
        str(tag).strip().lower()[:30]
        for tag in (entry.get("tags") or [])
        if str(tag).strip()
    ][:8]
    stacking = str(entry.get("stacking") or "max").lower()
    if stacking not in ("max", "union", "replace"):
        stacking = "max"
    entry["stacking"] = stacking
    if len(json.dumps(entry, separators=(",", ":"))) > _MAX_ENTRY_BYTES:
        raise TraitsValidationError("Trait entry exceeds maximum serialized size.")
    return entry


def _trait_from_core(raw: dict[str, Any]) -> dict[str, Any]:
    entry = _normalize_trait({**raw, "source": "base", "gm_edited": False})
    entry["origin_template_key"] = str(raw.get("key") or entry["key"])
    return entry


def _load_srd_class_traits() -> tuple[dict[str, Any], ...]:
    from app.services.character_creation.dnd5e_srd_class_traits import (
        CURRENT_SRD_CLASS_TRAITS_SEED_VERSION,
        SRD_CLASS_TRAITS,
        _refresh_srd_class_traits_cache,
    )

    if not SRD_CLASS_TRAITS:
        import app.services.character_creation.dnd5e_srd_class_progression  # noqa: F401

        _refresh_srd_class_traits_cache()
    from app.services.character_creation.dnd5e_srd_class_traits import (
        SRD_CLASS_TRAITS as loaded_traits,
    )

    return loaded_traits, CURRENT_SRD_CLASS_TRAITS_SEED_VERSION


def _load_srd_subclass_traits() -> tuple[dict[str, Any], ...]:
    from app.services.character_creation.dnd5e_srd_subclass_traits import (
        CURRENT_SRD_SUBCLASSES_SEED_VERSION,
        SRD_SUBCLASS_TRAITS,
        _refresh_srd_subclass_traits_cache,
    )

    if not SRD_SUBCLASS_TRAITS:
        _refresh_srd_subclass_traits_cache()
    from app.services.character_creation.dnd5e_srd_subclass_traits import (
        SRD_SUBCLASS_TRAITS as loaded_traits,
    )

    return loaded_traits, CURRENT_SRD_SUBCLASSES_SEED_VERSION


def _ensure_compendium(settings: dict[str, Any]) -> list[dict[str, Any]]:
    compendium = settings.get("traits_compendium")
    if not isinstance(compendium, list):
        compendium = []
    by_key: dict[str, dict[str, Any]] = {}
    for raw in compendium:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        try:
            entry = _normalize_trait(raw)
        except TraitsValidationError:
            continue
        by_key[entry["key"]] = entry
    for core in CORE_TRAITS:
        key = str(core["key"])
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = _trait_from_core(core)
        elif not existing.get("gm_edited"):
            merged = _trait_from_core(core)
            merged["notes"] = existing.get("notes") or ""
            by_key[key] = merged
    srd_class_traits, srd_class_traits_version = _load_srd_class_traits()
    for srd_trait in srd_class_traits:
        key = str(srd_trait["key"])
        existing = by_key.get(key)
        seed_version = int(srd_trait.get("srd_seed_version") or srd_class_traits_version)
        if existing is None:
            by_key[key] = _trait_from_core(srd_trait)
            by_key[key]["srd_seed_version"] = seed_version
        elif not existing.get("gm_edited"):
            current_version = int(existing.get("srd_seed_version") or 0)
            if current_version < seed_version:
                merged = _trait_from_core(srd_trait)
                merged["notes"] = existing.get("notes") or ""
                merged["srd_seed_version"] = seed_version
                by_key[key] = merged
    srd_subclass_traits, srd_subclass_traits_version = _load_srd_subclass_traits()
    for srd_trait in srd_subclass_traits:
        key = str(srd_trait["key"])
        existing = by_key.get(key)
        seed_version = int(srd_trait.get("srd_seed_version") or srd_subclass_traits_version)
        if existing is None:
            by_key[key] = _trait_from_core(srd_trait)
            by_key[key]["srd_seed_version"] = seed_version
        elif not existing.get("gm_edited"):
            current_version = int(existing.get("srd_seed_version") or 0)
            if current_version < seed_version:
                merged = _trait_from_core(srd_trait)
                merged["notes"] = existing.get("notes") or ""
                merged["srd_seed_version"] = seed_version
                by_key[key] = merged
    entries = sorted(by_key.values(), key=lambda row: (row.get("category", ""), row["name"].lower()))
    settings["traits_compendium"] = entries
    return entries


def ensure_traits_compendium(campaign_id: int) -> list[dict[str, Any]]:
    cfg = _config_for_campaign(campaign_id)
    settings = cfg.settings_json
    entries = _ensure_compendium(settings)
    cfg.settings_json = settings
    flag_modified(cfg, "settings_json")
    db.session.flush()
    return deepcopy(entries)


def list_traits(campaign_id: int) -> list[dict[str, Any]]:
    return ensure_traits_compendium(campaign_id)


def get_trait_entry(campaign_id: int, key: str) -> dict[str, Any] | None:
    needle = str(key or "").strip().lower()
    for entry in ensure_traits_compendium(campaign_id):
        if str(entry.get("key") or "").lower() == needle:
            return deepcopy(entry)
    return None


def _clean_trait_keys(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        keys = [part.strip().lower() for part in raw.split(",") if part.strip()]
    elif isinstance(raw, list):
        keys = [str(part or "").strip().lower() for part in raw if str(part or "").strip()]
    else:
        raise TraitsValidationError("trait_keys must be a list or comma-separated string.")
    if len(keys) > _MAX_TRAIT_KEYS:
        raise TraitsValidationError(f"At most {_MAX_TRAIT_KEYS} trait keys allowed.")
    return keys


def _clean_trait_patch(raw: dict[str, Any]) -> dict[str, Any]:
    name = str(raw.get("name") or "").strip()
    if not name or len(name) > _MAX_NAME_LEN:
        raise TraitsValidationError("Trait name must be 1-80 characters.")
    return {
        "name": name,
        "category": str(raw.get("category") or "other").lower(),
        "effects": _clean_effects(raw.get("effects") or {}),
        "prerequisites": _clean_prerequisites(raw.get("prerequisites") or {}),
        "tags": [
            str(tag).strip().lower()
            for tag in (raw.get("tags") or [])
            if str(tag).strip()
        ][:8],
        "stacking": str(raw.get("stacking") or "max").lower(),
        "notes": str(raw.get("notes") or "").strip()[:_MAX_NOTES_LEN],
        "summary": str(raw.get("summary") or "").strip()[:_MAX_SUMMARY_LEN],
        "rules_text": str(raw.get("rules_text") or "").strip()[:_MAX_RULES_TEXT_LEN],
        "gm_edited": True,
    }


def create_trait(campaign_id: int, raw: dict[str, Any]) -> dict[str, Any]:
    cfg = _config_for_campaign(campaign_id, lock=True)
    settings = cfg.settings_json
    entries = _ensure_compendium(settings)
    clean = _clean_trait_patch(raw)
    existing_keys = {entry["key"] for entry in entries}
    base_key = _slug(clean["name"])
    key = base_key
    suffix = 2
    while key in existing_keys:
        key = f"{base_key}-{suffix}"
        suffix += 1
    entry = _normalize_trait({"key": key, "source": "custom", **clean})
    entries.append(entry)
    settings["traits_compendium"] = sorted(
        entries, key=lambda row: (row.get("category", ""), row["name"].lower())
    )
    cfg.settings_json = settings
    flag_modified(cfg, "settings_json")
    db.session.flush()
    return deepcopy(entry)


def update_trait(campaign_id: int, key: str, raw: dict[str, Any]) -> dict[str, Any]:
    cfg = _config_for_campaign(campaign_id, lock=True)
    settings = cfg.settings_json
    entries = _ensure_compendium(settings)
    clean = _clean_trait_patch(raw)
    for entry in entries:
        if entry.get("key") == key:
            entry.update(clean)
            merged = _normalize_trait(entry)
            entry.clear()
            entry.update(merged)
            cfg.settings_json = settings
            flag_modified(cfg, "settings_json")
            db.session.flush()
            return deepcopy(entry)
    raise TraitsValidationError("Trait entry not found.")


def resolve_trait_effects(
    campaign_id: int,
    trait_keys: list[str] | None,
    *,
    context: dict[str, Any] | None = None,
    fallback_core: bool = True,
) -> dict[str, Any]:
    """Merge trait ``effects`` for keys whose prerequisites are met in *context*."""
    from app.services.combat.dnd5e_combat_profile import merge_combat_effects

    keys = _clean_trait_keys(trait_keys or [])
    if not keys:
        return {}
    ctx = dict(context or {})
    granted = {
        str(key).strip().lower()
        for key in (ctx.get("granted_trait_keys") or [])
        if str(key).strip()
    }
    catalog = {entry["key"]: entry for entry in ensure_traits_compendium(campaign_id)}
    layers: list[dict[str, Any]] = []
    pending = list(keys)
    for _ in range(len(pending) + _MAX_TRAIT_KEYS):
        if not pending:
            break
        progress = False
        next_pending: list[str] = []
        for key in pending:
            entry = catalog.get(key)
            if entry is None and fallback_core and key in CORE_TRAITS_BY_KEY:
                entry = CORE_TRAITS_BY_KEY[key]
            if entry is None:
                continue
            check_ctx = {**ctx, "granted_trait_keys": sorted(granted)}
            if not _prerequisites_met(entry.get("prerequisites"), check_ctx):
                next_pending.append(key)
                continue
            granted.add(key)
            effects = entry.get("effects") if isinstance(entry.get("effects"), dict) else {}
            if effects:
                layers.append(dict(effects))
            progress = True
        pending = next_pending
        if not progress:
            break
    return merge_combat_effects({}, *layers)


def list_traits_by_tag(campaign_id: int, tag: str) -> list[dict[str, Any]]:
    """Return compendium traits matching a tag (e.g. ``warlock-invocation``)."""
    needle = str(tag or "").strip().lower()
    if not needle:
        return []
    return [
        deepcopy(entry)
        for entry in ensure_traits_compendium(campaign_id)
        if needle in [str(t).strip().lower() for t in (entry.get("tags") or [])]
    ]


def trait_prerequisite_context_from_sheet(sheet: dict[str, Any]) -> dict[str, Any]:
    """Build prerequisite evaluation context from a character sheet."""
    creation = sheet.get("creation") if isinstance(sheet.get("creation"), dict) else {}
    spells_state = sheet.get("spells") if isinstance(sheet.get("spells"), dict) else {}
    spell_keys: list[str] = []
    for bucket in ("cantrips", "known", "prepared"):
        for raw in spells_state.get(bucket) or []:
            key = str(raw or "").strip().lower()
            if key:
                spell_keys.append(key)
    selections = (
        sheet.get("class_trait_selections")
        if isinstance(sheet.get("class_trait_selections"), dict)
        else {}
    )
    granted: set[str] = set()
    for level_keys in selections.values():
        if isinstance(level_keys, list):
            for key in level_keys:
                clean = str(key or "").strip().lower()
                if clean:
                    granted.add(clean)
    for level in range(1, 21):
        for key in selections.get(str(level)) or selections.get(level) or []:
            clean = str(key or "").strip().lower()
            if clean:
                granted.add(clean)
    try:
        level = max(1, min(20, int(sheet.get("level") or 1)))
    except (TypeError, ValueError):
        level = 1
    return {
        "level": level,
        "class_key": str(creation.get("class_key") or "").strip().lower(),
        "subclass_key": str(creation.get("subclass_key") or "").strip().lower(),
        "species_key": str(creation.get("species_key") or "").strip().lower(),
        "abilities": dict(sheet.get("abilities") or {}),
        "spell_keys": spell_keys,
        "granted_trait_keys": sorted(granted),
    }
