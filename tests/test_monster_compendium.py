"""Tests for the monster compendium service and deterministic generator."""

from __future__ import annotations

import pytest

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import Campaign, User
from app.services.combat import CombatValidationError
from app.services.combat import (
    encounter_service,
    monster_compendium_service,
    monster_generator,
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


_VALID_STATS = {
    "hp_max": 20,
    "ac": 13,
    "speed_ft": 30,
    "abilities": {"str": 14, "dex": 12, "con": 13, "int": 6, "wis": 10, "cha": 6},
    "attacks": [
        {
            "key": "bite",
            "name": "Bite",
            "kind": "melee",
            "attack_mod": 4,
            "damage": "1d6+2",
            "damage_type": "piercing",
            "range_ft": 5,
        }
    ],
    "legendary_actions": [
        {
            "key": "tail_sweep",
            "name": "Tail Sweep",
            "cost": 2,
            "description": "A broad sweep at nearby foes.",
            "attack_mod": 5,
            "damage": "1d8+2",
            "damage_type": "bludgeoning",
            "range_ft": 10,
        }
    ],
}


# ---------------------------------------------------------------------------
# Generator determinism
# ---------------------------------------------------------------------------
def test_generator_same_seed_same_template():
    seed = monster_generator.derive_seed("kobold-camp-3")
    a = monster_generator.generate_monster_template(seed, 2.0)
    b = monster_generator.generate_monster_template(seed, 2.0)
    assert a == b


def test_generator_different_seeds_differ():
    a = monster_generator.generate_monster_template(
        monster_generator.derive_seed("seed-one"), 1.0
    )
    b = monster_generator.generate_monster_template(
        monster_generator.derive_seed("seed-two"), 1.0
    )
    assert a != b


def test_generator_scales_with_challenge():
    seed = monster_generator.derive_seed("scaling-check")
    low = monster_generator.generate_monster_template(seed, 0.25)
    high = monster_generator.generate_monster_template(seed, 8.0)
    assert high["hp_max"] > low["hp_max"]
    assert high["attack_bonus"] >= low["attack_bonus"]


def test_generator_avoids_product_identity_names():
    forbidden = ("beholder", "mind flayer", "illithid", "displacer",
                 "githyanki", "githzerai", "slaad", "umber hulk", "yuan-ti")
    for raw in range(25):
        template = monster_generator.generate_monster_template(
            monster_generator.derive_seed(f"name-{raw}"), 1.0
        )
        lowered = template["name"].lower()
        assert all(bad not in lowered for bad in forbidden)


# ---------------------------------------------------------------------------
# CRUD + campaign scoping
# ---------------------------------------------------------------------------
def test_create_update_delete_entry():
    campaign = _make_campaign("comp-gm-1")
    entry = monster_compendium_service.create_entry(
        campaign.id, "Cave Brute", _VALID_STATS, challenge_rating=1.0
    )
    db.session.commit()
    assert entry.id is not None
    assert entry.stat_json["attacks"][0]["key"] == "bite"
    assert entry.stat_json["legendary_actions"][0]["cost"] == 2

    monster_compendium_service.update_entry(entry, name="Cave Brute Alpha")
    db.session.commit()
    assert entry.name == "Cave Brute Alpha"

    monster_compendium_service.delete_entry(entry)
    db.session.commit()
    assert monster_compendium_service.list_entries(campaign.id) == []


def test_entry_lookup_is_campaign_scoped():
    campaign_a = _make_campaign("comp-gm-a")
    campaign_b = _make_campaign("comp-gm-b")
    entry = monster_compendium_service.create_entry(
        campaign_a.id, "Scoped Beast", _VALID_STATS
    )
    db.session.commit()
    assert (
        monster_compendium_service.entry_for_campaign(entry.id, campaign_b.id) is None
    )
    assert (
        monster_compendium_service.entry_for_campaign(entry.id, campaign_a.id)
        is not None
    )


@pytest.mark.parametrize(
    "mutation",
    [
        {"name": ""},
        {"stats": {"hp_max": 0}},
        {"stats": {"hp_max": 10, "ac": 99}},
        {"stats": {"hp_max": 10, "abilities": {"str": 99}}},
        {"stats": {"hp_max": 10, "attacks": [{"damage": "lots"}]}},
        {"stats": {"hp_max": 10, "legendary_actions": [{"cost": 4}]}},
        {"stats": {"hp_max": 10, "legendary_actions": [{"damage": "lots"}]}},
        {"challenge_rating": "high"},
    ],
)
def test_create_entry_rejects_bad_input(mutation):
    campaign = _make_campaign(f"comp-gm-bad-{abs(hash(str(mutation))) % 10000}")
    kwargs = {
        "name": mutation.get("name", "OK Name"),
        "stat_json": mutation.get("stats", _VALID_STATS),
    }
    if "challenge_rating" in mutation:
        kwargs["challenge_rating"] = mutation["challenge_rating"]
    with pytest.raises(CombatValidationError):
        monster_compendium_service.create_entry(campaign.id, **kwargs)


def test_generate_entry_persists_seed_and_reproduces():
    campaign = _make_campaign("comp-gm-gen")
    entry = monster_compendium_service.generate_entry(
        campaign.id, raw_seed="goblin-pack", challenge=2.0
    )
    db.session.commit()
    assert entry.source == "generated"
    assert entry.generation_seed == monster_generator.derive_seed("goblin-pack")
    # Same seed reproduces identical mechanics.
    template = monster_generator.generate_monster_template(
        entry.generation_seed, 2.0
    )
    assert entry.stat_json["hp_max"] == template["hp_max"]
    assert entry.stat_json["ac"] == template["ac"]
    assert entry.name == template["name"]


# ---------------------------------------------------------------------------
# Clone to encounter (snapshot semantics)
# ---------------------------------------------------------------------------
def test_clone_to_encounter_snapshots_stats():
    campaign = _make_campaign("comp-gm-clone")
    entry = monster_compendium_service.create_entry(
        campaign.id, "Snapshot Beast", _VALID_STATS
    )
    encounter = encounter_service.create_encounter(campaign.id)
    db.session.commit()

    combatant = encounter_service.add_monster_combatant(encounter, entry, x=2, y=3)
    db.session.commit()
    assert combatant.hp_max == 20
    assert combatant.ac == 13
    assert combatant.side == "foe"
    assert combatant.compendium_entry_id == entry.id
    assert combatant.action_data_json["legendary_actions"][0]["name"] == "Tail Sweep"

    # Mutating the template later must not affect the existing combatant.
    new_stats = dict(_VALID_STATS)
    new_stats["hp_max"] = 999
    monster_compendium_service.update_entry(entry, stat_json=new_stats)
    db.session.commit()
    assert combatant.hp_max == 20


def test_clone_rejects_cross_campaign_entry():
    campaign_a = _make_campaign("comp-gm-x")
    campaign_b = _make_campaign("comp-gm-y")
    entry = monster_compendium_service.create_entry(
        campaign_b.id, "Foreign Beast", _VALID_STATS
    )
    encounter = encounter_service.create_encounter(campaign_a.id)
    db.session.commit()
    with pytest.raises(CombatValidationError):
        encounter_service.add_monster_combatant(encounter, entry)
