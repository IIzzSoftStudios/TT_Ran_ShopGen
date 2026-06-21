"""Tests for GM classes compendium API, service validation, and player class details."""

from __future__ import annotations

import pytest

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import Campaign, CampaignWorldConfig, Player, PlayerCharacterSheet, User
from app.services.character_creation.creation_service import build_final_sheet_json
from app.services.character_creation.dnd5e_catalog import merged_creation_catalog
from app.services.classes_compendium_service import (
    ClassesValidationError,
    create_class,
    ensure_classes_compendium,
    list_visible_classes,
    resolve_character_class_details,
    update_class,
)
from app.services.character_sheet_service import character_data_payload
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


def _make_gm_with_campaign(username: str = "gm-classes") -> tuple[User, Campaign]:
    user = User(username=username, password="x", role="GM")
    user.set_password("Secret1!")
    db.session.add(user)
    db.session.commit()
    ensure_gm_profile(user)
    db.session.commit()
    db.session.refresh(user)
    campaign = Campaign(
        gm_profile_id=user.gm_profile.id,
        name="Classes Camp",
        system_type="dnd5e",
        is_active=True,
        current_game_day=1,
        join_code="CAMP-CLASSES-01",
    )
    db.session.add(campaign)
    db.session.commit()
    return user, campaign


def test_ensure_classes_compendium_seeds_core_classes():
    _, campaign = _make_gm_with_campaign("gm-seed-classes")
    entries = ensure_classes_compendium(campaign.id)
    keys = {row["key"] for row in entries}
    assert "fighter" in keys
    assert "wizard" in keys
    assert all(len(row.get("level_progression") or []) == 20 for row in entries)


def test_create_class_requires_valid_progression():
    _, campaign = _make_gm_with_campaign("gm-create-class")
    with pytest.raises(ClassesValidationError):
        create_class(
            campaign.id,
            {
                "name": "Crystal Knight",
                "summary": "A custom martial class.",
                "hit_die": 10,
                "save_proficiencies": ["str", "con"],
                "skill_choices": {"count": 2, "options": ["athletics", "intimidation"]},
                "level_progression": [],
            },
        )


def test_create_and_update_custom_class():
    _, campaign = _make_gm_with_campaign("gm-update-class")
    created = create_class(
        campaign.id,
        {
            "name": "Crystal Knight",
            "summary": "A custom martial class.",
            "hit_die": 10,
            "save_proficiencies": ["str", "con"],
            "skill_choices": {"count": 2, "options": ["athletics", "intimidation"]},
            "level_progression": ensure_classes_compendium(campaign.id)[0]["level_progression"],
        },
    )
    db.session.commit()
    assert created["source"] == "custom"
    assert created["key"]

    updated = update_class(
        campaign.id,
        created["key"],
        {
            **created,
            "summary": "Updated custom martial class.",
            "level_progression": created["level_progression"],
        },
    )
    db.session.commit()
    assert updated["summary"] == "Updated custom martial class."


def test_hidden_class_omitted_from_visible_list():
    _, campaign = _make_gm_with_campaign("gm-hidden-class")
    created = create_class(
        campaign.id,
        {
            "name": "Hidden Knight",
            "summary": "Secret martial class.",
            "hit_die": 10,
            "save_proficiencies": ["str", "con"],
            "skill_choices": {"count": 2, "options": ["athletics", "intimidation"]},
            "level_progression": ensure_classes_compendium(campaign.id)[0]["level_progression"],
            "is_hidden": True,
            "visible_to_owner": False,
        },
    )
    db.session.commit()
    visible_keys = {row["key"] for row in list_visible_classes(campaign.id)}
    assert created["key"] not in visible_keys


def test_dashboard_includes_classes_compendium_for_dnd5e_campaign():
    user, campaign = _make_gm_with_campaign("gm-classes-tab")
    client = flask_app.test_client()
    seed_client_session(client, user, campaign_id=campaign.id)

    resp = client.get("/gm/")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert 'id="classes-tab-btn"' in html
    assert "Classes Compendium" in html
    assert 'id="classes-compendium-body"' in html
    assert 'id="classes-editor"' in html


def test_classes_compendium_json_updates_base_class():
    user, campaign = _make_gm_with_campaign("gm-classes-json")
    client = flask_app.test_client()
    seed_client_session(client, user, campaign_id=campaign.id)

    listed = client.get("/gm/classes/compendium")
    assert listed.status_code == 200
    fighter = next(row for row in listed.get_json()["classes"] if row["key"] == "fighter")
    progression = fighter["level_progression"]
    progression[0]["features"] = [{"name": "Custom Fighting Style", "description": "GM-authored level 1 feature."}]

    resp = client.post(
        "/gm/classes/compendium/fighter",
        json={
            "name": "Fighter",
            "summary": "Updated fighter shell.",
            "hit_die": 10,
            "save_proficiencies": ["str", "con"],
            "skill_choices": fighter["skill_choices"],
            "level_progression": progression,
            "is_hidden": False,
            "secret": False,
            "visible_to_owner": True,
            "notes": "",
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()["class"]
    assert body["summary"] == "Updated fighter shell."
    assert body["level_progression"][0]["features"][0]["name"] == "Custom Fighting Style"


def test_classes_compendium_json_creates_custom_class():
    user, campaign = _make_gm_with_campaign("gm-classes-create")
    client = flask_app.test_client()
    seed_client_session(client, user, campaign_id=campaign.id)

    base = ensure_classes_compendium(campaign.id)[0]
    resp = client.post(
        "/gm/classes/compendium",
        json={
            "name": "Star Mage",
            "summary": "Cosmic spellcaster.",
            "hit_die": 6,
            "save_proficiencies": ["int", "wis"],
            "skill_choices": {"count": 2, "options": ["arcana", "history"]},
            "level_progression": base["level_progression"],
        },
    )
    assert resp.status_code == 201
    created = resp.get_json()["class"]
    assert created["source"] == "custom"
    assert created["name"] == "Star Mage"


def test_custom_class_appears_in_merged_creation_catalog():
    _, campaign = _make_gm_with_campaign("gm-wizard-merge")
    base = ensure_classes_compendium(campaign.id)[0]
    create_class(
        campaign.id,
        {
            "name": "Star Mage",
            "summary": "Cosmic spellcaster.",
            "hit_die": 6,
            "save_proficiencies": ["int", "wis"],
            "skill_choices": {"count": 2, "options": ["arcana", "history"]},
            "level_progression": base["level_progression"],
        },
    )
    db.session.commit()
    catalog = merged_creation_catalog(classes_compendium=ensure_classes_compendium(campaign.id))
    keys = {row["key"] for row in catalog["classes"]}
    assert any(row["name"] == "Star Mage" for row in catalog["classes"])


def test_compendium_mutation_reflected_in_player_class_details():
    _, campaign = _make_gm_with_campaign("gm-live-progression")
    entries = ensure_classes_compendium(campaign.id)
    fighter = next(row for row in entries if row["key"] == "fighter")
    progression = fighter["level_progression"]
    progression[4]["features"] = [{"name": "Extra Attack", "description": "Attack twice when you take the Attack action."}]
    update_class(
        campaign.id,
        "fighter",
        {
            **fighter,
            "level_progression": progression,
        },
    )
    db.session.commit()

    catalog = merged_creation_catalog(classes_compendium=ensure_classes_compendium(campaign.id))
    sheet = build_final_sheet_json(
        {
            "name": "Live Fighter",
            "species_key": "human",
            "class_key": "fighter",
            "background_key": "soldier",
            "class_skill_choices": ["athletics", "intimidation"],
            "base_abilities": {"str": 15, "dex": 14, "con": 13, "int": 12, "wis": 10, "cha": 8},
        },
        catalog=catalog,
        settings={"ability_method": "player_set", "point_buy_budget": 27},
    )
    sheet["level"] = 5

    user = User(username="player-live", password="x", role="Player")
    user.set_password("Secret1!")
    db.session.add(user)
    db.session.commit()
    player = Player(user_id=user.id, campaign_id=campaign.id, currency=0, is_npc=False)
    db.session.add(player)
    db.session.flush()
    db.session.add(
        PlayerCharacterSheet(
            player_id=player.id,
            campaign_id=campaign.id,
            sheet_json=sheet,
        )
    )
    db.session.commit()

    details = resolve_character_class_details(
        campaign.id,
        class_key="fighter",
        level=5,
        owner_class_key="fighter",
    )
    assert details["available"] is True
    assert details["current_level_row"]["features"][0]["name"] == "Extra Attack"

    payload = character_data_payload(player, campaign)
    assert payload["class_details"]["available"] is True
    assert payload["class_details"]["current_level_row"]["features"][0]["name"] == "Extra Attack"


def test_hidden_class_not_exposed_by_name_fallback():
    _, campaign = _make_gm_with_campaign("gm-hidden-fallback")
    base = ensure_classes_compendium(campaign.id)[0]
    create_class(
        campaign.id,
        {
            "name": "Hidden Knight",
            "summary": "Secret martial class.",
            "hit_die": 10,
            "save_proficiencies": ["str", "con"],
            "skill_choices": {"count": 2, "options": ["athletics", "intimidation"]},
            "level_progression": base["level_progression"],
            "is_hidden": True,
            "visible_to_owner": False,
        },
    )
    db.session.commit()

    details = resolve_character_class_details(
        campaign.id,
        class_key=None,
        level=1,
        class_name_fallback="Hidden Knight",
        owner_class_key=None,
    )
    assert details["available"] is False


def test_sheet_stores_immutable_class_choices_not_progression_snapshot():
    catalog = merged_creation_catalog()
    sheet = build_final_sheet_json(
        {
            "name": "Immutable Fighter",
            "species_key": "human",
            "class_key": "fighter",
            "background_key": "soldier",
            "class_skill_choices": ["athletics", "intimidation"],
            "base_abilities": {"str": 15, "dex": 14, "con": 13, "int": 12, "wis": 10, "cha": 8},
        },
        catalog=catalog,
        settings={"ability_method": "player_set", "point_buy_budget": 27},
    )
    creation = sheet["creation"]
    assert creation["class_key"] == "fighter"
    assert creation.get("class_source")
    assert "level_progression" not in creation
