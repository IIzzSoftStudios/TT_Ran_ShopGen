"""Tests for SRD class feature traits and progression trait_keys."""

from __future__ import annotations

import uuid

import pytest

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import Campaign, User
from app.services.character_creation.dnd5e_srd_class_progression import (
    CURRENT_SRD_SEED_VERSION,
    SRD_CLASS_PROGRESSIONS,
)
from app.services.character_creation.dnd5e_srd_class_traits import (
    SRD_CLASS_TRAITS_BY_KEY,
    trait_key_for_feature,
)
from app.services.classes_compendium_service import ensure_classes_compendium
from app.services.combat.combat_profile_builder import build_player_combat_profile
from app.services.traits_compendium_service import ensure_traits_compendium
from app.services.user_capabilities import ensure_gm_profile


@pytest.fixture(autouse=True)
def _db_tables():
    flask_app.config["WTF_CSRF_ENABLED"] = False
    with flask_app.app_context():
        db.create_all()
        yield
        db.session.rollback()
        db.drop_all()


def _make_campaign() -> Campaign:
    user = User(username="srd-class-traits-gm", password="x", role="GM")
    user.set_password("Secret1!")
    db.session.add(user)
    db.session.commit()
    ensure_gm_profile(user)
    db.session.commit()
    campaign = Campaign(
        gm_profile_id=user.gm_profile.id,
        name="SRD Class Traits",
        system_type="dnd5e",
        is_active=True,
        current_game_day=1,
        join_code=f"CAMP-{uuid.uuid4().hex[:8].upper()}",
    )
    db.session.add(campaign)
    db.session.commit()
    return campaign


def test_barbarian_level_one_has_rage_and_unarmored_defense_trait_keys():
    row = SRD_CLASS_PROGRESSIONS["barbarian"]["level_progression"][0]
    assert row["level"] == 1
    assert "cf-barbarian-rage" in row["trait_keys"]
    assert "cf-barbarian-unarmored-defense" in row["trait_keys"]


def test_trait_key_mapping_shared_extra_attack():
    assert trait_key_for_feature("fighter", "Extra Attack") == "cf-extra-attack"
    assert trait_key_for_feature("barbarian", "Extra Attack") == "cf-extra-attack"


def test_traits_compendium_seeds_class_features():
    campaign = _make_campaign()
    keys = {row["key"] for row in ensure_traits_compendium(campaign.id)}
    assert "cf-barbarian-rage" in keys
    assert "cf-barbarian-unarmored-defense" in keys
    assert "cf-monk-unarmored-defense" in keys
    assert "cf-extra-attack" in keys


def test_accumulated_class_features_use_trait_summaries():
    from app.services.character_sheet_service import _accumulated_class_features
    from app.services.classes_compendium_service import ensure_classes_compendium
    from app.services.traits_compendium_service import ensure_traits_compendium

    campaign = _make_campaign()
    ensure_traits_compendium(campaign.id)
    ensure_classes_compendium(campaign.id)
    sheet = {
        "level": 2,
        "abilities": {"str": 8, "dex": 14, "con": 14, "int": 12, "wis": 10, "cha": 16},
        "creation": {"class_key": "warlock", "species_key": "human"},
        "class_name": "Warlock",
    }
    history = _accumulated_class_features(campaign, sheet)
    flat = [feat for row in history for feat in row.get("features") or []]
    patron = next(item for item in flat if item.get("name") == "Otherworldly Patron")
    assert patron.get("description")
    assert "patron" in patron["description"].lower()
    invocations = next(item for item in flat if item.get("name") == "Eldritch Invocations")
    assert invocations.get("description")
    assert "invocation" in invocations["description"].lower()


def test_barbarian_unarmored_defense_trait_has_con_ac_effect():
    trait = SRD_CLASS_TRAITS_BY_KEY["cf-barbarian-unarmored-defense"]
    assert trait["effects"]["unarmored_defense"] is True
    assert trait["effects"]["unarmored_ac_add_ability"] == "con"
    assert trait["effects"]["unarmored_defense_allows_shield"] is True


def test_classes_compendium_reseed_includes_trait_keys():
    campaign = _make_campaign()
    entries = ensure_classes_compendium(campaign.id)
    barbarian = next(row for row in entries if row["key"] == "barbarian")
    assert barbarian.get("srd_seed_version") == CURRENT_SRD_SEED_VERSION
    level_one = barbarian["level_progression"][0]
    assert "cf-barbarian-rage" in level_one["trait_keys"]


def test_barbarian_combat_profile_includes_unarmored_defense():
    campaign = _make_campaign()
    ensure_traits_compendium(campaign.id)
    classes = ensure_classes_compendium(campaign.id)
    barbarian = next(row for row in classes if row["key"] == "barbarian")
    level_one_traits = barbarian["level_progression"][0]["trait_keys"]
    sheet = {
        "level": 1,
        "abilities": {"str": 16, "dex": 14, "con": 16, "int": 8, "wis": 10, "cha": 8},
        "creation": {"class_key": "barbarian", "species_key": "human"},
        "class_trait_selections": {"1": level_one_traits},
    }
    profile = build_player_combat_profile(
        campaign.id,
        sheet,
        class_entry=barbarian,
    )
    assert profile.get("unarmored_ac_add_ability") == "con"
