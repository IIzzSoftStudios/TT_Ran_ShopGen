"""SRD mechanical class progression tables for all 12 PHB base classes.

Feature names are mechanical labels only — no copied book prose.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.services.character_creation.progression_helpers import proficiency_bonus

# Bump when SRD class data must be re-merged into existing campaign compendiums.
CURRENT_SRD_SEED_VERSION = 4

_ASI = {
    "name": "Ability Score Improvement",
    "description": "Increase one ability score by 2, or two ability scores by 1 each.",
}
_ASI_LEVELS = frozenset({4, 8, 12, 16, 19})

_ASI_CHOICE = {
    "type": "ability_scores",
    "title": "Ability Score Improvement",
    "description": "Add +2 to one ability score, or +1 to two different scores, on your character sheet.",
}


def _row(
    level: int,
    *,
    features: list[str] | None = None,
    spell_slots: dict[str, int] | None = None,
    pact_magic: dict[str, int] | None = None,
    cantrips_known: int | None = None,
    spells_known: int | None = None,
    spells_prepared: int | None = None,
    invocations_known: int | None = None,
    resources: dict[str, int] | None = None,
    player_choices: list[dict[str, str]] | None = None,
    trait_keys: list[str] | None = None,
    progression_stats: dict[str, int] | None = None,
    notes: str = "",
) -> dict[str, Any]:
    feature_objs = [{"name": name, "description": ""} for name in (features or [])]
    if level in _ASI_LEVELS:
        feature_objs.append(deepcopy(_ASI))
    choices = list(player_choices or [])
    if level in _ASI_LEVELS and not any(c.get("type") == "ability_scores" for c in choices):
        choices.append(deepcopy(_ASI_CHOICE))
    out: dict[str, Any] = {
        "level": level,
        "proficiency_bonus": proficiency_bonus(level),
        "features": feature_objs,
        "trait_keys": list(trait_keys or []),
        "spell_slots": dict(spell_slots or {}),
        "resources": dict(resources or {}),
        "notes": notes,
        "player_choices": choices,
        "progression_stats": dict(progression_stats or {}),
    }
    if pact_magic is not None:
        out["pact_magic"] = dict(pact_magic)
    if cantrips_known is not None:
        out["cantrips_known"] = cantrips_known
    if spells_known is not None:
        out["spells_known"] = spells_known
    if spells_prepared is not None:
        out["spells_prepared"] = spells_prepared
    if invocations_known is not None:
        out["invocations_known"] = invocations_known
    return out


# PHB full-caster slot progression (wizard, cleric, druid, bard, sorcerer)
_FULL_CASTER_SLOTS: tuple[dict[str, int], ...] = (
    {"1": 2},
    {"1": 3},
    {"1": 4, "2": 2},
    {"1": 4, "2": 3},
    {"1": 4, "2": 3, "3": 2},
    {"1": 4, "2": 3, "3": 3},
    {"1": 4, "2": 3, "3": 3, "4": 1},
    {"1": 4, "2": 3, "3": 3, "4": 2},
    {"1": 4, "2": 3, "3": 3, "4": 3, "5": 1},
    {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2},
    {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1},
    {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1},
    {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1, "7": 1},
    {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1, "7": 1},
    {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1, "7": 1, "8": 1},
    {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1, "7": 1, "8": 1},
    {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1, "7": 1, "8": 1, "9": 1},
    {"1": 4, "2": 3, "3": 3, "4": 3, "5": 3, "6": 1, "7": 1, "8": 1, "9": 1},
    {"1": 4, "2": 3, "3": 3, "4": 3, "5": 3, "6": 2, "7": 1, "8": 1, "9": 1},
    {"1": 4, "2": 3, "3": 3, "4": 3, "5": 3, "6": 2, "7": 2, "8": 1, "9": 1},
)

# PHB half-caster (paladin, ranger) — slots start at level 2
_HALF_CASTER_SLOTS: tuple[dict[str, int], ...] = (
    {},
    {"1": 2},
    {"1": 3},
    {"1": 3},
    {"1": 4, "2": 2},
    {"1": 4, "2": 2},
    {"1": 4, "2": 3},
    {"1": 4, "2": 3},
    {"1": 4, "2": 3, "3": 2},
    {"1": 4, "2": 3, "3": 2},
    {"1": 4, "2": 3, "3": 3},
    {"1": 4, "2": 3, "3": 3},
    {"1": 4, "2": 3, "3": 3, "4": 1},
    {"1": 4, "2": 3, "3": 3, "4": 1},
    {"1": 4, "2": 3, "3": 3, "4": 2},
    {"1": 4, "2": 3, "3": 3, "4": 2},
    {"1": 4, "2": 3, "3": 3, "4": 3, "5": 1},
    {"1": 4, "2": 3, "3": 3, "4": 3, "5": 1},
    {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2},
    {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2},
)


def _full_caster_progression(
    *,
    cantrips: tuple[int, ...],
    spells_known: tuple[int, ...] | None = None,
    spells_prepared: tuple[int, ...] | None = None,
    level_features: dict[int, list[str]],
) -> list[dict[str, Any]]:
    rows = []
    for level in range(1, 21):
        feats = list(level_features.get(level, []))
        kwargs: dict[str, Any] = {
            "features": feats,
            "spell_slots": dict(_FULL_CASTER_SLOTS[level - 1]),
            "cantrips_known": cantrips[level - 1],
        }
        if spells_known is not None:
            kwargs["spells_known"] = spells_known[level - 1]
        if spells_prepared is not None:
            kwargs["spells_prepared"] = spells_prepared[level - 1]
        rows.append(_row(level, **kwargs))
    return rows


def _half_caster_progression(
    *,
    cantrips: tuple[int, ...],
    spells_prepared: tuple[int, ...],
    level_features: dict[int, list[str]],
    resources: dict[int, dict[str, int]] | None = None,
) -> list[dict[str, Any]]:
    rows = []
    for level in range(1, 21):
        feats = list(level_features.get(level, []))
        rows.append(
            _row(
                level,
                features=feats,
                spell_slots=dict(_HALF_CASTER_SLOTS[level - 1]),
                cantrips_known=cantrips[level - 1],
                spells_prepared=spells_prepared[level - 1],
                resources=dict((resources or {}).get(level, {})),
            )
        )
    return rows


def _martial_progression(
    level_features: dict[int, list[str]],
    resources: dict[int, dict[str, int]] | None = None,
) -> list[dict[str, Any]]:
    return [
        _row(
            level,
            features=list(level_features.get(level, [])),
            resources=dict((resources or {}).get(level, {})),
        )
        for level in range(1, 21)
    ]


def _warlock_progression() -> list[dict[str, Any]]:
    """Warlock table per SRD — pact magic, invocations, spells known."""
    data = [
        # level, features, cantrips, spells, pact_slots, pact_level, invocations, choices
        (1, ["Otherworldly Patron", "Pact Magic"], 2, 2, 1, 1, 0, []),
        (2, ["Eldritch Invocations"], 2, 3, 2, 1, 2, []),
        (3, ["Pact Boon"], 2, 4, 2, 2, 2, []),
        (4, [], 3, 5, 2, 2, 2, []),
        (5, [], 3, 6, 2, 3, 3, []),
        (6, ["Otherworldly Patron Feature"], 3, 7, 2, 3, 3, []),
        (7, [], 3, 8, 2, 4, 4, []),
        (8, [], 3, 9, 2, 4, 4, []),
        (9, [], 3, 10, 2, 5, 5, []),
        (10, ["Otherworldly Patron Feature"], 4, 10, 2, 5, 5, []),
        (11, ["Mystic Arcanum (6th level)"], 4, 11, 3, 5, 5, [{"type": "mystic_arcanum", "title": "Mystic Arcanum (6th)", "description": "Learn one 6th-level warlock spell."}]),
        (12, [], 4, 11, 3, 5, 6, []),
        (13, ["Mystic Arcanum (7th level)"], 4, 12, 3, 5, 6, [{"type": "mystic_arcanum", "title": "Mystic Arcanum (7th)", "description": "Learn one 7th-level warlock spell."}]),
        (14, ["Otherworldly Patron Feature"], 4, 12, 3, 5, 6, []),
        (15, ["Mystic Arcanum (8th level)"], 4, 13, 3, 5, 7, [{"type": "mystic_arcanum", "title": "Mystic Arcanum (8th)", "description": "Learn one 8th-level warlock spell."}]),
        (16, [], 4, 13, 3, 5, 7, []),
        (17, ["Mystic Arcanum (9th level)"], 4, 14, 4, 5, 7, [{"type": "mystic_arcanum", "title": "Mystic Arcanum (9th)", "description": "Learn one 9th-level warlock spell."}]),
        (18, [], 4, 14, 4, 5, 8, []),
        (19, [], 4, 15, 4, 5, 8, []),
        (20, ["Eldritch Master"], 4, 15, 4, 5, 8, []),
    ]
    rows = []
    for level, feats, cantrips, spells, slots, slot_lvl, inv, choices in data:
        inv_val = inv if inv > 0 else None
        rows.append(
            _row(
                level,
                features=feats,
                cantrips_known=cantrips,
                spells_known=spells,
                pact_magic={"slots": slots, "slot_level": slot_lvl},
                invocations_known=inv_val,
                player_choices=choices,
            )
        )
    return rows


# Wizard cantrips known by level (PHB)
_WIZARD_CANTRIPS = (3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4)
_WIZARD_SPELLS_PREPARED = (4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 16, 16, 17, 17, 18, 19, 20, 21, 22)

_WIZARD_FEATURES: dict[int, list[str]] = {
    1: ["Spellcasting", "Arcane Recovery"],
    2: ["Arcane Tradition"],
    18: ["Spell Mastery"],
    20: ["Signature Spells"],
}

# Sorcerer spells known (PHB table approximation)
_SORCERER_CANTRIPS = (4, 4, 4, 5, 5, 5, 5, 5, 5, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6)
_SORCERER_SPELLS_KNOWN = (2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 12, 13, 13, 14, 14, 15, 15, 15, 15)
_SORCERER_FEATURES: dict[int, list[str]] = {
    1: ["Spellcasting", "Sorcerous Origin"],
    2: ["Font of Magic"],
    3: ["Metamagic"],
    20: ["Sorcerous Restoration"],
}

# Cleric prepared = level + WIS (we store base table as spells_prepared minimum guidance)
_CLERIC_CANTRIPS = (3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4)
_CLERIC_PREPARED = (2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21)
_CLERIC_FEATURES: dict[int, list[str]] = {
    1: ["Spellcasting", "Divine Domain"],
    2: ["Channel Divinity", "Divine Domain Feature"],
    5: ["Destroy Undead"],
    8: ["Divine Domain Feature"],
    10: ["Divine Intervention"],
    17: ["Destroy Undead (CR 4)"],
    20: ["Divine Intervention Improvement"],
}

# Druid
_DRUID_CANTRIPS = (2, 2, 2, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4)
_DRUID_PREPARED = (2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21)
_DRUID_FEATURES: dict[int, list[str]] = {
    1: ["Druidic", "Spellcasting"],
    2: ["Wild Shape", "Druid Circle"],
    4: ["Wild Shape Improvement"],
    18: ["Timeless Body", "Beast Spells"],
    20: ["Archdruid"],
}

# Bard
_BARD_CANTRIPS = (2, 2, 2, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4)
_BARD_SPELLS_KNOWN = (4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 15, 16, 16, 17, 17, 18, 18, 19, 19)
_BARD_FEATURES: dict[int, list[str]] = {
    1: ["Spellcasting", "Bardic Inspiration"],
    2: ["Jack of All Trades", "Song of Rest"],
    3: ["Bard College", "Expertise"],
    5: ["Font of Inspiration"],
    10: ["Magical Secrets", "Bardic Inspiration die d10"],
    15: ["Magical Secrets"],
    20: ["Superior Inspiration"],
}

# Paladin
_PALADIN_CANTRIPS = (0,) * 20
_PALADIN_PREPARED = (0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20)
_PALADIN_FEATURES: dict[int, list[str]] = {
    1: ["Divine Sense", "Lay on Hands"],
    2: ["Fighting Style", "Spellcasting", "Divine Smite"],
    3: ["Sacred Oath", "Channel Divinity"],
    5: ["Extra Attack"],
    6: ["Aura of Protection"],
    10: ["Aura of Courage"],
    11: ["Improved Divine Smite"],
    14: ["Cleansing Touch"],
}

# Ranger
_RANGER_CANTRIPS = (0,) * 20
_RANGER_PREPARED = (0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20)
_RANGER_FEATURES: dict[int, list[str]] = {
    1: ["Favored Enemy", "Natural Explorer"],
    2: ["Fighting Style", "Spellcasting"],
    3: ["Ranger Archetype", "Primeval Awareness"],
    5: ["Extra Attack"],
    8: ["Land's Stride"],
    10: ["Hide in Plain Sight", "Natural Explorer Improvement"],
    14: ["Vanish"],
    18: ["Feral Senses"],
    20: ["Foe Slayer"],
}

# Barbarian rage uses per level
_BARBARIAN_RAGES: dict[int, dict[str, int]] = {
    1: {"rage": 2},
    3: {"rage": 3},
    6: {"rage": 4},
    12: {"rage": 5},
    17: {"rage": 6},
    20: {"rage": 99},  # unlimited at 20 — display cap
}
_BARBARIAN_FEATURES: dict[int, list[str]] = {
    1: ["Rage", "Unarmored Defense"],
    2: ["Reckless Attack", "Danger Sense"],
    3: ["Primal Path"],
    5: ["Extra Attack", "Fast Movement"],
    7: ["Feral Instinct"],
    9: ["Brutal Critical"],
    11: ["Relentless Rage"],
    15: ["Persistent Rage"],
    18: ["Indomitable Might"],
    20: ["Primal Champion"],
}


def _barbarian_resources(level: int) -> dict[str, int]:
    rage = 2
    for threshold, res in sorted(_BARBARIAN_RAGES.items()):
        if level >= threshold:
            rage = res["rage"]
    return {"rage": rage}


# Fighter
_FIGHTER_FEATURES: dict[int, list[str]] = {
    1: ["Fighting Style", "Second Wind"],
    2: ["Action Surge"],
    3: ["Martial Archetype"],
    5: ["Extra Attack"],
    9: ["Indomitable"],
    11: ["Extra Attack (2)"],
    13: ["Indomitable (2 uses)"],
    17: ["Action Surge (2)", "Indomitable (3 uses)"],
    20: ["Extra Attack (3)"],
}
_FIGHTER_RESOURCES: dict[int, dict[str, int]] = {
    1: {"second_wind": 1},
    2: {"second_wind": 1, "action_surge": 1},
    17: {"second_wind": 1, "action_surge": 2, "indomitable": 3},
}


def _fighter_resources(level: int) -> dict[str, int]:
    res = {"second_wind": 1, "action_surge": 1, "indomitable": 0}
    if level >= 2:
        res["action_surge"] = 2 if level >= 17 else 1
    if level >= 9:
        res["indomitable"] = 1
    if level >= 13:
        res["indomitable"] = 2
    if level >= 17:
        res["indomitable"] = 3
    return res


# Monk ki points
def _monk_resources(level: int) -> dict[str, int]:
    if level < 2:
        return {}
    return {"ki": level}


_MONK_FEATURES: dict[int, list[str]] = {
    1: ["Unarmored Defense", "Martial Arts"],
    2: ["Ki", "Unarmored Movement"],
    3: ["Monastic Tradition", "Deflect Missiles"],
    4: ["Slow Fall"],
    5: ["Extra Attack", "Stunning Strike"],
    6: ["Ki-Empowered Strikes", "Monastic Tradition Feature"],
    7: ["Evasion", "Stillness of Mind"],
    10: ["Purity of Body"],
    13: ["Tongue of the Sun and Moon"],
    14: ["Diamond Soul"],
    15: ["Timeless Body"],
    18: ["Empty Body"],
    20: ["Perfect Self"],
}

# Rogue sneak attack dice in progression_stats
def _rogue_sneak_dice(level: int) -> int:
    return (level + 1) // 2


_ROGUE_FEATURES: dict[int, list[str]] = {
    1: ["Expertise", "Sneak Attack", "Thieves' Cant"],
    2: ["Cunning Action"],
    3: ["Roguish Archetype"],
    5: ["Uncanny Dodge"],
    7: ["Evasion"],
    11: ["Reliable Talent"],
    14: ["Blindsense"],
    18: ["Elusive"],
    20: ["Stroke of Luck"],
}


def _rogue_progression() -> list[dict[str, Any]]:
    rows = []
    for level in range(1, 21):
        rows.append(
            _row(
                level,
                features=list(_ROGUE_FEATURES.get(level, [])),
                progression_stats={"sneak_attack_dice": _rogue_sneak_dice(level)},
            )
        )
    return rows


def _barbarian_progression() -> list[dict[str, Any]]:
    rows = []
    for level in range(1, 21):
        rows.append(
            _row(
                level,
                features=list(_BARBARIAN_FEATURES.get(level, [])),
                resources=_barbarian_resources(level),
            )
        )
    return rows


def _fighter_progression() -> list[dict[str, Any]]:
    rows = []
    for level in range(1, 21):
        rows.append(
            _row(
                level,
                features=list(_FIGHTER_FEATURES.get(level, [])),
                resources=_fighter_resources(level),
            )
        )
    return rows


def _monk_progression() -> list[dict[str, Any]]:
    rows = []
    for level in range(1, 21):
        rows.append(
            _row(
                level,
                features=list(_MONK_FEATURES.get(level, [])),
                resources=_monk_resources(level),
            )
        )
    return rows


SRD_CLASS_PROGRESSIONS: dict[str, dict[str, Any]] = {
    "barbarian": {
        "spellcasting": {"type": "none", "ability": "cha"},
        "progression_columns": [],
        "level_progression": _barbarian_progression(),
    },
    "bard": {
        "spellcasting": {"type": "full", "ability": "cha"},
        "progression_columns": [],
        "level_progression": _full_caster_progression(
            cantrips=_BARD_CANTRIPS,
            spells_known=_BARD_SPELLS_KNOWN,
            level_features=_BARD_FEATURES,
        ),
    },
    "cleric": {
        "spellcasting": {"type": "full", "ability": "wis"},
        "progression_columns": [],
        "level_progression": _full_caster_progression(
            cantrips=_CLERIC_CANTRIPS,
            spells_prepared=_CLERIC_PREPARED,
            level_features=_CLERIC_FEATURES,
        ),
    },
    "druid": {
        "spellcasting": {"type": "full", "ability": "wis"},
        "progression_columns": [],
        "level_progression": _full_caster_progression(
            cantrips=_DRUID_CANTRIPS,
            spells_prepared=_DRUID_PREPARED,
            level_features=_DRUID_FEATURES,
        ),
    },
    "fighter": {
        "spellcasting": {"type": "none", "ability": "int"},
        "progression_columns": [],
        "level_progression": _fighter_progression(),
    },
    "monk": {
        "spellcasting": {"type": "none", "ability": "wis"},
        "progression_columns": [],
        "level_progression": _monk_progression(),
    },
    "paladin": {
        "spellcasting": {"type": "half", "ability": "cha"},
        "progression_columns": [],
        "level_progression": _half_caster_progression(
            cantrips=_PALADIN_CANTRIPS,
            spells_prepared=_PALADIN_PREPARED,
            level_features=_PALADIN_FEATURES,
        ),
    },
    "ranger": {
        "spellcasting": {"type": "half", "ability": "wis"},
        "progression_columns": [],
        "level_progression": _half_caster_progression(
            cantrips=_RANGER_CANTRIPS,
            spells_prepared=_RANGER_PREPARED,
            level_features=_RANGER_FEATURES,
        ),
    },
    "rogue": {
        "spellcasting": {"type": "none", "ability": "int"},
        "progression_columns": [{"key": "sneak_attack_dice", "label": "Sneak Attack Dice"}],
        "level_progression": _rogue_progression(),
    },
    "sorcerer": {
        "spellcasting": {"type": "known", "ability": "cha"},
        "progression_columns": [],
        "level_progression": _full_caster_progression(
            cantrips=_SORCERER_CANTRIPS,
            spells_known=_SORCERER_SPELLS_KNOWN,
            level_features=_SORCERER_FEATURES,
        ),
    },
    "warlock": {
        "spellcasting": {"type": "pact", "ability": "cha"},
        "progression_columns": [],
        "level_progression": _warlock_progression(),
    },
    "wizard": {
        "spellcasting": {"type": "full", "ability": "int"},
        "progression_columns": [],
        "level_progression": _full_caster_progression(
            cantrips=_WIZARD_CANTRIPS,
            spells_prepared=_WIZARD_SPELLS_PREPARED,
            level_features=_WIZARD_FEATURES,
        ),
    },
}

from app.services.character_creation.dnd5e_srd_class_traits import (
    _refresh_srd_class_traits_cache,
    enrich_progression_trait_keys,
)

for _class_key, _bundle in SRD_CLASS_PROGRESSIONS.items():
    enrich_progression_trait_keys(_class_key, _bundle["level_progression"])

_refresh_srd_class_traits_cache()
