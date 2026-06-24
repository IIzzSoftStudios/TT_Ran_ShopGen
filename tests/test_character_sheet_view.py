"""Tests for full character sheet view data (traits, vault characters)."""

from __future__ import annotations

import pytest

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import Player, PlayerCharacterSheet, User
from app.services.character_creation.creation_service import build_final_sheet_json
from app.services.character_creation.dnd5e_catalog import merged_creation_catalog
from app.services.character_sheet_service import build_character_view


@pytest.fixture(autouse=True)
def _db_tables():
    flask_app.config["WTF_CSRF_ENABLED"] = False
    with flask_app.app_context():
        db.create_all()
        yield
        db.session.rollback()
        db.drop_all()


def test_vault_character_traits_resolve_without_campaign():
    user = User(username="solo-traits", password="x", role="Player")
    user.set_password("Secret1!")
    db.session.add(user)
    db.session.commit()
    player = Player(user_id=user.id, campaign_id=None, currency=0, is_npc=False)
    db.session.add(player)
    db.session.flush()

    catalog = merged_creation_catalog()
    sheet = build_final_sheet_json(
        {
            "name": "Vault Elf",
            "species_key": "elf",
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
            campaign_id=None,
            sheet_json=sheet,
        )
    )
    db.session.commit()

    view = build_character_view(player, None)
    assert view.traits_details["available"] is True
    assert any(t["name"] == "Keen Senses" for t in view.traits_details["traits"])
    assert view.species_details["available"] is True
    assert view.species_details["name"] == "Elf"
    assert view.background_details["available"] is True
    assert view.class_details["available"] is True
