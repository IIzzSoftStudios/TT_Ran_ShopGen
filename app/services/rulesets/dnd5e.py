"""D&D 5e rule set definition."""
from app.services.rulesets.base import (
    AbilityDef,
    DerivedDef,
    ProficiencyTier,
    Ruleset,
    SaveDef,
    SkillDef,
)


ABILITIES = (
    AbilityDef("str", "Strength"),
    AbilityDef("dex", "Dexterity"),
    AbilityDef("con", "Constitution"),
    AbilityDef("int", "Intelligence"),
    AbilityDef("wis", "Wisdom"),
    AbilityDef("cha", "Charisma"),
)

SKILLS = (
    SkillDef("acrobatics", "Acrobatics", "dex"),
    SkillDef("animal_handling", "Animal Handling", "wis"),
    SkillDef("arcana", "Arcana", "int"),
    SkillDef("athletics", "Athletics", "str"),
    SkillDef("deception", "Deception", "cha"),
    SkillDef("history", "History", "int"),
    SkillDef("insight", "Insight", "wis"),
    SkillDef("intimidation", "Intimidation", "cha"),
    SkillDef("investigation", "Investigation", "int"),
    SkillDef("medicine", "Medicine", "wis"),
    SkillDef("nature", "Nature", "int"),
    SkillDef("perception", "Perception", "wis"),
    SkillDef("performance", "Performance", "cha"),
    SkillDef("persuasion", "Persuasion", "cha"),
    SkillDef("religion", "Religion", "int"),
    SkillDef("sleight_of_hand", "Sleight of Hand", "dex"),
    SkillDef("stealth", "Stealth", "dex"),
    SkillDef("survival", "Survival", "wis"),
)

SAVES = (
    SaveDef("str", "Strength Save", "str"),
    SaveDef("dex", "Dexterity Save", "dex"),
    SaveDef("con", "Constitution Save", "con"),
    SaveDef("int", "Intelligence Save", "int"),
    SaveDef("wis", "Wisdom Save", "wis"),
    SaveDef("cha", "Charisma Save", "cha"),
)

DERIVED = (
    DerivedDef("hp_max", "Max HP", header=True),
    DerivedDef("hp_current", "Current HP", header=True),
    DerivedDef("ac", "AC", header=True),
    DerivedDef("initiative", "Initiative", header=True),
    DerivedDef("passive_perception", "Perception", header=True),
)

TIERS = (
    ProficiencyTier("half", "Half", 1, 0.5),
    ProficiencyTier("normal", "Normal", 2, 1.0),
    ProficiencyTier("expertise", "Expertise", 3, 2.0),
)


def _prof_bonus(level):
    # Stock 5e progression: +2 at 1-4, +3 at 5-8, +4 at 9-12, +5 at 13-16, +6 at 17-20.
    if level is None or level <= 0:
        return 2
    return 2 + ((level - 1) // 4)


RULESET = Ruleset(
    system_type="dnd5e",
    display_name="D&D 5e",
    abilities=ABILITIES,
    skills=SKILLS,
    saves=SAVES,
    derived=DERIVED,
    proficiency_tiers=TIERS,
    supports_skill_proficiency=True,
    supports_save_proficiency=True,
    ability_min=1,
    ability_max=30,
    ability_default=10,
    _prof_bonus_fn=_prof_bonus,
)
