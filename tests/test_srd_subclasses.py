"""Tests for SRD subclass seeds and trait linkage."""

from __future__ import annotations

import pytest

from app.services.character_creation.dnd5e_srd_subclasses import (
    ALL_CORE_SUBCLASSES,
    CORE_SUBCLASSES_BY_CLASS,
)
from app.services.character_creation.dnd5e_srd_subclass_traits import SRD_SUBCLASS_TRAITS_BY_KEY
from app.services.character_creation.subclasses._helpers import trait_key_for_subclass_feature


def test_twelve_srd_subclasses_seeded():
    assert len(ALL_CORE_SUBCLASSES) == 12
    assert len(CORE_SUBCLASSES_BY_CLASS) == 12


def test_barbarian_berserker_feature_grants():
    berserker = next(
        row for row in CORE_SUBCLASSES_BY_CLASS["barbarian"] if row["key"] == "path-of-the-berserker"
    )
    assert berserker["pick_level"] == 3
    levels = {grant["level"] for grant in berserker["feature_grants"]}
    assert levels == {3, 6, 10, 14}
    names = {grant["name"] for grant in berserker["feature_grants"]}
    assert "Frenzy" in names
    assert "Mindless Rage" in names


def test_subclass_traits_linked_by_key():
    key = trait_key_for_subclass_feature("path-of-the-berserker", "Frenzy")
    assert key == "scf-path-of-the-berserker-frenzy"
    trait = SRD_SUBCLASS_TRAITS_BY_KEY[key]
    assert trait["prerequisites"]["class_keys"] == ["barbarian"]
    assert trait["prerequisites"]["subclass_keys"] == ["path-of-the-berserker"]
    assert trait["prerequisites"]["min_level"] == 3


def test_cleric_life_domain_picks_at_level_one():
    life = next(row for row in CORE_SUBCLASSES_BY_CLASS["cleric"] if row["key"] == "life-domain")
    assert life["pick_level"] == 1
