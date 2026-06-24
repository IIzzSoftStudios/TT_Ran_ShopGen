"""Tests for SRD level up / level down on character sheets."""

from __future__ import annotations

import pytest

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import Campaign, Player, PlayerCharacterSheet, User
from app.services.character_creation.creation_service import build_final_sheet_json
from app.services.character_creation.dnd5e_catalog import merged_creation_catalog
from app.services.character_creation.level_progression_service import (
    _con_mod,
    apply_level_down,
    apply_level_up,
    preview_level_up,
    srd_average_hit_die_gain,
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


def _campaign_and_player() -> tuple[Campaign, Player]:
    gm = User(username="gm-level", password="x", role="GM")
    gm.set_password("Secret1!")
    db.session.add(gm)
    db.session.commit()
    ensure_gm_profile(gm)
    db.session.commit()
    campaign = Campaign(
        gm_profile_id=gm.gm_profile.id,
        name="Level Camp",
        system_type="dnd5e",
        is_active=True,
        current_game_day=1,
        join_code="CAMP-LEVEL-01",
    )
    db.session.add(campaign)
    db.session.commit()
    ensure_classes_compendium(campaign.id)

    user = User(username="player-level", password="x", role="Player")
    user.set_password("Secret1!")
    db.session.add(user)
    db.session.commit()
    player = Player(user_id=user.id, campaign_id=campaign.id, currency=0, is_npc=False)
    db.session.add(player)
    db.session.flush()

    catalog = merged_creation_catalog(classes_compendium=ensure_classes_compendium(campaign.id))
    sheet = build_final_sheet_json(
        {
            "name": "Test Fighter",
            "species_key": "human",
            "class_key": "fighter",
            "background_key": "soldier",
            "class_skill_choices": ["athletics", "intimidation"],
            "base_abilities": {"str": 15, "dex": 14, "con": 13, "int": 12, "wis": 10, "cha": 8},
        },
        catalog=catalog,
        settings={"ability_method": "player_set", "point_buy_budget": 27},
    )
    db.session.add(
        PlayerCharacterSheet(
            player_id=player.id,
            campaign_id=campaign.id,
            sheet_json=sheet,
        )
    )
    db.session.commit()
    return campaign, player


def test_srd_average_hit_die_gain():
    assert srd_average_hit_die_gain(10, 1) == 7
    assert srd_average_hit_die_gain(8, -1) == 4


def test_level_up_applies_hp_and_increments_level():
    campaign, player = _campaign_and_player()
    row = PlayerCharacterSheet.query.filter_by(
        player_id=player.id, campaign_id=campaign.id
    ).first()
    start_hp = row.sheet_json["defenses"]["hp_max"]
    assert row.sheet_json["level"] == 1
    expected_gain = srd_average_hit_die_gain(10, _con_mod(row.sheet_json))

    ok, messages, summary = apply_level_up(player, campaign)
    assert ok is True
    assert summary is not None
    assert any("Advanced to level 2" in msg for msg in messages)
    assert any("Hit points increased" in msg for msg in messages)

    db.session.refresh(row)
    assert row.sheet_json["level"] == 2
    assert row.sheet_json["defenses"]["hp_max"] == start_hp + expected_gain
    assert len(row.sheet_json.get("level_ledger") or []) == 1


def test_level_down_reverses_last_level_up():
    campaign, player = _campaign_and_player()
    row = PlayerCharacterSheet.query.filter_by(
        player_id=player.id, campaign_id=campaign.id
    ).first()
    start_hp = row.sheet_json["defenses"]["hp_max"]
    expected_gain = srd_average_hit_die_gain(10, _con_mod(row.sheet_json))
    apply_level_up(player, campaign)
    db.session.refresh(row)
    hp_at_two = row.sheet_json["defenses"]["hp_max"]
    assert hp_at_two == start_hp + expected_gain

    ok, messages = apply_level_down(player, campaign)
    assert ok is True
    assert any("Returned to level 1" in msg for msg in messages)

    db.session.refresh(row)
    assert row.sheet_json["level"] == 1
    assert row.sheet_json["defenses"]["hp_max"] == hp_at_two - expected_gain
    assert row.sheet_json.get("level_ledger") == []


def test_level_up_blocked_at_twenty():
    from sqlalchemy.orm.attributes import flag_modified

    campaign, player = _campaign_and_player()
    row = PlayerCharacterSheet.query.filter_by(
        player_id=player.id, campaign_id=campaign.id
    ).first()
    sheet = dict(row.sheet_json)
    sheet["level"] = 20
    row.sheet_json = sheet
    flag_modified(row, "sheet_json")
    db.session.commit()

    ok, messages, _summary = apply_level_up(player, campaign)
    assert ok is False
    assert any("maximum level" in msg.lower() for msg in messages)


def test_level_down_blocked_at_one():
    campaign, player = _campaign_and_player()
    ok, messages = apply_level_down(player, campaign)
    assert ok is False
    assert any("level 1" in msg.lower() for msg in messages)


def test_preview_level_up_includes_asi_at_level_four():
    campaign, player = _campaign_and_player()
    row = PlayerCharacterSheet.query.filter_by(
        player_id=player.id, campaign_id=campaign.id
    ).first()
    sheet = dict(row.sheet_json)
    sheet["level"] = 3
    row.sheet_json = sheet
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(row, "sheet_json")
    db.session.commit()

    preview = preview_level_up(player, campaign)
    assert preview["available"] is True
    assert preview["next_level"] == 4
    assert any(
        choice.get("type") == "ability_scores" for choice in preview.get("player_choices") or []
    )

    ok, _messages, summary = apply_level_up(player, campaign)
    assert ok is True
    assert summary is not None
    assert any(
        choice.get("type") == "ability_scores" for choice in summary.get("player_choices") or []
    )


def _warlock_player(campaign) -> Player:
    user = User(username="player-warlock", password="x", role="Player")
    user.set_password("Secret1!")
    db.session.add(user)
    db.session.commit()
    player = Player(user_id=user.id, campaign_id=campaign.id, currency=0, is_npc=False)
    db.session.add(player)
    db.session.flush()
    catalog = merged_creation_catalog(classes_compendium=ensure_classes_compendium(campaign.id))
    sheet = build_final_sheet_json(
        {
            "name": "Test Warlock",
            "species_key": "human",
            "class_key": "warlock",
            "background_key": "soldier",
            "class_skill_choices": ["arcana", "deception"],
            "base_abilities": {"str": 8, "dex": 14, "con": 14, "int": 12, "wis": 10, "cha": 16},
        },
        catalog=catalog,
        settings={"ability_method": "player_set", "point_buy_budget": 27},
    )
    db.session.add(
        PlayerCharacterSheet(
            player_id=player.id,
            campaign_id=campaign.id,
            sheet_json=sheet,
        )
    )
    db.session.commit()
    return player


def test_apply_ability_score_improvement_updates_sheet():
    from app.services.character_creation.level_progression_service import (
        apply_ability_score_improvement,
        apply_level_up,
    )

    campaign, player = _campaign_and_player()
    row = PlayerCharacterSheet.query.filter_by(
        player_id=player.id, campaign_id=campaign.id
    ).first()
    sheet = dict(row.sheet_json)
    sheet["level"] = 3
    row.sheet_json = sheet
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(row, "sheet_json")
    db.session.commit()

    ok, _messages, _summary = apply_level_up(player, campaign)
    assert ok is True
    db.session.refresh(row)
    assert row.sheet_json["level"] == 4
    start_str = row.sheet_json["abilities"]["str"]
    assert any(
        choice.get("type") == "ability_scores"
        for choice in (row.sheet_json.get("pending_level_choices") or [])
    )

    ok, message = apply_ability_score_improvement(
        player,
        campaign,
        level=4,
        increases={"str": 2},
    )
    assert ok is True
    assert "updated" in message.lower()
    db.session.refresh(row)
    assert row.sheet_json["abilities"]["str"] == start_str + 2
    assert not any(
        choice.get("type") == "ability_scores" and not choice.get("skipped")
        for choice in (row.sheet_json.get("pending_level_choices") or [])
    )


def test_level_up_summary_needs_wizard_only_when_choices_exist():
    from app.services.character_creation.level_progression_service import (
        enrich_level_up_summary_for_wizard,
        level_up_summary_needs_wizard,
    )

    campaign, player = _campaign_and_player()
    ok, _messages, summary = apply_level_up(player, campaign)
    assert ok is True
    enriched = enrich_level_up_summary_for_wizard(player, campaign, summary)
    assert level_up_summary_needs_wizard(enriched) is False

    row = PlayerCharacterSheet.query.filter_by(
        player_id=player.id, campaign_id=campaign.id
    ).first()
    sheet = dict(row.sheet_json)
    sheet["level"] = 3
    row.sheet_json = sheet
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(row, "sheet_json")
    db.session.commit()

    ok, _messages, summary = apply_level_up(player, campaign)
    assert ok is True
    enriched = enrich_level_up_summary_for_wizard(player, campaign, summary)
    assert level_up_summary_needs_wizard(enriched) is True


def test_enrich_level_up_summary_builds_wizard_steps():
    from app.services.character_creation.level_progression_service import (
        apply_level_up,
        enrich_level_up_summary_for_wizard,
    )

    campaign, player = _campaign_and_player()
    row = PlayerCharacterSheet.query.filter_by(
        player_id=player.id, campaign_id=campaign.id
    ).first()
    sheet = dict(row.sheet_json)
    sheet["level"] = 3
    row.sheet_json = sheet
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(row, "sheet_json")
    db.session.commit()

    ok, _messages, summary = apply_level_up(player, campaign)
    assert ok is True
    enriched = enrich_level_up_summary_for_wizard(player, campaign, summary)
    steps = enriched.get("wizard_steps") or []
    assert steps[0]["type"] == "summary"
    assert any(step.get("type") == "ability_scores" for step in steps)
    db.session.refresh(row)
    assert enriched.get("abilities", {}).get("str") == row.sheet_json["abilities"]["str"]


def test_level_down_reverses_ability_score_improvement():
    from app.services.character_creation.level_progression_service import (
        apply_ability_score_improvement,
        apply_level_up,
    )
    from sqlalchemy.orm.attributes import flag_modified

    campaign, player = _campaign_and_player()
    row = PlayerCharacterSheet.query.filter_by(
        player_id=player.id, campaign_id=campaign.id
    ).first()
    sheet = dict(row.sheet_json)
    sheet["level"] = 3
    row.sheet_json = sheet
    flag_modified(row, "sheet_json")
    db.session.commit()

    ok, _messages, _summary = apply_level_up(player, campaign)
    assert ok is True
    db.session.refresh(row)
    assert row.sheet_json["level"] == 4
    start_str = row.sheet_json["abilities"]["str"]

    ok, _message = apply_ability_score_improvement(
        player,
        campaign,
        level=4,
        increases={"str": 2},
    )
    assert ok is True
    db.session.refresh(row)
    assert row.sheet_json["abilities"]["str"] == start_str + 2

    ok, messages = apply_level_down(player, campaign)
    assert ok is True
    db.session.refresh(row)
    assert row.sheet_json["level"] == 3
    assert row.sheet_json["abilities"]["str"] == start_str
    assert any(
        choice.get("type") == "ability_scores" and not choice.get("skipped")
        for choice in (row.sheet_json.get("pending_level_choices") or [])
    )
    assert str(4) not in (row.sheet_json.get("applied_level_choices") or {})


def test_warlock_level_up_applies_pact_slots_and_invocations():
    campaign, _fighter = _campaign_and_player()
    player = _warlock_player(campaign)
    row = PlayerCharacterSheet.query.filter_by(
        player_id=player.id, campaign_id=campaign.id
    ).first()
    assert row.sheet_json["spell_slots"] == {"1": 1}
    caps = row.sheet_json.get("class_progression") or {}
    assert caps.get("cantrips_known") == 2
    assert caps.get("spells_known") == 2

    ok, _messages, summary = apply_level_up(player, campaign)
    assert ok is True
    db.session.refresh(row)
    assert row.sheet_json["level"] == 2
    assert row.sheet_json["spell_slots"] == {"1": 2}
    caps = row.sheet_json.get("class_progression") or {}
    assert caps.get("invocations_known") == 2
    assert summary is not None


def test_level_up_blocked_at_campaign_max_player_level():
    from sqlalchemy.orm.attributes import flag_modified

    from app.services.character_creation.campaign_settings import update_creation_settings

    campaign, player = _campaign_and_player()
    update_creation_settings(campaign.id, {"max_player_level": 2})
    db.session.commit()

    row = PlayerCharacterSheet.query.filter_by(
        player_id=player.id, campaign_id=campaign.id
    ).first()
    sheet = dict(row.sheet_json)
    sheet["level"] = 2
    row.sheet_json = sheet
    flag_modified(row, "sheet_json")
    db.session.commit()

    preview = preview_level_up(player, campaign)
    assert preview["available"] is False
    assert preview["max_player_level"] == 2

    ok, messages, _summary = apply_level_up(player, campaign)
    assert ok is False
    assert any("maximum level" in msg.lower() for msg in messages)
