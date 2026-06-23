"""Tests for SRD species compendium seeding."""

from __future__ import annotations

import pytest
from sqlalchemy.orm.attributes import flag_modified

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import Campaign, CampaignWorldConfig, User
from app.services.character_creation.dnd5e_species import CORE_SPECIES
from app.services.character_creation.srd_species_manifest import SRD_SPECIES_COUNT
from app.services.species_compendium_service import ensure_species_compendium
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


def test_core_species_matches_manifest():
    assert len(CORE_SPECIES) == SRD_SPECIES_COUNT == 9


def test_ensure_species_compendium_seeds_srd_traits_and_mods():
    campaign = _make_campaign("srd-species-seed")
    entries = ensure_species_compendium(campaign.id)
    db.session.commit()

    elf = next(row for row in entries if row["key"] == "elf")
    assert elf["ability_modifiers"]["dex"] == 2
    assert elf["content_source"] == "srd_5_1"
    assert any(trait["name"] == "Darkvision" for trait in elf["traits"])
    assert "Speed 30 ft" in elf["stat_modifiers"]

    human = next(row for row in entries if row["key"] == "human")
    assert all(human["ability_modifiers"][ab] == 1 for ab in ("str", "dex", "con", "int", "wis", "cha"))

    half_elf = next(row for row in entries if row["key"] == "half-elf")
    assert half_elf["flex_ability_bonuses"] == 2

    dwarf = next(row for row in entries if row["key"] == "dwarf")
    assert "Speed 25 ft" in dwarf["stat_modifiers"]


def test_ensure_species_preserves_gm_edited_entries():
    campaign = _make_campaign("srd-species-gm-edit")
    ensure_species_compendium(campaign.id)
    db.session.commit()

    cfg = CampaignWorldConfig.query.filter_by(campaign_id=campaign.id).one()
    for row in cfg.settings_json["species_compendium"]:
        if row["key"] == "elf":
            row["ability_modifiers"]["dex"] = 3
            row["traits"] = [{"name": "Custom", "description": "GM note."}]
            row["gm_edited"] = True
    flag_modified(cfg, "settings_json")
    db.session.commit()

    entries = ensure_species_compendium(campaign.id)
    db.session.commit()
    elf = next(row for row in entries if row["key"] == "elf")
    assert elf["ability_modifiers"]["dex"] == 3
    assert elf["traits"][0]["name"] == "Custom"

    human = next(row for row in entries if row["key"] == "human")
    assert human["ability_modifiers"]["str"] == 1
