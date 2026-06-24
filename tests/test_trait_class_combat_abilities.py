"""Tests for trait class combat ability effects (Extra Attack, UD, Action Surge)."""

from __future__ import annotations

import uuid

import pytest

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import Campaign, User
from app.services.combat.combat_profile_builder import build_player_combat_profile
from app.services.combat.multiattack_rules import resolve_extra_attack_count
from app.services.traits_compendium_service import (
    clean_trait_effects,
    ensure_traits_compendium,
    resolve_trait_effects,
    update_trait,
)
from app.services.classes_compendium_service import ensure_classes_compendium
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
    user = User(username="trait-combat-gm", password="x", role="GM")
    user.set_password("Secret1!")
    db.session.add(user)
    db.session.commit()
    ensure_gm_profile(user)
    db.session.commit()
    campaign = Campaign(
        gm_profile_id=user.gm_profile.id,
        name="Trait Combat",
        system_type="dnd5e",
        is_active=True,
        current_game_day=1,
        join_code=f"CAMP-{uuid.uuid4().hex[:8].upper()}",
    )
    db.session.add(campaign)
    db.session.commit()
    return campaign


def test_clean_trait_effects_accepts_class_combat_abilities():
    effects = clean_trait_effects(
        {
            "extra_attacks_per_action": 3,
            "unarmored_defense": True,
            "unarmored_ac_add_ability": "con",
            "unarmored_defense_allows_shield": True,
            "action_surge": True,
            "action_surge_additional_actions": 1,
        }
    )
    assert effects["extra_attacks_per_action"] == 3
    assert effects["unarmored_defense"] is True
    assert effects["action_surge"] is True


def test_extra_attack_from_trait_profile():
    campaign = _campaign()
    ensure_traits_compendium(campaign.id)
    update_trait(
        campaign.id,
        "cf-extra-attack",
        {
            "name": "Extra Attack",
            "category": "attack",
            "effects": {"extra_attacks_per_action": 2},
            "prerequisites": {},
            "notes": "",
            "summary": "",
            "rules_text": "",
        },
    )
    db.session.commit()
    fighter = next(row for row in ensure_classes_compendium(campaign.id) if row["key"] == "fighter")
    sheet = {
        "level": 5,
        "abilities": {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 10, "cha": 8},
        "creation": {"class_key": "fighter", "species_key": "human"},
        "class_trait_selections": {"5": ["cf-extra-attack"]},
    }
    profile = build_player_combat_profile(campaign.id, sheet, class_entry=fighter)
    assert profile.get("extra_attacks_per_action") == 2
    assert resolve_extra_attack_count(fighter, 5, combat_profile=profile) == 2


def test_unarmored_defense_trait_effects_merge():
    campaign = _campaign()
    ensure_traits_compendium(campaign.id)
    merged = resolve_trait_effects(
        campaign.id,
        ["cf-barbarian-unarmored-defense"],
        context={"level": 1, "class_key": "barbarian", "species_key": "human", "abilities": {}},
    )
    assert merged.get("unarmored_defense") is True
    assert merged.get("unarmored_ac_add_ability") == "con"
    assert merged.get("unarmored_defense_allows_shield") is True
