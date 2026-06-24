"""Tests for SRD class progression seeds and schema."""

from __future__ import annotations

import pytest

import uuid

from app.services.character_creation.dnd5e_srd_class_progression import (
    CURRENT_SRD_SEED_VERSION,
    SRD_CLASS_PROGRESSIONS,
)
from app.services.character_creation.progression_helpers import resolve_spell_slots_from_row
from app.services.classes_compendium_service import (
    ClassesValidationError,
    _clean_level_progression,
    _normalize_entry,
    ensure_classes_compendium,
)
from app.extensions import db
from app.models import Campaign, User
from app.services.user_capabilities import ensure_gm_profile


def _make_campaign(username: str = "srd-seed-gm") -> Campaign:
    user = User(username=username, password="x", role="GM")
    user.set_password("Secret1!")
    db.session.add(user)
    db.session.commit()
    ensure_gm_profile(user)
    db.session.commit()
    campaign = Campaign(
        gm_profile_id=user.gm_profile.id,
        name="SRD Seed",
        system_type="dnd5e",
        is_active=True,
        current_game_day=1,
        join_code=f"CAMP-{uuid.uuid4().hex[:8].upper()}",
    )
    db.session.add(campaign)
    db.session.commit()
    return campaign


@pytest.mark.parametrize("class_key", list(SRD_CLASS_PROGRESSIONS.keys()))
def test_srd_progression_has_twenty_rows(class_key):
    entry = SRD_CLASS_PROGRESSIONS[class_key]
    rows = entry["level_progression"]
    assert len(rows) == 20
    assert [row["level"] for row in rows] == list(range(1, 21))


def test_warlock_level_11_pact_magic():
    rows = SRD_CLASS_PROGRESSIONS["warlock"]["level_progression"]
    row = rows[10]
    assert row["level"] == 11
    assert row["pact_magic"] == {"slots": 3, "slot_level": 5}
    assert row["invocations_known"] == 5
    assert resolve_spell_slots_from_row(row) == {"5": 3}


def test_warlock_level_20_pact_magic():
    rows = SRD_CLASS_PROGRESSIONS["warlock"]["level_progression"]
    row = rows[19]
    assert row["pact_magic"] == {"slots": 4, "slot_level": 5}
    assert row["invocations_known"] == 8


def test_wizard_level_5_spell_slots():
    rows = SRD_CLASS_PROGRESSIONS["wizard"]["level_progression"]
    row = rows[4]
    assert row["spell_slots"].get("3") == 2
    assert row["cantrips_known"] == 4


def test_clean_progression_accepts_extended_fields():
    rows = SRD_CLASS_PROGRESSIONS["warlock"]["level_progression"]
    cleaned = _clean_level_progression(rows)
    assert cleaned[1]["invocations_known"] == 2
    assert cleaned[0]["pact_magic"] == {"slots": 1, "slot_level": 1}


def test_ensure_compendium_applies_srd_seed():
    from app import app as flask_app

    with flask_app.app_context():
        db.create_all()
        campaign = _make_campaign()
        entries = ensure_classes_compendium(campaign.id)
        warlock = next(e for e in entries if e["key"] == "warlock")
        assert warlock["srd_seed_version"] == CURRENT_SRD_SEED_VERSION
        assert warlock["spellcasting"]["type"] == "pact"
        assert warlock["level_progression"][1]["invocations_known"] == 2
        db.session.rollback()


def test_gm_customized_class_skips_reseed():
    from app import app as flask_app

    with flask_app.app_context():
        db.create_all()
        campaign = _make_campaign("srd-custom-gm")
        entries = ensure_classes_compendium(campaign.id)
        warlock = next(e for e in entries if e["key"] == "warlock")
        warlock["progression_customized"] = True
        warlock["level_progression"][0]["cantrips_known"] = 5
        from app.services.classes_compendium_service import update_class

        update_class(campaign.id, "warlock", warlock)
        db.session.commit()

        refreshed = ensure_classes_compendium(campaign.id)
        warlock2 = next(e for e in refreshed if e["key"] == "warlock")
        assert warlock2["level_progression"][0]["cantrips_known"] == 5
        db.session.rollback()
