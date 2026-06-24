"""Tests for SRD multiattack parsing and combat resolution."""

from __future__ import annotations

from random import Random

import pytest

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import BattleCombatant, Campaign, User
from app.services.combat import CombatValidationError, encounter_service
from app.services.combat.multiattack_rules import (
    build_multiattack_entry,
    extra_attack_count,
    parse_multiattack_attack_keys,
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


def test_parse_adult_red_dragon_multiattack():
    attacks = [
        {"key": "bite", "name": "Bite."},
        {"key": "claw", "name": "Claw."},
        {"key": "tail", "name": "Tail."},
    ]
    token_map = {"bite": "bite", "claw": "claw", "tail": "tail"}
    description = (
        "The dragon can use its Frightful Presence. It then makes three attacks: "
        "one with its bite and two with its claws."
    )
    keys = parse_multiattack_attack_keys(description, token_map, fallback_key="bite")
    assert keys == ["bite", "claw", "claw"]


def test_build_multiattack_entry_from_srd_action():
    attacks = [
        {"key": "bite", "name": "Bite."},
        {"key": "claw", "name": "Claw."},
    ]
    action = {
        "name": "Multiattack.",
        "description": "The hezrou makes three attacks: one with its bite and two with its claws.",
    }
    entry = build_multiattack_entry(action, attacks)
    assert entry is not None
    assert entry["attack_keys"] == ["bite", "claw", "claw"]


def test_extra_attack_count_from_progression():
    class_entry = {
        "level_progression": [
            {"level": 4, "features": []},
            {
                "level": 5,
                "features": [
                    {
                        "name": "Extra Attack",
                        "description": "You can attack twice, instead of once, whenever you take the Attack action.",
                    }
                ],
            },
            {
                "level": 11,
                "features": [
                    {
                        "name": "Extra Attack (2)",
                        "description": "You can attack three times whenever you take the Attack action.",
                    }
                ],
            },
        ]
    }
    assert extra_attack_count(class_entry, 4) == 1
    assert extra_attack_count(class_entry, 5) == 2
    assert extra_attack_count(class_entry, 11) == 3


def test_extra_attack_count_from_feature_names():
    class_entry = {
        "level_progression": [
            {"level": 4, "features": []},
            {"level": 5, "features": [{"name": "Extra Attack", "description": ""}]},
            {
                "level": 11,
                "features": [
                    {
                        "name": "Extra Attack",
                        "description": "You can attack three times whenever you take the Attack action.",
                    }
                ],
            },
        ]
    }
    assert extra_attack_count(class_entry, 4) == 1
    assert extra_attack_count(class_entry, 5) == 2
    assert extra_attack_count(class_entry, 11) == 3


def _make_campaign() -> Campaign:
    user = User(username="ma-gm", password="x", role="GM")
    user.set_password("Secret1!")
    db.session.add(user)
    db.session.commit()
    ensure_gm_profile(user)
    db.session.commit()
    db.session.refresh(user)
    campaign = Campaign(
        gm_profile_id=user.gm_profile.id,
        name="ma-camp",
        system_type="dnd5e",
        is_active=True,
        current_game_day=1,
    )
    db.session.add(campaign)
    db.session.commit()
    return campaign


def _seed_avoiding_nat1() -> Random:
    for seed in range(500):
        if Random(seed).randint(1, 20) > 1:
            return Random(seed)
    raise AssertionError("no seed found")


def _add_dragon(encounter):
    combatant = BattleCombatant(
        encounter_id=encounter.id,
        campaign_id=encounter.campaign_id,
        name="Dragon",
        side="foe",
        status="active",
        x=0,
        y=0,
        hp_max=200,
        hp_current=200,
        temp_hp=0,
        ac=19,
        speed_ft=40,
        dex_mod=0,
        ability_json={"str": 27},
        action_data_json={
            "attacks": [
                {
                    "key": "bite",
                    "name": "Bite",
                    "kind": "melee",
                    "attack_mod": 14,
                    "damage": "2d10+8",
                    "damage_type": "piercing",
                    "range_ft": 10,
                },
                {
                    "key": "claw",
                    "name": "Claw",
                    "kind": "melee",
                    "attack_mod": 14,
                    "damage": "2d6+8",
                    "damage_type": "slashing",
                    "range_ft": 5,
                },
            ],
            "multiattacks": [
                {
                    "key": "multiattack",
                    "name": "Multiattack",
                    "attack_keys": ["bite", "claw", "claw"],
                }
            ],
        },
        resources_json={"action": True, "bonus_action": True, "reaction": True},
        conditions_json=[],
    )
    db.session.add(combatant)
    db.session.commit()
    return combatant


def test_multiattack_resolves_all_swings_and_consumes_one_action():
    campaign = _make_campaign()
    encounter = encounter_service.create_encounter(campaign.id, "Dragon fight")
    dragon = _add_dragon(encounter)
    target = BattleCombatant(
        encounter_id=encounter.id,
        campaign_id=encounter.campaign_id,
        name="Fighter",
        side="party",
        status="active",
        x=1,
        y=0,
        hp_max=80,
        hp_current=80,
        temp_hp=0,
        ac=18,
        speed_ft=30,
        dex_mod=2,
        ability_json={"str": 16},
        action_data_json={"attacks": []},
        resources_json={"action": True, "bonus_action": True, "reaction": True},
        conditions_json=[],
    )
    db.session.add(target)
    db.session.commit()
    encounter_service.roll_initiative(encounter, Random(1))
    db.session.commit()
    dragon.initiative_order = 1
    target.initiative_order = 2
    db.session.commit()

    before_hp = target.hp_current
    result = encounter_service.multiattack_action(
        encounter,
        dragon,
        target.id,
        "multiattack",
        _seed_avoiding_nat1(),
    )
    db.session.commit()

    assert len(result["results"]) == 3
    assert all("to_hit" in swing for swing in result["results"])
    assert dragon.resources_json["action"] is False
    assert target.hp_current < before_hp
    with pytest.raises(CombatValidationError):
        encounter_service.multiattack_action(
            encounter,
            dragon,
            target.id,
            "multiattack",
            Random(2),
        )
