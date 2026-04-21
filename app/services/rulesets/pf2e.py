"""Pathfinder 2e rule set definition."""
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
    SkillDef("arcana", "Arcana", "int"),
    SkillDef("athletics", "Athletics", "str"),
    SkillDef("crafting", "Crafting", "int"),
    SkillDef("deception", "Deception", "cha"),
    SkillDef("diplomacy", "Diplomacy", "cha"),
    SkillDef("intimidation", "Intimidation", "cha"),
    SkillDef("lore", "Lore", "int"),
    SkillDef("medicine", "Medicine", "wis"),
    SkillDef("nature", "Nature", "wis"),
    SkillDef("occultism", "Occultism", "int"),
    SkillDef("performance", "Performance", "cha"),
    SkillDef("religion", "Religion", "wis"),
    SkillDef("society", "Society", "int"),
    SkillDef("stealth", "Stealth", "dex"),
    SkillDef("survival", "Survival", "wis"),
    SkillDef("thievery", "Thievery", "dex"),
)

SAVES = (
    SaveDef("fortitude", "Fortitude", "con"),
    SaveDef("reflex", "Reflex", "dex"),
    SaveDef("will", "Will", "wis"),
)

DERIVED = (
    DerivedDef("hp_max", "Max HP", header=True),
    DerivedDef("hp_current", "Current HP", header=True),
    DerivedDef("ac", "AC", header=True),
    DerivedDef("perception", "Perception", header=True),
    DerivedDef("speed", "Speed"),
)

TIERS = (
    ProficiencyTier("untrained", "Untrained", 0, 0.0),
    ProficiencyTier("trained", "Trained", 1, 1.0),
    ProficiencyTier("expert", "Expert", 2, 1.0),
    ProficiencyTier("master", "Master", 3, 1.0),
    ProficiencyTier("legendary", "Legendary", 4, 1.0),
)


def _prof_bonus_pf2e(level):
    # PF2e proficiency bonus = level + tier_bonus; here we return the level
    # component. The tier-specific +2/+4/+6/+8 is layered on in the service.
    try:
        lvl = int(level) if level is not None else 0
    except (TypeError, ValueError):
        lvl = 0
    return max(lvl, 0)


def _ability_mod_pf2e(score):
    # PF2e uses the same (score - 10) / 2, floored.
    return (score - 10) // 2


RULESET = Ruleset(
    system_type="pf2e",
    display_name="Pathfinder 2e",
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
    _ability_mod_fn=_ability_mod_pf2e,
    _prof_bonus_fn=_prof_bonus_pf2e,
)
