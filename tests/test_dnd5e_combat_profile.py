"""Tests for SRD combat profile helpers and encounter integration."""

from __future__ import annotations

from random import Random

import pytest

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import BattleCombatant, Campaign, User
from app.services.combat import dnd5e_combat_profile as profile
from app.services.combat import encounter_service
from app.services.user_capabilities import ensure_gm_profile


@pytest.fixture(autouse=True)
def _db_tables():
    flask_app.config["WTF_CSRF_ENABLED"] = False
    with flask_app.app_context():
        db.create_all()
        yield
        db.session.rollback()
        db.drop_all()


def _make_campaign(username: str) -> Campaign:
    user = User(username=username, password="x", role="GM")
    user.set_password("Secret1!")
    db.session.add(user)
    db.session.commit()
    ensure_gm_profile(user)
    db.session.commit()
    db.session.refresh(user)
    campaign = Campaign(
        gm_profile_id=user.gm_profile.id,
        name=f"{username}-camp",
        system_type="dnd5e",
        is_active=True,
        current_game_day=1,
    )
    db.session.add(campaign)
    db.session.commit()
    return campaign


def test_species_speed_profiles():
    assert profile.species_profile("dwarf")["speed_ft"] == 25
    assert profile.species_profile("elf")["speed_ft"] == 30
    assert profile.species_profile("tiefling")["damage_resistances"] == ["fire"]


def test_damage_resistance_halves():
    out = profile.apply_damage_modifiers(
        10, "fire", {"damage_resistances": ["fire"]}
    )
    assert out["total"] == 5
    assert "resistance" in out["applied"]


def test_damage_immunity_zeros():
    out = profile.apply_damage_modifiers(
        20, "poison", {"damage_immunities": ["poison"]}
    )
    assert out["total"] == 0


def test_flanking_detects_opposite_allies():
    assert profile.is_flanking(0, 0, 1, 0, [(2, 0)], attack_kind="melee")
    assert not profile.is_flanking(0, 0, 2, 0, [(1, 0)], attack_kind="melee")


def test_cover_bonus_from_blocker():
    bonus = profile.cover_ac_bonus(0, 0, 4, 0, [(2, 0)])
    assert bonus == 2


def test_lucky_rerolls_natural_one(monkeypatch):
    calls = {"n": 0}

    def fake_d20(mod, rng, mode="normal"):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "rolls": [1],
                "natural": 1,
                "total": 1 + mod,
                "mode": mode,
                "is_nat20": False,
                "is_nat1": True,
            }
        return {
            "rolls": [15],
            "natural": 15,
            "total": 15 + mod,
            "mode": mode,
            "is_nat20": False,
            "is_nat1": False,
        }

    monkeypatch.setattr(profile.rules, "d20_roll", fake_d20)
    result = profile.roll_d20_with_lucky(2, Random(1), "normal", {"lucky": True})
    assert result["lucky_reroll"] is True
    assert result["natural"] == 15


def test_monster_profile_parses_immunities():
    stats = {
        "speed_ft": 40,
        "senses": "darkvision 60 ft.",
        "damage_immunities": "fire",
        "damage_resistances": "cold",
        "condition_immunities": "poisoned",
        "saving_throws": "Dex +5, Con +10",
        "legendary_actions": [{"key": "tail", "name": "Tail", "cost": 1}],
    }
    parsed = profile.monster_profile(stats)
    assert parsed["darkvision_ft"] == 60
    assert "fire" in parsed["damage_immunities"]
    assert parsed["save_bonuses"]["dex"] == 5
    assert parsed["legendary_points_max"] == 3


def test_attack_includes_cover_ac_detail():
    campaign = _make_campaign("srd-cover")
    encounter = encounter_service.create_encounter(campaign.id, "Cover Test")
    db.session.commit()

    blocker = BattleCombatant(
        encounter_id=encounter.id,
        campaign_id=campaign.id,
        name="Blocker",
        side="party",
        status="active",
        x=1,
        y=0,
        hp_max=10,
        hp_current=10,
        ac=10,
        speed_ft=30,
        dex_mod=0,
        ability_json={"con": 10},
        action_data_json={"attacks": []},
        resources_json=encounter_service._fresh_resources(),
        conditions_json=[],
    )
    target = BattleCombatant(
        encounter_id=encounter.id,
        campaign_id=campaign.id,
        name="Tiefling",
        side="foe",
        status="active",
        x=2,
        y=0,
        hp_max=20,
        hp_current=20,
        ac=12,
        speed_ft=30,
        dex_mod=0,
        ability_json={"con": 10},
        action_data_json={
            "attacks": [],
            "combat_profile": profile.species_profile("tiefling"),
        },
        resources_json=encounter_service._fresh_resources(),
        conditions_json=[],
    )
    attacker = BattleCombatant(
        encounter_id=encounter.id,
        campaign_id=campaign.id,
        name="Mage",
        side="party",
        status="active",
        x=0,
        y=0,
        hp_max=10,
        hp_current=10,
        ac=10,
        speed_ft=30,
        dex_mod=0,
        ability_json={"str": 10},
        action_data_json={
            "attacks": [
                {
                    "key": "fire",
                    "name": "Fire Bolt",
                    "kind": "ranged",
                    "attack_mod": 20,
                    "damage": "2d10",
                    "damage_type": "fire",
                    "range_ft": 120,
                }
            ]
        },
        resources_json=encounter_service._fresh_resources(),
        conditions_json=[],
    )
    db.session.add_all([blocker, target, attacker])
    db.session.commit()

    encounter.settings_json = dict(encounter.settings_json or {})
    encounter.settings_json["cover"] = True
    encounter.status = "active"
    encounter.round_number = 1
    encounter.turn_index = 0
    attacker.initiative_order = 0
    target.initiative_order = 1
    blocker.initiative_order = 2
    db.session.commit()

    result = encounter_service.attack_action(
        encounter, attacker, target.id, "fire", Random(9999)
    )
    assert result["ac_detail"]["cover_bonus"] == 2
