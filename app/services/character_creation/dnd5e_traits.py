"""Mechanical trait templates for combat (no SRD rules text).

Traits are reusable effect bundles referenced by species, classes, and monsters
via ``trait_keys``. GMs may author custom traits in the traits compendium.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

ABILITIES = ("str", "dex", "con", "int", "wis", "cha")

_CATEGORIES = frozenset(
    {"sense", "movement", "defense", "save", "attack", "resource", "condition", "other"}
)


def _trait(
    key: str,
    name: str,
    category: str,
    effects: dict[str, Any],
    *,
    tags: list[str] | None = None,
    prerequisites: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if category not in _CATEGORIES:
        category = "other"
    return {
        "key": key,
        "name": name,
        "source": "base",
        "origin_template_key": key,
        "category": category,
        "effects": deepcopy(effects),
        "prerequisites": deepcopy(prerequisites or {}),
        "tags": list(tags or []),
        "stacking": "max",
        "notes": "",
    }


# Base mechanical templates (SRD-aligned numbers, generic labels only).
CORE_TRAITS: tuple[dict[str, Any], ...] = (
    _trait("speed-25", "Speed 25 ft", "movement", {"speed_ft": 25}),
    _trait("speed-30", "Speed 30 ft", "movement", {"speed_ft": 30}),
    _trait("size-small", "Small size", "movement", {"size": "small"}),
    _trait("size-medium", "Medium size", "movement", {"size": "medium"}),
    _trait("size-large", "Large size", "movement", {"size": "large"}),
    _trait("darkvision-60", "Darkvision 60 ft", "sense", {"darkvision_ft": 60}, tags=["sense"]),
    _trait("darkvision-120", "Darkvision 120 ft", "sense", {"darkvision_ft": 120}, tags=["sense"]),
    _trait("resist-poison", "Poison damage resistance", "defense", {"damage_resistances": ["poison"]}),
    _trait("resist-fire", "Fire damage resistance", "defense", {"damage_resistances": ["fire"]}),
    _trait("resist-acid", "Acid damage resistance", "defense", {"damage_resistances": ["acid"]}),
    _trait("resist-cold", "Cold damage resistance", "defense", {"damage_resistances": ["cold"]}),
    _trait("resist-lightning", "Lightning damage resistance", "defense", {"damage_resistances": ["lightning"]}),
    _trait("immune-poison", "Poison damage immunity", "defense", {"damage_immunities": ["poison"]}),
    _trait("save-adv-charmed", "Advantage vs charmed", "save", {"save_advantage_vs_conditions": ["charmed"]}),
    _trait("save-adv-frightened", "Advantage vs frightened", "save", {"save_advantage_vs_conditions": ["frightened"]}),
    _trait("save-adv-poisoned", "Advantage vs poisoned", "save", {"save_advantage_vs_conditions": ["poisoned"]}),
    _trait(
        "save-adv-magic-int-wis-cha",
        "Advantage on Int/Wis/Cha saves vs magic",
        "save",
        {"save_advantage_vs_magic": ["int", "wis", "cha"]},
    ),
    _trait("lucky", "Lucky (reroll nat 1)", "attack", {"lucky": True}),
    _trait("savage-attacks", "Extra damage die on melee crit", "attack", {"savage_attacks": True}),
    _trait(
        "relentless-endurance",
        "Drop to 1 HP once",
        "resource",
        {"relentless_endurance": True},
        prerequisites={"ability_scores": {"con": 11}},
    ),
)

CORE_TRAITS_BY_KEY: dict[str, dict[str, Any]] = {row["key"]: row for row in CORE_TRAITS}
