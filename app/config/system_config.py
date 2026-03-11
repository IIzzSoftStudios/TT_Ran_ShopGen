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
        # Saving throws (manual entry for now)
        StatField("STR_SAVE", "save", "Strength Save"),
        StatField("DEX_SAVE", "save", "Dexterity Save"),
        StatField("CON_SAVE", "save", "Constitution Save"),
        StatField("INT_SAVE", "save", "Intelligence Save"),
        StatField("WIS_SAVE", "save", "Wisdom Save"),
        StatField("CHA_SAVE", "save", "Charisma Save"),
        # Example skills (SRD-aligned)
        StatField("Acrobatics", "skill", "Acrobatics"),
        StatField("Animal_Handling", "skill", "Animal Handling"),
        StatField("Arcana", "skill", "Arcana"),
        StatField("Athletics", "skill", "Athletics"),
        StatField("Deception", "skill", "Deception"),
        StatField("History", "skill", "History"),
        StatField("Insight", "skill", "Insight"),
        StatField("Intimidation", "skill", "Intimidation"),
        StatField("Investigation", "skill", "Investigation"),
        StatField("Medicine", "skill", "Medicine"),
        StatField("Nature", "skill", "Nature"),
        StatField("Perception", "skill", "Perception"),
        StatField("Performance", "skill", "Performance"),
        StatField("Persuasion", "skill", "Persuasion"),
        StatField("Religion", "skill", "Religion"),
        StatField("Sleight_of_Hand", "skill", "Sleight of Hand"),
        StatField("Stealth", "skill", "Stealth"),
        StatField("Survival", "skill", "Survival"),
        # Skill proficiency tiers (0 = Untrained, 1 = Half, 2 = Proficient, 3 = Expertise)
        StatField("Acrobatics", "skill_prof_tier", "Acrobatics Proficiency Tier"),
        StatField("Animal_Handling", "skill_prof_tier", "Animal Handling Proficiency Tier"),
        StatField("Arcana", "skill_prof_tier", "Arcana Proficiency Tier"),
        StatField("Athletics", "skill_prof_tier", "Athletics Proficiency Tier"),
        StatField("Deception", "skill_prof_tier", "Deception Proficiency Tier"),
        StatField("History", "skill_prof_tier", "History Proficiency Tier"),
        StatField("Insight", "skill_prof_tier", "Insight Proficiency Tier"),
        StatField("Intimidation", "skill_prof_tier", "Intimidation Proficiency Tier"),
        StatField("Investigation", "skill_prof_tier", "Investigation Proficiency Tier"),
        StatField("Medicine", "skill_prof_tier", "Medicine Proficiency Tier"),
        StatField("Nature", "skill_prof_tier", "Nature Proficiency Tier"),
        StatField("Perception", "skill_prof_tier", "Perception Proficiency Tier"),
        StatField("Performance", "skill_prof_tier", "Performance Proficiency Tier"),
        StatField("Persuasion", "skill_prof_tier", "Persuasion Proficiency Tier"),
        StatField("Religion", "skill_prof_tier", "Religion Proficiency Tier"),
        StatField("Sleight_of_Hand", "skill_prof_tier", "Sleight of Hand Proficiency Tier"),
        StatField("Stealth", "skill_prof_tier", "Stealth Proficiency Tier"),
        StatField("Survival", "skill_prof_tier", "Survival Proficiency Tier"),
        # Saving throw proficiency flags (0 = not proficient, 1 = proficient)
        StatField("STR_SAVE", "save_prof_flag", "Strength Save Proficiency"),
        StatField("DEX_SAVE", "save_prof_flag", "Dexterity Save Proficiency"),
        StatField("CON_SAVE", "save_prof_flag", "Constitution Save Proficiency"),
        StatField("INT_SAVE", "save_prof_flag", "Intelligence Save Proficiency"),
        StatField("WIS_SAVE", "save_prof_flag", "Wisdom Save Proficiency"),
        StatField("CHA_SAVE", "save_prof_flag", "Charisma Save Proficiency"),
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
        # Perception and saves
        StatField("Perception", "skill", "Perception", input_type="number"),
        StatField("Fortitude", "save", "Fortitude Save"),
        StatField("Reflex", "save", "Reflex Save"),
        StatField("Will", "save", "Will Save"),
        StatField("Class_DC", "derived", "Class DC"),
        # Core skills (subset, ORC-friendly)
        StatField("Acrobatics", "skill", "Acrobatics"),
        StatField("Arcana", "skill", "Arcana"),
        StatField("Athletics", "skill", "Athletics"),
        StatField("Crafting", "skill", "Crafting"),
        StatField("Deception", "skill", "Deception"),
        StatField("Diplomacy", "skill", "Diplomacy"),
        StatField("Intimidation", "skill", "Intimidation"),
        StatField("Lore", "skill", "Lore"),
        StatField("Medicine", "skill", "Medicine"),
        StatField("Nature", "skill", "Nature"),
        StatField("Occultism", "skill", "Occultism"),
        StatField("Performance", "skill", "Performance"),
        StatField("Religion", "skill", "Religion"),
        StatField("Society", "skill", "Society"),
        StatField("Stealth", "skill", "Stealth"),
        StatField("Survival", "skill", "Survival"),
        StatField("Thievery", "skill", "Thievery"),
        # Skill ranks (0, 2, 4, 6, 8)
        StatField("Perception", "skill_rank", "Perception Rank Bonus"),
        StatField("Acrobatics", "skill_rank", "Acrobatics Rank Bonus"),
        StatField("Arcana", "skill_rank", "Arcana Rank Bonus"),
        StatField("Athletics", "skill_rank", "Athletics Rank Bonus"),
        StatField("Crafting", "skill_rank", "Crafting Rank Bonus"),
        StatField("Deception", "skill_rank", "Deception Rank Bonus"),
        StatField("Diplomacy", "skill_rank", "Diplomacy Rank Bonus"),
        StatField("Intimidation", "skill_rank", "Intimidation Rank Bonus"),
        StatField("Lore", "skill_rank", "Lore Rank Bonus"),
        StatField("Medicine", "skill_rank", "Medicine Rank Bonus"),
        StatField("Nature", "skill_rank", "Nature Rank Bonus"),
        StatField("Occultism", "skill_rank", "Occultism Rank Bonus"),
        StatField("Performance", "skill_rank", "Performance Rank Bonus"),
        StatField("Religion", "skill_rank", "Religion Rank Bonus"),
        StatField("Society", "skill_rank", "Society Rank Bonus"),
        StatField("Stealth", "skill_rank", "Stealth Rank Bonus"),
        StatField("Survival", "skill_rank", "Survival Rank Bonus"),
        StatField("Thievery", "skill_rank", "Thievery Rank Bonus"),
        # Save ranks (0, 2, 4, 6, 8)
        StatField("Fortitude", "save_rank", "Fortitude Rank Bonus"),
        StatField("Reflex", "save_rank", "Reflex Rank Bonus"),
        StatField("Will", "save_rank", "Will Rank Bonus"),
    ],
    SYSTEM_SAVAGE_WORLDS: [
        # Generic action RPG-style attributes (labels kept generic)
        StatField("Agility_Generic", "ability", "Agility", input_type="text"),
        StatField("Smarts_Generic", "ability", "Smarts", input_type="text"),
        StatField("Spirit_Generic", "ability", "Spirit", input_type="text"),
        StatField("Strength_Generic", "ability", "Strength", input_type="text"),
        StatField("Vigor_Generic", "ability", "Vigor", input_type="text"),
        # Generic defenses
        StatField("Defense", "derived", "Defense"),
        StatField("Resilience", "derived", "Resilience"),
        # Generic resource pool
        StatField("Fortune_Tokens", "resource", "Fortune Tokens"),
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

