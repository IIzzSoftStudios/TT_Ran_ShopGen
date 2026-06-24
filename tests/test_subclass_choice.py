"""Tests for player subclass selection and trait accumulation."""

from __future__ import annotations

import uuid

import pytest

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import Campaign, Player, PlayerCharacterSheet, User
from app.services.character_creation.level_progression_service import apply_subclass_choice
from app.services.classes_compendium_service import (
    accumulated_class_trait_keys,
    ensure_classes_compendium,
    get_class_entry,
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


def _make_player_campaign() -> tuple[Campaign, Player]:
    user = User(username="subclass-gm", password="x", role="GM")
    user.set_password("Secret1!")
    db.session.add(user)
    db.session.commit()
    ensure_gm_profile(user)
    db.session.commit()
    campaign = Campaign(
        gm_profile_id=user.gm_profile.id,
        name="Subclass Camp",
        system_type="dnd5e",
        is_active=True,
        current_game_day=1,
        join_code=f"CAMP-{uuid.uuid4().hex[:8].upper()}",
    )
    db.session.add(campaign)
    db.session.commit()
    player_user = User(username="subclass-player", password="x", role="Player")
    player_user.set_password("Secret1!")
    db.session.add(player_user)
    db.session.commit()
    player = Player(
        user_id=player_user.id,
        campaign_id=campaign.id,
        currency=0,
        is_npc=False,
    )
    db.session.add(player)
    db.session.commit()
    return campaign, player


def _barbarian_sheet(level: int = 3) -> dict:
    return {
        "level": level,
        "class_name": "Barbarian",
        "creation": {
            "class_key": "barbarian",
            "class_source": "base",
        },
        "abilities": {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8},
    }


def test_apply_subclass_choice_grants_traits():
    campaign, player = _make_player_campaign()
    ensure_classes_compendium(campaign.id)
    sheet = _barbarian_sheet(3)
    row = PlayerCharacterSheet(
        player_id=player.id,
        campaign_id=campaign.id,
        sheet_json=sheet,
    )
    db.session.add(row)
    db.session.commit()

    ok, message = apply_subclass_choice(
        player,
        campaign,
        level=3,
        subclass_key="path-of-the-berserker",
    )
    assert ok, message
    db.session.refresh(row)
    creation = row.sheet_json.get("creation") or {}
    assert creation.get("subclass_key") == "path-of-the-berserker"
    selections = row.sheet_json.get("class_trait_selections") or {}
    level_three = selections.get("3") or []
    assert "scf-path-of-the-berserker-frenzy" in level_three


def test_subclass_choice_blocked_after_pick():
    campaign, player = _make_player_campaign()
    ensure_classes_compendium(campaign.id)
    sheet = _barbarian_sheet(3)
    sheet["creation"]["subclass_key"] = "path-of-the-berserker"
    row = PlayerCharacterSheet(
        player_id=player.id,
        campaign_id=campaign.id,
        sheet_json=sheet,
    )
    db.session.add(row)
    db.session.commit()

    ok, message = apply_subclass_choice(
        player,
        campaign,
        level=3,
        subclass_key="champion",
    )
    assert not ok
    assert "already" in message.lower()


def test_accumulated_class_trait_keys_includes_subclass():
    campaign, _player = _make_player_campaign()
    ensure_classes_compendium(campaign.id)
    class_entry = get_class_entry(campaign.id, "barbarian")
    sheet = _barbarian_sheet(6)
    sheet["creation"]["subclass_key"] = "path-of-the-berserker"
    keys = accumulated_class_trait_keys(class_entry, 6, sheet=sheet)
    assert "scf-path-of-the-berserker-frenzy" in keys
    assert "scf-path-of-the-berserker-mindless-rage" in keys
