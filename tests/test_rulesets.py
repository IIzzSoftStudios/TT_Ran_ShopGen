"""Tests for the rule set registry and per-system schema definitions.

These tests are intentionally pure-Python (no Flask app / DB required) so
they exercise only the registry + math contract that the character sheet
service relies on.
"""
from app.services.rulesets import (
    Ruleset,
    get_ruleset,
    known_system_types,
    register,
)
from app.services.rulesets.dnd5e import RULESET as DND5E
from app.services.rulesets.pf2e import RULESET as PF2E
from app.services.rulesets.generic import RULESET as GENERIC


def test_known_system_types_includes_builtins():
    st = set(known_system_types())
    assert {"dnd5e", "pf2e", "generic"}.issubset(st)


def test_get_ruleset_exact_match():
    assert get_ruleset("dnd5e") is DND5E
    assert get_ruleset("pf2e") is PF2E
    assert get_ruleset("generic") is GENERIC


def test_get_ruleset_case_and_alias():
    assert get_ruleset("DND5E") is DND5E
    assert get_ruleset("dnd") is DND5E
    assert get_ruleset("5e") is DND5E


def test_get_ruleset_unknown_falls_back_to_generic():
    assert get_ruleset("homebrew_flavor_of_the_week") is GENERIC
    assert get_ruleset(None) is GENERIC
    assert get_ruleset("") is GENERIC


def test_ability_modifier_dnd5e():
    assert DND5E.compute_ability_mod(10) == 0
    assert DND5E.compute_ability_mod(8) == -1
    assert DND5E.compute_ability_mod(12) == 1
    assert DND5E.compute_ability_mod(18) == 4
    assert DND5E.compute_ability_mod(None) == 0
    assert DND5E.compute_ability_mod("not a number") == 0


def test_clamp_ability_dnd5e():
    assert DND5E.clamp_ability(14) == 14
    assert DND5E.clamp_ability(0) == DND5E.ability_min
    assert DND5E.clamp_ability(999) == DND5E.ability_max
    assert DND5E.clamp_ability("abc") is None


def test_proficiency_bonus_dnd5e_curve():
    assert DND5E.proficiency_bonus(1) == 2
    assert DND5E.proficiency_bonus(4) == 2
    assert DND5E.proficiency_bonus(5) == 3
    assert DND5E.proficiency_bonus(9) == 4
    assert DND5E.proficiency_bonus(13) == 5
    assert DND5E.proficiency_bonus(17) == 6


def test_dnd5e_has_eighteen_skills_and_six_saves():
    assert len(DND5E.skills) == 18
    assert len(DND5E.saves) == 6
    keys = DND5E.skill_keys()
    # Sample a few canonical skills.
    for must_have in ("athletics", "stealth", "perception", "persuasion"):
        assert must_have in keys


def test_pf2e_has_sixteen_or_seventeen_skills_and_three_saves():
    # PF2E has 16 core + Lore placeholder = 17 in our table.
    assert len(PF2E.skills) >= 16
    assert len(PF2E.saves) == 3
    assert {"fortitude", "reflex", "will"} == set(PF2E.save_keys())


def test_pf2e_tiers_include_legendary():
    tier_keys = [t.key for t in PF2E.proficiency_tiers]
    assert tier_keys == ["untrained", "trained", "expert", "master", "legendary"]


def test_generic_has_no_skills_or_saves():
    assert GENERIC.skills == ()
    assert GENERIC.saves == ()
    assert GENERIC.supports_skill_proficiency is False
    assert GENERIC.supports_save_proficiency is False


def test_tier_by_value_lookup():
    tier = DND5E.tier_by_value(2)
    assert tier is not None and tier.key == "normal"
    assert DND5E.tier_by_value(99) is None
    assert DND5E.tier_by_value("not an int") is None


def test_register_replaces_existing_entry():
    marker = Ruleset(
        system_type="dnd5e_test_marker",
        display_name="Marker",
        abilities=(),
        skills=(),
        saves=(),
        derived=(),
        proficiency_tiers=(),
    )
    register(marker)
    assert get_ruleset("dnd5e_test_marker") is marker


def test_register_rejects_non_ruleset():
    import pytest
    with pytest.raises(TypeError):
        register({"not": "a ruleset"})


def test_to_meta_shape():
    meta = DND5E.to_meta()
    assert meta["system_type"] == "dnd5e"
    assert meta["supports_skill_proficiency"] is True
    assert meta["supports_save_proficiency"] is True
    assert isinstance(meta["proficiency_tiers"], list)
    assert all({"key", "label", "value"}.issubset(t) for t in meta["proficiency_tiers"])
