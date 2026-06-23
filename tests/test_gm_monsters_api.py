"""Tests for SRD monster catalog seeding and combat API."""

from __future__ import annotations

import pytest

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import Campaign, MonsterCompendiumEntry, User
from app.services.character_creation.dnd5e_monsters import CORE_MONSTERS
from app.services.combat.monster_catalog_service import ensure_srd_monsters_for_campaign
from app.services.combat.srd_monster_manifest import SRD_MONSTER_COUNT
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


def _make_gm_with_campaign(username: str) -> tuple[User, Campaign]:
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
    return user, campaign


def test_core_monsters_matches_manifest():
    assert len(CORE_MONSTERS) == SRD_MONSTER_COUNT == 200


def test_ensure_srd_monsters_idempotent_and_preserves_gm_edits():
    _, campaign = _make_gm_with_campaign("srd-mon-gm")
    first = ensure_srd_monsters_for_campaign(campaign.id)
    db.session.commit()
    assert first["inserted"] == SRD_MONSTER_COUNT
    assert first["updated"] == 0

    goblin = MonsterCompendiumEntry.query.filter_by(
        campaign_id=campaign.id, origin_srd_key="goblin"
    ).one()
    assert goblin.name == "Goblin"
    assert goblin.source == "srd_5_1"
    assert goblin.challenge_rating == 0.25
    assert goblin.stat_json["hp_max"] == 7
    assert goblin.stat_json["attacks"][0]["damage"] == "1d6+2"

    stats = dict(goblin.stat_json)
    stats["hp_max"] = 99
    stats["gm_edited"] = True
    goblin.stat_json = stats
    db.session.commit()

    second = ensure_srd_monsters_for_campaign(campaign.id)
    db.session.commit()
    assert second["inserted"] == 0
    assert second["updated"] == SRD_MONSTER_COUNT - 1
    assert second["skipped"] == 1
    db.session.refresh(goblin)
    assert goblin.stat_json["hp_max"] == 99

    third = ensure_srd_monsters_for_campaign(campaign.id)
    db.session.commit()
    assert third["inserted"] == 0
    assert third["skipped"] == 1


def test_seed_srd_monsters_api():
    user, campaign = _make_gm_with_campaign("srd-mon-api")
    client = flask_app.test_client()
    seed_client_session(client, user, campaign_id=campaign.id, session_mode="gm")

    resp = client.post("/api/combat/monsters/srd/seed")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["counts"]["inserted"] == SRD_MONSTER_COUNT

    resp2 = client.post("/api/combat/monsters/srd/seed")
    assert resp2.status_code == 200
    assert resp2.get_json()["counts"]["inserted"] == 0

    listed = client.get("/api/combat/monsters")
    assert listed.status_code == 200
    monsters = listed.get_json()["monsters"]
    assert len(monsters) == SRD_MONSTER_COUNT
    assert any(m["name"] == "Goblin" and m["source"] == "srd_5_1" for m in monsters)


def test_list_monsters_auto_seeds_srd_without_manual_import():
    user, campaign = _make_gm_with_campaign("srd-mon-list")
    client = flask_app.test_client()
    seed_client_session(client, user, campaign_id=campaign.id, session_mode="gm")

    assert MonsterCompendiumEntry.query.filter_by(campaign_id=campaign.id).count() == 0

    listed = client.get("/api/combat/monsters")
    assert listed.status_code == 200
    monsters = listed.get_json()["monsters"]
    assert len(monsters) == SRD_MONSTER_COUNT
    assert MonsterCompendiumEntry.query.filter_by(campaign_id=campaign.id).count() == SRD_MONSTER_COUNT


def test_skip_world_generation_seeds_srd_monsters_for_dnd5e():
    user = User(username="srd-skip-gm", password="x", role="GM")
    user.set_password("Secret1!")
    db.session.add(user)
    db.session.commit()
    ensure_gm_profile(user)
    db.session.commit()

    client = flask_app.test_client()
    seed_client_session(client, user)
    resp = client.post(
        "/gm/generate_world/skip",
        data={"campaign_name": "SRD Skip Camp", "system_type": "dnd5e"},
    )
    assert resp.status_code in (302, 303)
    campaign = Campaign.query.filter_by(name="SRD Skip Camp").one()
    assert (
        MonsterCompendiumEntry.query.filter_by(campaign_id=campaign.id).count()
        == SRD_MONSTER_COUNT
    )
