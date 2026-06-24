"""Tests for traits compendium and custom combat profiles."""

from __future__ import annotations

import pytest

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import Campaign, User
from app.services.combat.combat_profile_builder import (
    build_monster_combat_profile,
    build_player_combat_profile,
)
from app.services.classes_compendium_service import ensure_classes_compendium, update_class
from app.services.species_compendium_service import create_species, ensure_species_compendium
from app.services.traits_compendium_service import (
    create_trait,
    ensure_traits_compendium,
    resolve_trait_effects,
)
from app.services.user_capabilities import ensure_gm_profile


@pytest.fixture(autouse=True)
def _db_tables():
    flask_app.config["WTF_CSRF_ENABLED"] = False
    with flask_app.app_context():
        db.create_all()
        yield
        db.session.rollback()
        db.drop_all()


def _campaign() -> Campaign:
    user = User(username="traits-gm", password="x", role="GM")
    user.set_password("Secret1!")
    db.session.add(user)
    db.session.commit()
    ensure_gm_profile(user)
    db.session.commit()
    db.session.refresh(user)
    campaign = Campaign(
        gm_profile_id=user.gm_profile.id,
        name="traits-camp",
        system_type="dnd5e",
        is_active=True,
        current_game_day=1,
    )
    db.session.add(campaign)
    db.session.commit()
    return campaign


def test_traits_compendium_seeds_core_templates():
    campaign = _campaign()
    traits = ensure_traits_compendium(campaign.id)
    keys = {row["key"] for row in traits}
    assert "darkvision-60" in keys
    assert "resist-fire" in keys


def test_create_trait_accepts_condition_immunities():
    campaign = _campaign()
    ensure_traits_compendium(campaign.id)
    entry = create_trait(
        campaign.id,
        {
            "name": "Unshakable",
            "category": "defense",
            "effects": {"condition_immunities": ["frightened", "charmed"]},
        },
    )
    db.session.commit()
    assert "frightened" in entry["effects"]["condition_immunities"]


def test_custom_species_trait_keys_apply_in_combat_profile():
    campaign = _campaign()
    ensure_traits_compendium(campaign.id)
    create_trait(
        campaign.id,
        {
            "name": "Sky Glide",
            "category": "movement",
            "effects": {"speed_ft": 35},
        },
    )
    db.session.commit()
    create_species(
        campaign.id,
        {
            "name": "Sky Folk",
            "population_percent": 5,
            "ability_modifiers": {a: 0 for a in ("str", "dex", "con", "int", "wis", "cha")},
            "trait_keys": "speed-30, resist-fire",
            "stat_modifiers": "Speed 35 ft from glide (fallback parse)",
            "traits": [],
            "notes": "",
        },
    )
    db.session.commit()
    species = next(
        e for e in ensure_species_compendium(campaign.id) if e["name"] == "Sky Folk"
    )
    sheet = {
        "level": 1,
        "abilities": {"str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10},
        "save_prof_flags": {},
        "creation": {"species_key": species["key"]},
    }
    profile = build_player_combat_profile(
        campaign.id, sheet, species_entry=species, class_entry=None
    )
    assert profile["speed_ft"] == 35
    assert "fire" in profile.get("damage_resistances", [])


def test_srd_species_seeded_with_trait_keys():
    campaign = _campaign()
    ensure_traits_compendium(campaign.id)
    tiefling = next(
        e for e in ensure_species_compendium(campaign.id) if e["key"] == "tiefling"
    )
    assert "resist-fire" in tiefling.get("trait_keys", [])


def test_monster_trait_keys_and_resistances_in_combat_profile():
    campaign = _campaign()
    ensure_traits_compendium(campaign.id)
    stats = {
        "hp_max": 40,
        "ac": 15,
        "speed_ft": 30,
        "abilities": {"str": 16, "dex": 12, "con": 14, "int": 8, "wis": 10, "cha": 6},
        "damage_resistances": ["cold"],
        "trait_keys": ["resist-fire", "darkvision-60"],
    }
    profile = build_monster_combat_profile(stats, campaign.id)
    assert "cold" in profile.get("damage_resistances", [])
    assert "fire" in profile.get("damage_resistances", [])
    assert profile.get("darkvision_ft") == 60


def test_trait_prerequisites_block_until_level_met():
    campaign = _campaign()
    ensure_traits_compendium(campaign.id)
    entry = create_trait(
        campaign.id,
        {
            "name": "Veteran Edge",
            "category": "attack",
            "effects": {"lucky": True},
            "prerequisites": {"min_level": 5},
        },
    )
    db.session.commit()
    low = resolve_trait_effects(
        campaign.id,
        [entry["key"]],
        context={"level": 3, "abilities": {"con": 14}},
    )
    high = resolve_trait_effects(
        campaign.id,
        [entry["key"]],
        context={"level": 5, "abilities": {"con": 14}},
    )
    assert not low.get("lucky")
    assert high.get("lucky") is True


def test_trait_prerequisites_require_granted_trait_keys():
    campaign = _campaign()
    ensure_traits_compendium(campaign.id)
    base = create_trait(
        campaign.id,
        {
            "name": "Wings Base",
            "category": "movement",
            "effects": {"speed_ft": 30},
        },
    )
    advanced = create_trait(
        campaign.id,
        {
            "name": "Wings Glide",
            "category": "movement",
            "effects": {"speed_ft": 40},
            "prerequisites": {"trait_keys": [base["key"]]},
        },
    )
    db.session.commit()
    alone = resolve_trait_effects(campaign.id, [advanced["key"]], context={"level": 1})
    chained = resolve_trait_effects(
        campaign.id,
        [base["key"], advanced["key"]],
        context={"level": 1},
    )
    assert alone.get("speed_ft") != 40
    assert chained.get("speed_ft") == 40


def test_relentless_endurance_requires_minimum_con():
    campaign = _campaign()
    ensure_traits_compendium(campaign.id)
    weak = resolve_trait_effects(
        campaign.id,
        ["relentless-endurance"],
        context={"level": 1, "abilities": {"con": 8}},
    )
    tough = resolve_trait_effects(
        campaign.id,
        ["relentless-endurance"],
        context={"level": 1, "abilities": {"con": 12}},
    )
    assert not weak.get("relentless_endurance")
    assert tough.get("relentless_endurance") is True
