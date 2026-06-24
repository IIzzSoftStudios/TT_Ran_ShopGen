"""Tests for D&D 5e character creation wizard, settings, and vault join continuity."""

from __future__ import annotations

import json

import pytest

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import Campaign, CampaignWorldConfig, Player, PlayerCharacterSheet, Region, User
from app.services.character_creation.campaign_settings import get_creation_settings
from app.services.character_creation.creation_service import (
    build_final_sheet_json,
    point_buy_spend,
)
from app.services import character_sheet_service
from app.services.join_codes import redeem_campaign_code
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


def _make_user(username: str, role: str = "Both") -> User:
    u = User(username=username, password="x", role=role)
    u.set_password("Secret1!")
    db.session.add(u)
    db.session.commit()
    return u


def _make_dnd_campaign(gm_user: User, name: str = "DnD Camp") -> Campaign:
    ensure_gm_profile(gm_user)
    db.session.commit()
    db.session.refresh(gm_user)
    camp = Campaign(
        gm_profile_id=gm_user.gm_profile.id,
        name=name,
        system_type="dnd5e",
        is_active=True,
        current_game_day=1,
        join_code="CAMP-TEST-0001",
    )
    db.session.add(camp)
    db.session.commit()
    return camp


def _valid_wizard_payload(**overrides):
    base = {
        "name": "Aldric",
        "species_key": "human",
        "class_key": "fighter",
        "background_key": "soldier",
        "class_skill_choices": ["athletics", "intimidation"],
        "base_abilities": {
            "str": 15,
            "dex": 14,
            "con": 13,
            "int": 12,
            "wis": 10,
            "cha": 8,
        },
    }
    base.update(overrides)
    return base


def test_create_character_get_includes_dnd5e_wizard(client):
    with flask_app.app_context():
        user = _make_user("wizard-get")
        seed_client_session(client, user)
        resp = client.get("/player/character/create")
        assert resp.status_code == 200
        body = resp.data
        assert b"id=\"dnd5e-wizard\"" in body
        assert b"character_create_wizard.js" in body
        assert b"DND5E_WIZARD_CONFIG" in body
        assert b'"back_url": "/campaigns"' in body
        assert b'id="wizard-back">Back to campaign menu</button>' in body
        assert b'id="wizard-exit-modal"' in body
        assert b"Leave character creation?" in body
        assert b"Any choices you made in this wizard will not be saved." in body
        assert b".modal-backdrop[hidden]" in body
        assert b".actions-row[hidden]" in body
        assert b".skill-choice input[type=\"checkbox\"]" in body
        assert b".selection-badge" in body
        assert b"id=\"background-modal\"" in body
        assert b"Accept background" in body
        assert b"species-trait-list" in body
        assert b"species-modal-choices" in body
        assert b'"traits"' in body


def test_point_buy_spend_table():
    assert point_buy_spend({"str": 8, "dex": 8, "con": 8, "int": 8, "wis": 8, "cha": 8}) == 0
    assert point_buy_spend({"str": 15, "dex": 8, "con": 8, "int": 8, "wis": 8, "cha": 8}) == 9


def test_campaign_redeem_redirects_dnd5e_player_to_wizard(client):
    with flask_app.app_context():
        gm = _make_user("gm-redeem-wizard", role="GM")
        player_user = _make_user("redeem-wizard-player", role="Player")
        camp = _make_dnd_campaign(gm, name="Wizard Camp")
        seed_client_session(client, player_user)

        resp = client.post(
            "/campaigns/redeem",
            data={"campaign_code": camp.join_code},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)
        player = Player.query.filter_by(
            user_id=player_user.id,
            campaign_id=camp.id,
            is_npc=False,
        ).one()
        assert f"/player/character/create?campaign_player_id={player.id}" in resp.location
        with client.session_transaction() as sess:
            assert sess.get("player_id") == player.id
            assert sess.get("campaign_id") == camp.id


def test_dnd5e_finalize_updates_campaign_player_sheet(client):
    with flask_app.app_context():
        gm = _make_user("gm-camp-final", role="GM")
        player_user = _make_user("camp-final-player", role="Player")
        camp = _make_dnd_campaign(gm, name="Finalize Camp")
        seed_client_session(client, player_user)

        redeem = client.post(
            "/campaigns/redeem",
            data={"campaign_code": camp.join_code},
            follow_redirects=False,
        )
        assert redeem.status_code in (302, 303)
        player = Player.query.filter_by(
            user_id=player_user.id,
            campaign_id=camp.id,
            is_npc=False,
        ).one()

        payload = _valid_wizard_payload()
        resp = client.post(
            "/player/character/create/dnd5e/finalize",
            data=json.dumps({**payload, "campaign_player_id": player.id}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        sheet = PlayerCharacterSheet.query.filter_by(
            player_id=player.id, campaign_id=camp.id
        ).one()
        assert sheet.sheet_json["name"] == "Aldric"
        assert sheet.sheet_json["species"] == "Human"
        assert sheet.sheet_json["class_name"] == "Fighter"


def test_non_dnd5e_create_still_instant(client):
    with flask_app.app_context():
        user = _make_user("generic-create")
        seed_client_session(client, user)
        resp = client.post(
            "/player/character/create",
            data={"system_type": "generic", "name": "Quick"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)
        player = Player.query.filter_by(user_id=user.id).one()
        sheet = PlayerCharacterSheet.query.filter_by(
            player_id=player.id, campaign_id=None
        ).one()
        assert sheet.sheet_json["system_type"] == "generic"
        assert sheet.sheet_json["name"] == "Quick"


def test_dnd5e_finalize_creates_player_and_sheet(client):
    with flask_app.app_context():
        user = _make_user("wizard-final")
        seed_client_session(client, user)
        payload = _valid_wizard_payload()
        resp = client.post(
            "/player/character/create/dnd5e/finalize",
            data=json.dumps({**payload, "draft_token": "tok-1"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        player = Player.query.filter_by(user_id=user.id).one()
        sheet = PlayerCharacterSheet.query.filter_by(
            player_id=player.id, campaign_id=None
        ).one()
        assert sheet.sheet_json["species"] == "Human"
        assert sheet.sheet_json["class_name"] == "Fighter"
        assert sheet.sheet_json["level"] == 1
        assert sheet.sheet_json["abilities"]["str"] == 16
        assert sheet.sheet_json["creation"]["ability_method"] == "point_buy"


def test_dnd5e_finalize_idempotent_with_same_draft_token(client):
    with flask_app.app_context():
        user = _make_user("wizard-idem")
        seed_client_session(client, user)
        payload = {**_valid_wizard_payload(), "draft_token": "same-token"}
        first = client.post(
            "/player/character/create/dnd5e/finalize",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert first.status_code == 200
        second = client.post(
            "/player/character/create/dnd5e/finalize",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert second.status_code == 200
        assert Player.query.filter_by(user_id=user.id, is_npc=False).count() == 1


def test_dnd5e_finalize_rejects_invalid_species(client):
    with flask_app.app_context():
        user = _make_user("wizard-bad-species")
        seed_client_session(client, user)
        payload = _valid_wizard_payload(species_key="not-a-species")
        resp = client.post(
            "/player/character/create/dnd5e/finalize",
            data=json.dumps({**payload, "draft_token": "bad"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert Player.query.filter_by(user_id=user.id).count() == 0


def test_point_buy_budget_enforced(client):
    with flask_app.app_context():
        user = _make_user("wizard-budget")
        seed_client_session(client, user)
        payload = _valid_wizard_payload(
            base_abilities={
                "str": 15,
                "dex": 15,
                "con": 15,
                "int": 15,
                "wis": 15,
                "cha": 15,
            }
        )
        resp = client.post(
            "/player/character/create/dnd5e/finalize",
            data=json.dumps({**payload, "draft_token": "over"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert "budget" in body["errors"][0].lower()


def test_random_roll_endpoint_and_finalize(client, monkeypatch):
    from app.services.character_creation.campaign_settings import (
        solo_default_creation_settings,
    )

    def _random_solo():
        out = solo_default_creation_settings()
        out["ability_method"] = "random_roll"
        return out

    def _random_catalog(**kwargs):
        from app.services.character_creation.dnd5e_catalog import (
            merged_creation_catalog as _merge,
        )

        return {
            "settings": _random_solo(),
            "catalog": _merge(),
            "point_buy_costs": {},
            "point_buy_range": {"min": 8, "max": 15},
        }

    monkeypatch.setattr(
        "app.services.character_creation.creation_service.solo_default_creation_settings",
        _random_solo,
    )
    monkeypatch.setattr(
        "app.services.character_creation.creation_service.wizard_catalog_for_user",
        _random_catalog,
    )

    with flask_app.app_context():
        user = _make_user("wizard-roll")
        seed_client_session(client, user)
        for ab in ("str", "dex", "con", "int", "wis", "cha"):
            roll_resp = client.post(
                "/player/character/create/dnd5e/roll",
                data=json.dumps({"ability_key": ab, "reroll": False}),
                content_type="application/json",
            )
            assert roll_resp.status_code == 200, roll_resp.get_json()

        payload = _valid_wizard_payload()
        payload.pop("base_abilities", None)
        resp = client.post(
            "/player/character/create/dnd5e/finalize",
            data=json.dumps({**payload, "draft_token": "roll-final"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        player = Player.query.filter_by(user_id=user.id).one()
        sheet = PlayerCharacterSheet.query.filter_by(
            player_id=player.id, campaign_id=None
        ).one()
        assert sheet.sheet_json["creation"]["ability_method"] == "random_roll"
        assert sheet.sheet_json["creation"]["ability_rolls"]


def test_random_roll_finalize_requires_draft(client, monkeypatch):
    from app.services.character_creation.campaign_settings import (
        solo_default_creation_settings,
    )

    def _random_solo():
        out = solo_default_creation_settings()
        out["ability_method"] = "random_roll"
        return out

    monkeypatch.setattr(
        "app.services.character_creation.creation_service.solo_default_creation_settings",
        _random_solo,
    )

    with flask_app.app_context():
        user = _make_user("wizard-roll-missing")
        seed_client_session(client, user)
        payload = _valid_wizard_payload()
        payload.pop("base_abilities", None)
        resp = client.post(
            "/player/character/create/dnd5e/finalize",
            data=json.dumps({**payload, "draft_token": "no-roll"}),
            content_type="application/json",
        )
        assert resp.status_code == 400


def test_gm_character_creation_settings_persist(client):
    with flask_app.app_context():
        gm = _make_user("gm-settings", role="GM")
        camp = _make_dnd_campaign(gm)
        seed_client_session(
            client,
            gm,
            session_mode="gm",
            campaign_id=camp.id,
            system_type="dnd5e",
        )
        resp = client.post(
            "/gm/character-creation/settings",
            data=json.dumps(
                {
                    "ability_method": "random_roll",
                    "point_buy_budget": 30,
                    "random_rerolls_per_ability": 2,
                    "max_player_level": 12,
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 200
        cfg = CampaignWorldConfig.query.filter_by(campaign_id=camp.id).one()
        stored = cfg.settings_json["character_creation"]
        assert stored["ability_method"] == "random_roll"
        assert stored["random_rerolls_per_ability"] == 2
        assert stored["max_player_level"] == 12


def test_gm_home_shows_species_compendium_without_character_options_tab(client):
    with flask_app.app_context():
        gm = _make_user("gm-char-opt", role="GM")
        camp = _make_dnd_campaign(gm)
        seed_client_session(
            client,
            gm,
            session_mode="gm",
            campaign_id=camp.id,
            system_type="dnd5e",
        )
        resp = client.get("/gm/")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert 'id="character-options-tab-btn"' not in html
        assert 'id="character-options-pane-content"' not in html
        assert 'id="species-tab-btn"' in html
        assert 'id="species-add-btn"' in html
        assert 'id="char-creation-controls"' in html
        assert 'id="char-creation-max-level"' in html


def test_vault_sheet_copied_on_campaign_join(client):
    with flask_app.app_context():
        gm = _make_user("gm-join", role="GM")
        player_user = _make_user("join-player", role="Player")
        camp = _make_dnd_campaign(gm)

        solo = Player(user_id=player_user.id, campaign_id=None, currency=0, is_npc=False)
        db.session.add(solo)
        db.session.flush()
        db.session.add(
            PlayerCharacterSheet(
                player_id=solo.id,
                campaign_id=None,
                sheet_json={
                    "schema_version": 1,
                    "system_type": "dnd5e",
                    "name": "Vault Hero",
                    "species": "Human",
                    "class_name": "Fighter",
                    "level": 1,
                    "abilities": {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 10, "cha": 8},
                    "defenses": {},
                    "save_prof_flags": {},
                    "skill_prof_tiers": {},
                },
            )
        )
        db.session.commit()

        redeem_campaign_code(player_user, camp.join_code, player_id=solo.id)
        campaign_sheet = PlayerCharacterSheet.query.filter_by(
            player_id=solo.id, campaign_id=camp.id
        ).one()
        assert campaign_sheet.sheet_json["name"] == "Vault Hero"
        vault_sheet = PlayerCharacterSheet.query.filter_by(
            player_id=solo.id, campaign_id=None
        ).one()
        assert vault_sheet.sheet_json["name"] == "Vault Hero"


def test_build_final_sheet_applies_species_after_point_buy():
    from app.services.character_creation.dnd5e_catalog import merged_creation_catalog as catalog_merge

    catalog = catalog_merge()
    settings = {
        "ability_method": "point_buy",
        "point_buy_budget": 27,
        "settings_version": "test",
    }
    sheet = build_final_sheet_json(
        _valid_wizard_payload(),
        catalog=catalog,
        settings=settings,
    )
    assert sheet["abilities"]["str"] == 16
    assert sheet["creation"]["base_abilities"]["str"] == 15
    assert sheet["traits"]
    assert sheet["creation"]["trait_keys"] == ["speed-30", "size-medium"]


def test_build_final_sheet_elf_grants_perception_and_traits():
    from app.services.character_creation.dnd5e_catalog import merged_creation_catalog as catalog_merge

    catalog = catalog_merge()
    settings = {
        "ability_method": "point_buy",
        "point_buy_budget": 27,
        "settings_version": "test",
    }
    sheet = build_final_sheet_json(
        _valid_wizard_payload(species_key="elf"),
        catalog=catalog,
        settings=settings,
    )
    assert any(t.get("name") == "Keen Senses" for t in sheet["traits"])
    assert sheet["skill_prof_tiers"]["perception"] == 2
    assert "darkvision-60" in sheet["creation"]["trait_keys"]


def test_build_final_sheet_half_elf_requires_species_skills():
    from app.services.character_creation.dnd5e_catalog import merged_creation_catalog as catalog_merge

    catalog = catalog_merge()
    settings = {
        "ability_method": "point_buy",
        "point_buy_budget": 27,
        "settings_version": "test",
    }
    with pytest.raises(Exception):
        build_final_sheet_json(
            _valid_wizard_payload(
                species_key="half-elf",
                species_flex_assignments={"int": 1, "wis": 1},
            ),
            catalog=catalog,
            settings=settings,
        )


def test_merged_catalog_exposes_srd_species_traits():
    from app.services.character_creation.dnd5e_catalog import merged_creation_catalog as catalog_merge

    catalog = catalog_merge()
    dwarf = next(row for row in catalog["species"] if row["key"] == "dwarf")
    assert dwarf["traits"]
    assert dwarf["trait_keys"]
    assert dwarf["stat_modifiers"]


def test_custom_class_with_any_skill_options_finalizes_immutable_choices():
    from app.services.classes_compendium_service import create_class, ensure_classes_compendium
    from app.services.character_creation.dnd5e_catalog import merged_creation_catalog

    gm = _make_user("gm-any-class", role="GM")
    camp = _make_dnd_campaign(gm)
    base = ensure_classes_compendium(camp.id)[0]
    create_class(
        camp.id,
        {
            "name": "Lore Bard",
            "summary": "Custom bard shell.",
            "hit_die": 8,
            "save_proficiencies": ["dex", "cha"],
            "skill_choices": {"count": 3, "options": "any"},
            "level_progression": base["level_progression"],
        },
    )
    db.session.commit()

    catalog = merged_creation_catalog(classes_compendium=ensure_classes_compendium(camp.id))
    custom = next(row for row in catalog["classes"] if row["name"] == "Lore Bard")
    sheet = build_final_sheet_json(
        _valid_wizard_payload(
            class_key=custom["key"],
            class_skill_choices=["arcana", "history", "performance"],
        ),
        catalog=catalog,
        settings=get_creation_settings(camp.id),
    )
    assert sheet["creation"]["class_key"] == custom["key"]
    assert sheet["creation"]["class_source"] == "custom"
    assert "level_progression" not in sheet["creation"]
    assert sheet["creation"]["class_skill_choices"] == ["arcana", "history", "performance"]


def test_solo_defaults_never_use_campaign_settings():
    solo = get_creation_settings(None)
    assert solo["scope"] == "solo"
    assert solo["point_buy_budget"] == 27


def test_build_final_sheet_uncapped_accepts_high_abilities():
    from app.services.character_creation.dnd5e_catalog import merged_creation_catalog as catalog_merge

    catalog = catalog_merge()
    settings = get_creation_settings(None)
    payload = _valid_wizard_payload(
        base_abilities={
            "str": 22,
            "dex": 18,
            "con": 20,
            "int": 14,
            "wis": 12,
            "cha": 10,
        }
    )
    sheet = build_final_sheet_json(
        payload,
        catalog=catalog,
        settings=settings,
        uncapped=True,
    )
    assert sheet["creation"]["base_abilities"]["str"] == 22
    assert sheet["abilities"]["str"] == 23  # human +1 to all


def test_dragonborn_finalize_stores_ancestry_and_resist_trait():
    from app.services.character_creation.dnd5e_catalog import merged_creation_catalog as catalog_merge

    catalog = catalog_merge()
    settings = get_creation_settings(None)
    sheet = build_final_sheet_json(
        _valid_wizard_payload(
            species_key="dragonborn",
            dragonborn_ancestry="fire",
        ),
        catalog=catalog,
        settings=settings,
    )
    creation = sheet["creation"]
    assert creation["dragonborn_ancestry"] == "fire"
    assert "fire" in (creation.get("dragonborn_breath_summary") or "").lower()
    assert "resist-fire" in creation["trait_keys"]


def test_gm_create_npc_get_shows_dnd5e_wizard(client):
    with flask_app.app_context():
        gm = _make_user("gm-npc-wizard", role="GM")
        camp = _make_dnd_campaign(gm)
        seed_client_session(client, gm, campaign_id=camp.id, session_mode="gm")
        resp = client.get("/gm/npcs/create")
        assert resp.status_code == 200
        body = resp.data
        assert b"id=\"dnd5e-wizard\"" in body
        assert b"character_create_wizard.js" in body
        assert b'"gm_npc_mode": true' in body or b'"gm_npc_mode":true' in body
        assert b"Create NPC" in body


def test_gm_create_npc_dnd5e_finalize_creates_npc_with_high_abilities(client):
    with flask_app.app_context():
        gm = _make_user("gm-npc-finalize", role="GM")
        camp = _make_dnd_campaign(gm)
        seed_client_session(client, gm, campaign_id=camp.id, session_mode="gm")
        payload = _valid_wizard_payload(
            name="Ancient Dragon Knight",
            base_abilities={
                "str": 24,
                "dex": 14,
                "con": 22,
                "int": 10,
                "wis": 12,
                "cha": 16,
            },
        )
        resp = client.post(
            "/gm/npcs/create/dnd5e/finalize",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        player = Player.query.get(data["player_id"])
        assert player is not None
        assert player.is_npc is True
        sheet = PlayerCharacterSheet.query.filter_by(
            player_id=player.id, campaign_id=camp.id
        ).one()
        assert sheet.sheet_json["name"] == "Ancient Dragon Knight"
        assert sheet.sheet_json["creation"]["base_abilities"]["str"] == 24
        assert sheet.sheet_json["abilities"]["str"] == 25  # human +1 to all
        assert sheet.sheet_json["creation"]["ability_method"] == "gm_set"


def test_gm_create_ruler_npc_assigns_region_and_redirects_to_edit(client):
    with flask_app.app_context():
        gm = _make_user("gm-ruler-npc", role="GM")
        camp = _make_dnd_campaign(gm)
        region = Region(campaign_id=camp.id, name="Northreach")
        db.session.add(region)
        db.session.commit()
        seed_client_session(client, gm, campaign_id=camp.id, session_mode="gm")
        payload = _valid_wizard_payload(name="Queen Aria")
        payload["region_id"] = region.id
        payload["assign_ruler"] = True
        resp = client.post(
            "/gm/npcs/create/dnd5e/finalize",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        db.session.refresh(region)
        assert region.ruler_player_id == data["player_id"]
        assert f"/gm/regions/edit/{region.id}" in data["redirect_url"]


def test_apply_sheet_update_npc_keeps_high_abilities():
    gm = _make_user("gm-npc-sheet", role="GM")
    camp = _make_dnd_campaign(gm)
    player = Player(is_npc=True, user_id=None, campaign_id=camp.id, currency=0)
    db.session.add(player)
    db.session.flush()
    db.session.add(
        PlayerCharacterSheet(
            player_id=player.id,
            campaign_id=camp.id,
            sheet_json={
                "schema_version": 1,
                "system_type": "dnd5e",
                "name": "Boss NPC",
                "abilities": {"str": 24, "dex": 14, "con": 20, "int": 10, "wis": 12, "cha": 8},
                "defenses": {},
                "save_prof_flags": {},
                "skill_prof_tiers": {},
            },
        )
    )
    db.session.commit()

    ok, errors = character_sheet_service.apply_sheet_update(
        player=player,
        campaign=camp,
        form={"stat_ability_str": "50", "stat_ability_dex": "18"},
    )
    assert ok is True
    assert not errors
    updated = PlayerCharacterSheet.query.filter_by(
        player_id=player.id, campaign_id=camp.id
    ).one()
    assert updated.sheet_json["abilities"]["str"] == 50
