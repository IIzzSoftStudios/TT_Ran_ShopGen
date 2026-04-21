"""Generic rule set definition.

Abilities + HP only. No skills, no saves, no proficiency tiers. Chosen as the
safe fallback when a Campaign.system_type is unknown or the GM has not picked
a system. Future GM-configurable rule sets will register themselves against
this registry via ``rulesets.register(...)``.
"""
from app.services.rulesets.base import (
    AbilityDef,
    DerivedDef,
    Ruleset,
)


ABILITIES = (
    AbilityDef("str", "Strength"),
    AbilityDef("dex", "Dexterity"),
    AbilityDef("con", "Constitution"),
    AbilityDef("int", "Intelligence"),
    AbilityDef("wis", "Wisdom"),
    AbilityDef("cha", "Charisma"),
)

DERIVED = (
    DerivedDef("hp_max", "Max HP", header=True),
    DerivedDef("hp_current", "Current HP", header=True),
)


RULESET = Ruleset(
    system_type="generic",
    display_name="Generic",
    abilities=ABILITIES,
    skills=(),
    saves=(),
    derived=DERIVED,
    proficiency_tiers=(),
    supports_skill_proficiency=False,
    supports_save_proficiency=False,
    ability_min=1,
    ability_max=99,
    ability_default=10,
)
