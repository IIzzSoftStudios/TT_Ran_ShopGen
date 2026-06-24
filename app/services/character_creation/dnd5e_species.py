"""D&D 5e SRD 5.1 species seed catalog (CC-BY-4.0 mechanical shells).

Attribution: System Reference Document 5.1, Wizards of the Coast LLC,
available under Creative Commons Attribution 4.0 International (CC-BY-4.0).
Trait text is mechanical summary only — not copied book prose.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.services.character_creation.srd_species_manifest import SRD_SPECIES_COUNT

ABILITIES = ("str", "dex", "con", "int", "wis", "cha")

DRAGONBORN_ANCESTRY_META: dict[str, dict[str, str]] = {
    "acid": {
        "label": "Acid",
        "damage_type": "acid",
        "breath_shape": "5×30-ft line",
        "trait_key": "resist-acid",
        "breath_summary": (
            "5×30-ft line; DC 8 + CON mod + proficiency; 2d6 acid damage; "
            "half on save; recharge 5–6"
        ),
    },
    "cold": {
        "label": "Cold",
        "damage_type": "cold",
        "breath_shape": "15-ft cone",
        "trait_key": "resist-cold",
        "breath_summary": (
            "15-ft cone; DC 8 + CON mod + proficiency; 2d6 cold damage; "
            "half on save; recharge 5–6"
        ),
    },
    "fire": {
        "label": "Fire",
        "damage_type": "fire",
        "breath_shape": "15-ft cone",
        "trait_key": "resist-fire",
        "breath_summary": (
            "15-ft cone; DC 8 + CON mod + proficiency; 2d6 fire damage; "
            "half on save; recharge 5–6"
        ),
    },
    "lightning": {
        "label": "Lightning",
        "damage_type": "lightning",
        "breath_shape": "15-ft cone",
        "trait_key": "resist-lightning",
        "breath_summary": (
            "15-ft cone; DC 8 + CON mod + proficiency; 2d6 lightning damage; "
            "half on save; recharge 5–6"
        ),
    },
    "poison": {
        "label": "Poison",
        "damage_type": "poison",
        "breath_shape": "15-ft cone",
        "trait_key": "resist-poison",
        "breath_summary": (
            "15-ft cone; DC 8 + CON mod + proficiency; 2d6 poison damage; "
            "half on save; recharge 5–6"
        ),
    },
}

_ZERO_MODS = {ability: 0 for ability in ABILITIES}


def _mods(**kwargs: int) -> dict[str, int]:
    row = dict(_ZERO_MODS)
    for key, value in kwargs.items():
        if key in row:
            row[key] = int(value)
    return row


def _entry(
    key: str,
    name: str,
    *,
    summary: str,
    ability_modifiers: dict[str, int],
    flex_ability_bonuses: int = 0,
    stat_modifiers: str = "",
    traits: list[dict[str, str]] | None = None,
    trait_keys: list[str] | None = None,
    species_skill_proficiencies: list[str] | None = None,
    species_skill_choices: dict[str, Any] | None = None,
    requires_dragonborn_ancestry: bool = False,
) -> dict[str, Any]:
    return {
        "key": key,
        "origin_srd_key": key,
        "name": name,
        "summary": summary,
        "ability_modifiers": ability_modifiers,
        "flex_ability_bonuses": flex_ability_bonuses,
        "stat_modifiers": stat_modifiers,
        "traits": deepcopy(traits or []),
        "trait_keys": list(trait_keys or []),
        "species_skill_proficiencies": list(species_skill_proficiencies or []),
        "species_skill_choices": deepcopy(species_skill_choices) if species_skill_choices else None,
        "requires_dragonborn_ancestry": bool(requires_dragonborn_ancestry),
        "content_source": "srd_5_1",
        "srd_reference": "SRD 5.1",
    }


CORE_SPECIES: tuple[dict[str, Any], ...] = (
    _entry(
        "human",
        "Human",
        summary="Adaptable people with broad aptitude.",
        ability_modifiers=_mods(str=1, dex=1, con=1, int=1, wis=1, cha=1),
        stat_modifiers="Medium size. Speed 30 ft. Common plus one extra language.",
        trait_keys=["speed-30", "size-medium"],
        traits=[
            {
                "name": "Ability Score Increase",
                "description": "+1 to Strength, Dexterity, Constitution, Intelligence, Wisdom, and Charisma.",
            }
        ],
    ),
    _entry(
        "elf",
        "Elf",
        summary="Graceful people with keen senses and fey heritage.",
        ability_modifiers=_mods(dex=2),
        stat_modifiers="Medium size. Speed 30 ft. Common and Elvish.",
        trait_keys=["speed-30", "size-medium", "darkvision-60", "save-adv-charmed"],
        species_skill_proficiencies=["perception"],
        traits=[
            {
                "name": "Darkvision",
                "description": "See in dim light within 60 feet as if bright light, and in darkness as if dim light.",
            },
            {
                "name": "Keen Senses",
                "description": "Proficiency in the Perception skill.",
            },
            {
                "name": "Fey Ancestry",
                "description": "Advantage on saving throws against being charmed; magic cannot put you to sleep.",
            },
            {
                "name": "Trance",
                "description": "Four hours of trance counts as a long rest; remain semiconscious while doing so.",
            },
        ],
    ),
    _entry(
        "dwarf",
        "Dwarf",
        summary="Sturdy folk known for resilience and stonecraft.",
        ability_modifiers=_mods(con=2),
        stat_modifiers="Medium size. Speed 25 ft. (not reduced by heavy armor). Common and Dwarvish.",
        trait_keys=["speed-25", "size-medium", "darkvision-60", "save-adv-poisoned", "resist-poison"],
        traits=[
            {
                "name": "Darkvision",
                "description": "See in dim light within 60 feet as if bright light, and in darkness as if dim light.",
            },
            {
                "name": "Dwarven Resilience",
                "description": "Advantage on saving throws against poison; resistance to poison damage.",
            },
            {
                "name": "Dwarven Combat Training",
                "description": "Proficiency with battleaxe, handaxe, light hammer, and warhammer.",
            },
            {
                "name": "Stonecunning",
                "description": "Add double proficiency bonus to History checks related to stonework origins.",
            },
        ],
    ),
    _entry(
        "halfling",
        "Halfling",
        summary="Small, nimble folk with quick reflexes and steady luck.",
        ability_modifiers=_mods(dex=2),
        stat_modifiers="Small size. Speed 25 ft. Common and Halfling.",
        trait_keys=["speed-25", "size-small", "lucky", "save-adv-frightened"],
        traits=[
            {
                "name": "Lucky",
                "description": "When you roll a 1 on a d20 for an attack roll, ability check, or saving throw, reroll and use the new roll.",
            },
            {
                "name": "Brave",
                "description": "Advantage on saving throws against being frightened.",
            },
            {
                "name": "Halfling Nimbleness",
                "description": "Move through the space of creatures that are a size larger than you.",
            },
        ],
    ),
    _entry(
        "dragonborn",
        "Dragonborn",
        summary="Draconic heritage with breath weapon and elemental resilience.",
        ability_modifiers=_mods(str=2, cha=1),
        stat_modifiers="Medium size. Speed 30 ft. Common and Draconic.",
        trait_keys=["speed-30", "size-medium"],
        requires_dragonborn_ancestry=True,
        traits=[
            {
                "name": "Draconic Ancestry",
                "description": "Choose acid, cold, fire, lightning, or poison. Breath weapon (15-ft cone or 5x30-ft line, DC 8 + Con mod + proficiency, 2d6 damage, half on save; recharge 5-6).",
            },
            {
                "name": "Damage Resistance",
                "description": "Resistance to the damage type tied to your draconic ancestry.",
            },
        ],
    ),
    _entry(
        "gnome",
        "Gnome",
        summary="Curious inventors with quick minds and fey resilience.",
        ability_modifiers=_mods(int=2),
        stat_modifiers="Small size. Speed 25 ft. Common and Gnomish.",
        trait_keys=["speed-25", "size-small", "darkvision-60", "save-adv-magic-int-wis-cha"],
        traits=[
            {
                "name": "Darkvision",
                "description": "See in dim light within 60 feet as if bright light, and in darkness as if dim light.",
            },
            {
                "name": "Gnome Cunning",
                "description": "Advantage on Intelligence, Wisdom, and Charisma saving throws against magic.",
            },
        ],
    ),
    _entry(
        "half-elf",
        "Half-Elf",
        summary="Charismatic blend of human and elven heritage.",
        ability_modifiers=_mods(cha=2),
        flex_ability_bonuses=2,
        stat_modifiers="Medium size. Speed 30 ft. Common, Elvish, and one extra language.",
        trait_keys=["speed-30", "size-medium", "darkvision-60", "save-adv-charmed"],
        species_skill_choices={"count": 2, "options": "any"},
        traits=[
            {
                "name": "Flexible Ability Increase",
                "description": "+1 to two ability scores of your choice (other than Charisma).",
            },
            {
                "name": "Darkvision",
                "description": "See in dim light within 60 feet as if bright light, and in darkness as if dim light.",
            },
            {
                "name": "Fey Ancestry",
                "description": "Advantage on saving throws against being charmed; magic cannot put you to sleep.",
            },
            {
                "name": "Skill Versatility",
                "description": "Proficiency in two skills of your choice.",
            },
        ],
    ),
    _entry(
        "half-orc",
        "Half-Orc",
        summary="Powerful and enduring warriors.",
        ability_modifiers=_mods(str=2, con=1),
        stat_modifiers="Medium size. Speed 30 ft. Common and Orc.",
        trait_keys=["speed-30", "size-medium", "darkvision-60", "savage-attacks", "relentless-endurance"],
        traits=[
            {
                "name": "Darkvision",
                "description": "See in dim light within 60 feet as if bright light, and in darkness as if dim light.",
            },
            {
                "name": "Relentless Endurance",
                "description": "When reduced to 0 hit points but not killed outright, drop to 1 hit point instead (once per long rest).",
            },
            {
                "name": "Savage Attacks",
                "description": "When you score a critical hit with a melee weapon attack, roll one extra damage die.",
            },
        ],
    ),
    _entry(
        "tiefling",
        "Tiefling",
        summary="Infernal legacy with force of personality and fire resilience.",
        ability_modifiers=_mods(cha=2, int=1),
        stat_modifiers="Medium size. Speed 30 ft. Common and Infernal.",
        trait_keys=["speed-30", "size-medium", "darkvision-60", "resist-fire"],
        traits=[
            {
                "name": "Darkvision",
                "description": "See in dim light within 60 feet as if bright light, and in darkness as if dim light.",
            },
            {
                "name": "Hellish Resistance",
                "description": "Resistance to fire damage.",
            },
        ],
    ),
)

if len(CORE_SPECIES) != SRD_SPECIES_COUNT:
    raise RuntimeError(
        f"SRD species catalog mismatch: manifest={SRD_SPECIES_COUNT}, data={len(CORE_SPECIES)}"
    )

CORE_SPECIES_BY_KEY = {row["key"]: row for row in CORE_SPECIES}
