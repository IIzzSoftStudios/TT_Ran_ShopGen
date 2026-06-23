"""SRD-safe D&D 5e character creation catalog and campaign merge helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Optional

from app.services.character_creation.dnd5e_species import ABILITIES, CORE_SPECIES

# Mechanical shells only — original/minimal descriptions, no copied book text.
# Full SRD 5.1 ability modifiers and traits live in dnd5e_species.py.

CORE_CLASSES: tuple[dict[str, Any], ...] = (
    {
        "key": "barbarian",
        "name": "Barbarian",
        "summary": "Fierce warrior fueled by primal fury.",
        "save_proficiencies": ["str", "con"],
        "skill_choices": {
            "count": 2,
            "options": [
                "animal_handling",
                "athletics",
                "intimidation",
                "nature",
                "perception",
                "survival",
            ],
        },
        "hit_die": 12,
    },
    {
        "key": "bard",
        "name": "Bard",
        "summary": "Inspiring performer weaving magic and lore.",
        "save_proficiencies": ["dex", "cha"],
        "skill_choices": {"count": 3, "options": "any"},
        "hit_die": 8,
    },
    {
        "key": "cleric",
        "name": "Cleric",
        "summary": "Divine champion channeling sacred power.",
        "save_proficiencies": ["wis", "cha"],
        "skill_choices": {
            "count": 2,
            "options": ["history", "insight", "medicine", "persuasion", "religion"],
        },
        "hit_die": 8,
    },
    {
        "key": "druid",
        "name": "Druid",
        "summary": "Nature priest drawing power from the wild.",
        "save_proficiencies": ["int", "wis"],
        "skill_choices": {
            "count": 2,
            "options": [
                "arcana",
                "animal_handling",
                "insight",
                "medicine",
                "nature",
                "perception",
                "religion",
                "survival",
            ],
        },
        "hit_die": 8,
    },
    {
        "key": "fighter",
        "name": "Fighter",
        "summary": "Master of weapons and battlefield tactics.",
        "save_proficiencies": ["str", "con"],
        "skill_choices": {
            "count": 2,
            "options": [
                "acrobatics",
                "animal_handling",
                "athletics",
                "history",
                "insight",
                "intimidation",
                "perception",
                "survival",
            ],
        },
        "hit_die": 10,
    },
    {
        "key": "monk",
        "name": "Monk",
        "summary": "Disciplined martial artist harnessing inner energy.",
        "save_proficiencies": ["str", "dex"],
        "skill_choices": {
            "count": 2,
            "options": [
                "acrobatics",
                "athletics",
                "history",
                "insight",
                "religion",
                "stealth",
            ],
        },
        "hit_die": 8,
    },
    {
        "key": "paladin",
        "name": "Paladin",
        "summary": "Holy knight bound by sacred oath.",
        "save_proficiencies": ["wis", "cha"],
        "skill_choices": {
            "count": 2,
            "options": [
                "athletics",
                "insight",
                "intimidation",
                "medicine",
                "persuasion",
                "religion",
            ],
        },
        "hit_die": 10,
    },
    {
        "key": "ranger",
        "name": "Ranger",
        "summary": "Wilderness hunter guarding the borderlands.",
        "save_proficiencies": ["str", "dex"],
        "skill_choices": {
            "count": 3,
            "options": [
                "animal_handling",
                "athletics",
                "insight",
                "investigation",
                "nature",
                "perception",
                "stealth",
                "survival",
            ],
        },
        "hit_die": 10,
    },
    {
        "key": "rogue",
        "name": "Rogue",
        "summary": "Skilled infiltrator relying on precision.",
        "save_proficiencies": ["dex", "int"],
        "skill_choices": {
            "count": 4,
            "options": [
                "acrobatics",
                "athletics",
                "deception",
                "insight",
                "intimidation",
                "investigation",
                "perception",
                "performance",
                "persuasion",
                "sleight_of_hand",
                "stealth",
            ],
        },
        "hit_die": 8,
    },
    {
        "key": "sorcerer",
        "name": "Sorcerer",
        "summary": "Innate spellcaster shaped by magical bloodline.",
        "save_proficiencies": ["con", "cha"],
        "skill_choices": {
            "count": 2,
            "options": [
                "arcana",
                "deception",
                "insight",
                "intimidation",
                "persuasion",
                "religion",
            ],
        },
        "hit_die": 6,
    },
    {
        "key": "warlock",
        "name": "Warlock",
        "summary": "Arcane pact-maker drawing otherworldly power.",
        "save_proficiencies": ["wis", "cha"],
        "skill_choices": {
            "count": 2,
            "options": [
                "arcana",
                "deception",
                "history",
                "intimidation",
                "investigation",
                "nature",
                "religion",
            ],
        },
        "hit_die": 8,
    },
    {
        "key": "wizard",
        "name": "Wizard",
        "summary": "Scholarly mage mastering arcane formulas.",
        "save_proficiencies": ["int", "wis"],
        "skill_choices": {
            "count": 2,
            "options": [
                "arcana",
                "history",
                "insight",
                "investigation",
                "medicine",
                "religion",
            ],
        },
        "hit_die": 6,
    },
)

CORE_BACKGROUNDS: tuple[dict[str, Any], ...] = (
    {
        "key": "acolyte",
        "name": "Acolyte",
        "summary": "Raised in a temple or faith community.",
        "skill_proficiencies": ["insight", "religion"],
    },
    {
        "key": "charlatan",
        "name": "Charlatan",
        "summary": "Skilled at disguise and misdirection.",
        "skill_proficiencies": ["deception", "sleight_of_hand"],
    },
    {
        "key": "criminal",
        "name": "Criminal",
        "summary": "Experienced in illicit trade and stealth.",
        "skill_proficiencies": ["deception", "stealth"],
    },
    {
        "key": "entertainer",
        "name": "Entertainer",
        "summary": "Performer who captivates crowds.",
        "skill_proficiencies": ["acrobatics", "performance"],
    },
    {
        "key": "folk-hero",
        "name": "Folk Hero",
        "summary": "Champion of common people.",
        "skill_proficiencies": ["animal_handling", "survival"],
    },
    {
        "key": "guild-artisan",
        "name": "Guild Artisan",
        "summary": "Member of a craft guild.",
        "skill_proficiencies": ["insight", "persuasion"],
    },
    {
        "key": "hermit",
        "name": "Hermit",
        "summary": "Secluded seeker of truth.",
        "skill_proficiencies": ["medicine", "religion"],
    },
    {
        "key": "noble",
        "name": "Noble",
        "summary": "Raised among aristocracy.",
        "skill_proficiencies": ["history", "persuasion"],
    },
    {
        "key": "outlander",
        "name": "Outlander",
        "summary": "Raised in the wilds far from cities.",
        "skill_proficiencies": ["athletics", "survival"],
    },
    {
        "key": "sage",
        "name": "Sage",
        "summary": "Dedicated researcher and lore keeper.",
        "skill_proficiencies": ["arcana", "history"],
    },
    {
        "key": "sailor",
        "name": "Sailor",
        "summary": "Seasoned crew member of seafaring life.",
        "skill_proficiencies": ["athletics", "perception"],
    },
    {
        "key": "soldier",
        "name": "Soldier",
        "summary": "Trained in organized warfare.",
        "skill_proficiencies": ["athletics", "intimidation"],
    },
    {
        "key": "urchin",
        "name": "Urchin",
        "summary": "Streetwise survivor of urban hardship.",
        "skill_proficiencies": ["sleight_of_hand", "stealth"],
    },
)

ALL_SKILL_KEYS = (
    "acrobatics",
    "animal_handling",
    "arcana",
    "athletics",
    "deception",
    "history",
    "insight",
    "intimidation",
    "investigation",
    "medicine",
    "nature",
    "perception",
    "performance",
    "persuasion",
    "religion",
    "sleight_of_hand",
    "stealth",
    "survival",
)


def _normalize_species_entry(raw: dict[str, Any], *, source: str) -> dict[str, Any]:
    key = str(raw.get("key") or "").strip().lower()
    name = str(raw.get("name") or key).strip()
    mods = raw.get("ability_modifiers") or {}
    clean_mods = {a: int(mods.get(a, 0) or 0) for a in ABILITIES}
    return {
        "key": key,
        "name": name,
        "summary": str(raw.get("summary") or raw.get("notes") or "").strip()[:500],
        "ability_modifiers": clean_mods,
        "flex_ability_bonuses": int(raw.get("flex_ability_bonuses") or 0),
        "source": source,
        "provenance": source,
    }


def _species_from_compendium(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in entries:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "").strip().lower()
        name = str(row.get("name") or "").strip()
        if not key or not name:
            continue
        mods = row.get("ability_modifiers") or {}
        out.append(
            _normalize_species_entry(
                {
                    "key": key,
                    "name": name,
                    "summary": row.get("summary") or row.get("notes") or "",
                    "ability_modifiers": mods,
                    "flex_ability_bonuses": row.get("flex_ability_bonuses") or 0,
                },
                source="species_compendium",
            )
        )
    return out


def _species_from_gm_options(options: dict[str, Any]) -> list[dict[str, Any]]:
    raw_list = options.get("species") if isinstance(options, dict) else None
    if not isinstance(raw_list, list):
        return []
    out = []
    for row in raw_list:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "").strip().lower()
        if key.startswith("core:"):
            continue
        out.append(_normalize_species_entry(row, source="gm_custom"))
    return out


def _normalize_class_entry(raw: dict[str, Any], *, source: str) -> dict[str, Any]:
    key = str(raw.get("key") or "").strip().lower()
    name = str(raw.get("name") or key).strip()
    skill_cfg = deepcopy(raw.get("skill_choices") or {"count": 2, "options": []})
    if skill_cfg.get("options") == "any":
        skill_cfg["options"] = list(ALL_SKILL_KEYS)
    elif isinstance(skill_cfg.get("options"), list):
        skill_cfg["options"] = [
            str(item).strip().lower()
            for item in skill_cfg["options"]
            if str(item).strip().lower() in ALL_SKILL_KEYS
        ]
    return {
        "key": key,
        "name": name,
        "summary": str(raw.get("summary") or "").strip()[:500],
        "hit_die": int(raw.get("hit_die") or 8),
        "save_proficiencies": list(raw.get("save_proficiencies") or []),
        "skill_choices": skill_cfg,
        "source": source,
        "provenance": source,
    }


def _classes_from_compendium(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in entries:
        if not isinstance(row, dict):
            continue
        if row.get("is_hidden") or row.get("secret"):
            continue
        key = str(row.get("key") or "").strip().lower()
        name = str(row.get("name") or "").strip()
        if not key or not name:
            continue
        out.append(
            _normalize_class_entry(
                row,
                source=str(row.get("source") or "classes_compendium"),
            )
        )
    return out


def merged_creation_catalog(
    *,
    campaign_id: Optional[int] = None,
    species_compendium: Optional[list[dict[str, Any]]] = None,
    classes_compendium: Optional[list[dict[str, Any]]] = None,
    character_options: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Merge core catalog, species/classes compendiums, and GM options deterministically."""
    by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    def _add(entry: dict[str, Any], *, allow_override: bool) -> None:
        key = entry["key"]
        if key in by_key and not allow_override:
            return
        by_key[key] = entry
        if key not in order:
            order.append(key)

    for raw in CORE_SPECIES:
        _add(_normalize_species_entry(raw, source="core"), allow_override=False)

    if species_compendium:
        for entry in _species_from_compendium(species_compendium):
            if entry["key"] in by_key and by_key[entry["key"]]["source"] == "core":
                continue
            _add(entry, allow_override=True)

    if character_options:
        for entry in _species_from_gm_options(character_options):
            namespaced_key = f"gm:{entry['key']}"
            entry = deepcopy(entry)
            entry["key"] = namespaced_key
            _add(entry, allow_override=True)

    species = [by_key[k] for k in order if k in by_key]

    backgrounds = [deepcopy(b) for b in CORE_BACKGROUNDS]
    if character_options and isinstance(character_options.get("backgrounds"), list):
        for row in character_options["backgrounds"]:
            if not isinstance(row, dict):
                continue
            key = str(row.get("key") or "").strip().lower()
            name = str(row.get("name") or "").strip()
            if not key or not name:
                continue
            backgrounds.append(
                {
                    "key": f"gm:{key}",
                    "name": name[:60],
                    "summary": str(row.get("summary") or "")[:500],
                    "skill_proficiencies": list(row.get("skill_proficiencies") or [])[:4],
                    "source": "gm_custom",
                }
            )

    class_by_key: dict[str, dict[str, Any]] = {}
    class_order: list[str] = []

    def _add_class(entry: dict[str, Any], *, allow_override: bool) -> None:
        key = entry["key"]
        if key in class_by_key and not allow_override:
            return
        class_by_key[key] = entry
        if key not in class_order:
            class_order.append(key)

    for raw in CORE_CLASSES:
        _add_class(_normalize_class_entry(raw, source="core"), allow_override=False)

    if classes_compendium:
        for entry in _classes_from_compendium(classes_compendium):
            if (
                entry["key"] in class_by_key
                and class_by_key[entry["key"]]["source"] == "core"
                and entry.get("source") == "classes_compendium"
            ):
                _add_class(entry, allow_override=True)
            else:
                _add_class(entry, allow_override=True)

    classes = [class_by_key[k] for k in class_order if k in class_by_key]

    return {
        "species": species,
        "classes": classes,
        "backgrounds": backgrounds,
        "skill_keys": list(ALL_SKILL_KEYS),
    }


def catalog_entry_by_key(catalog: dict[str, Any], kind: str, key: str) -> Optional[dict[str, Any]]:
    items = catalog.get(kind) or []
    needle = (key or "").strip().lower()
    for row in items:
        if str(row.get("key") or "").lower() == needle:
            return row
    return None
