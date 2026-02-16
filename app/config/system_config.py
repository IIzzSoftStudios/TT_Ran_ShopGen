from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Literal


StatInputType = Literal["number", "text"]


@dataclass(frozen=True)
class StatField:
    """Represents a single stat/field on a character sheet for a given system."""

    key: str
    category: str | None
    label: str
    input_type: StatInputType = "number"


SYSTEM_DND5E = "dnd5e"
SYSTEM_PF2E = "pf2e"
SYSTEM_SAVAGE_WORLDS = "savage_worlds"
SYSTEM_GENERIC = "generic"


SYSTEM_SCHEMAS: Dict[str, List[StatField]] = {
    SYSTEM_GENERIC: [
        StatField("STR", "ability", "Strength"),
        StatField("DEX", "ability", "Dexterity"),
        StatField("CON", "ability", "Constitution"),
        StatField("INT", "ability", "Intelligence"),
        StatField("WIS", "ability", "Wisdom"),
        StatField("CHA", "ability", "Charisma"),
    ],
    SYSTEM_DND5E: [
        # Core abilities
        StatField("STR", "ability", "Strength"),
        StatField("DEX", "ability", "Dexterity"),
        StatField("CON", "ability", "Constitution"),
        StatField("INT", "ability", "Intelligence"),
        StatField("WIS", "ability", "Wisdom"),
        StatField("CHA", "ability", "Charisma"),
        # Common derived stats
        StatField("HP", "derived", "Hit Points"),
        StatField("AC", "derived", "Armor Class"),
        StatField("PB", "derived", "Proficiency Bonus"),
    ],
    SYSTEM_PF2E: [
        StatField("STR", "ability", "Strength"),
        StatField("DEX", "ability", "Dexterity"),
        StatField("CON", "ability", "Constitution"),
        StatField("INT", "ability", "Intelligence"),
        StatField("WIS", "ability", "Wisdom"),
        StatField("CHA", "ability", "Charisma"),
        StatField("HP", "derived", "Hit Points"),
        StatField("AC", "derived", "Armor Class"),
        StatField("Perception", "skill", "Perception", input_type="number"),
        StatField("Class_DC", "derived", "Class DC"),
    ],
    SYSTEM_SAVAGE_WORLDS: [
        StatField("Agility", "attribute", "Agility", input_type="text"),
        StatField("Smarts", "attribute", "Smarts", input_type="text"),
        StatField("Spirit", "attribute", "Spirit", input_type="text"),
        StatField("Strength", "attribute", "Strength", input_type="text"),
        StatField("Vigor", "attribute", "Vigor", input_type="text"),
        StatField("Parry", "derived", "Parry"),
        StatField("Toughness", "derived", "Toughness"),
        StatField("Bennies", "resource", "Bennies"),
    ],
}


def get_system_schema(system_type: str) -> List[StatField]:
    """
    Return the configured schema for a system.
    Falls back to generic if the system is unknown.
    """
    normalized = (system_type or SYSTEM_GENERIC).lower()

    # Simple normalization so templates can use friendly keys while DB stores strings
    if normalized in {"dnd", "dnd5e", "5e"}:
        key = SYSTEM_DND5E
    elif normalized in {"pf2", "pf2e", "pathfinder2e"}:
        key = SYSTEM_PF2E
    elif normalized in {"savage_worlds", "savage-worlds", "swade"}:
        key = SYSTEM_SAVAGE_WORLDS
    else:
        key = SYSTEM_GENERIC

    return SYSTEM_SCHEMAS.get(key, SYSTEM_SCHEMAS[SYSTEM_GENERIC])


def seed_default_stats_for_character(character, system_type: str, db_session) -> None:
    """
    Create CharacterStat rows for a character based on the system schema.
    Intended to replace the hard-coded base_stats list in the player character handler.
    """
    from app.models.users import CharacterStat  # local import to avoid circulars

    schema = get_system_schema(system_type)
    for field in schema:
        db_session.add(
            CharacterStat(
                character_id=character.id,
                stat_key=field.key,
                category=field.category,
                value=None,
            )
        )

