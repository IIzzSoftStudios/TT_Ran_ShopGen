"""Tests for player monster bestiary and GM known_to_players flag."""

from __future__ import annotations

import pytest

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import Campaign, Player, User
from app.services.combat.monster_compendium_service import create_entry, serialize_entry, update_entry
from app.services.player_monster_service import build_known_monster_entries
from app.services.user_capabilities import ensure_gm_profile
from tests.session_helpers import seed_client_session


@pytest.fixture(autouse=True)
def _db_tables():
    flask_app.config["WTF_CSRF_ENABLED"] = False
    with flask_app.app_context():
        db.create_all()
        yield
        db.session.rollback()
        db.drop_all()


def _campaign_with_player():
    user = User(username="pm-player", password="x", role="Player")
    user.set_password("Secret1!")
    db.session.add(user)
    db.session.commit()
    gm = User(username="pm-gm", password="x", role="GM")
    gm.set_password("Secret1!")
    db.session.add(gm)
    db.session.commit()
    ensure_gm_profile(gm)
    db.session.commit()
    campaign = Campaign(
        gm_profile_id=gm.gm_profile.id,
        name="pm-camp",
        system_type="dnd5e",
        is_active=True,
        current_game_day=1,
    )
    db.session.add(campaign)
    db.session.commit()
    player = Player(user_id=user.id, campaign_id=campaign.id, currency=0)
    db.session.add(player)
    db.session.commit()
    return campaign, player, user


def test_gm_known_monster_appears_in_player_list_without_journal():
    campaign, player, _ = _campaign_with_player()
    entry = create_entry(
        campaign.id,
        "Hidden Drake",
        {"hp_max": 40, "ac": 15, "speed_ft": 30, "abilities": {"str": 16, "dex": 12, "con": 14, "int": 8, "wis": 10, "cha": 6}, "attacks": []},
        challenge_rating=3,
    )
    entry.known_to_players = True
    db.session.commit()

    rows = build_known_monster_entries(campaign.id, player.id)
    assert len(rows) == 1
    assert rows[0]["name"] == "Hidden Drake"
    assert rows[0]["gm_known"] is True
    assert rows[0]["in_journal"] is False


def test_discover_monster_creates_blank_journal():
    campaign, player, user = _campaign_with_player()
    entry = create_entry(
        campaign.id,
        "Cave Spider",
        {"hp_max": 22, "ac": 13, "speed_ft": 30, "abilities": {"str": 10, "dex": 16, "con": 12, "int": 2, "wis": 10, "cha": 2}, "attacks": []},
        challenge_rating=0.5,
    )
    db.session.commit()

    client = flask_app.test_client()
    seed_client_session(client, user, campaign_id=campaign.id, player_id=player.id, session_mode="player")

    blocked = client.get(f"/player/monsters/{entry.id}/profile")
    assert blocked.status_code == 404

    discover = client.post(
        "/player/monsters/discover",
        json={"monster_entry_id": entry.id},
        headers={"Content-Type": "application/json"},
    )
    assert discover.status_code == 200
    body = discover.get_json()
    assert body["ok"] is True
    assert body["monster"]["in_journal"] is True
    assert body["monster"]["stats"]["attacks"] == []

    profile = client.get(f"/player/monsters/{entry.id}/profile").get_json()
    assert profile["monster"]["name"] == "Cave Spider"

    save = client.post(
        f"/player/monsters/{entry.id}/journal",
        json={"stats": {"hp_max": 20, "ac": 14, "notes": "Very fast"}},
        headers={"Content-Type": "application/json"},
    )
    assert save.status_code == 200
    assert save.get_json()["monster"]["stats"]["hp_max"] == 20
    assert save.get_json()["monster"]["stats"]["notes"] == "Very fast"


def test_update_monster_persists_known_to_players():
    campaign, _, _ = _campaign_with_player()
    entry = create_entry(
        campaign.id,
        "Test Ooze",
        {"hp_max": 10, "ac": 8, "speed_ft": 20, "abilities": {"str": 12, "dex": 6, "con": 16, "int": 1, "wis": 6, "cha": 2}, "attacks": []},
    )
    db.session.commit()
    update_entry(entry, known_to_players=True)
    db.session.commit()
    data = serialize_entry(entry)
    assert data["known_to_players"] is True


def test_player_combatant_includes_compendium_entry_id_for_foes():
    from app.models import BattleCombatant, BattleEncounter
    from app.services.combat.serializers import serialize_combatant

    campaign, player, _ = _campaign_with_player()
    entry = create_entry(
        campaign.id,
        "Goblin",
        {"hp_max": 7, "ac": 15, "speed_ft": 30, "abilities": {"str": 8, "dex": 14, "con": 10, "int": 10, "wis": 8, "cha": 8}, "attacks": []},
    )
    db.session.flush()
    encounter = BattleEncounter(campaign_id=campaign.id, name="Test", status="active")
    db.session.add(encounter)
    db.session.flush()
    foe = BattleCombatant(
        encounter_id=encounter.id,
        campaign_id=campaign.id,
        name="Goblin",
        side="foe",
        status="active",
        x=0,
        y=0,
        hp_max=7,
        hp_current=7,
        temp_hp=0,
        ac=15,
        speed_ft=30,
        dex_mod=2,
        compendium_entry_id=entry.id,
        action_data_json={"attacks": []},
        resources_json={},
        conditions_json=[],
    )
    db.session.add(foe)
    db.session.commit()

    payload = serialize_combatant(foe, for_gm=False, viewer_player_id=player.id)
    assert payload["compendium_entry_id"] == entry.id
    assert "hp_current" not in payload
