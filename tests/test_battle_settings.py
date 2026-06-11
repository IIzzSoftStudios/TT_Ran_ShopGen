"""Tests for battle settings defaults, validation, and persistence."""

from __future__ import annotations

import pytest

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import BattleSettings, Campaign, User
from app.services.combat import CombatValidationError
from app.services.combat import encounter_service, settings_service
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


def test_defaults_returned_without_row():
    campaign = _make_campaign("set-gm-1")
    settings = settings_service.get_settings(campaign.id)
    assert settings == settings_service.DEFAULT_SETTINGS
    assert BattleSettings.query.filter_by(campaign_id=campaign.id).first() is None


def test_save_persists_and_merges_partial_payload():
    campaign = _make_campaign("set-gm-2")
    saved = settings_service.save_settings(
        campaign.id,
        {"track_spell_slots": True, "diagonal_mode": "always_five"},
    )
    db.session.commit()
    assert saved["track_spell_slots"] is True
    assert saved["diagonal_mode"] == "always_five"
    # Untouched keys keep defaults.
    assert saved["death_saves"] is True

    reloaded = settings_service.get_settings(campaign.id)
    assert reloaded == saved
    # Upsert: saving again reuses the single row.
    settings_service.save_settings(campaign.id, {"flanking": True})
    db.session.commit()
    assert BattleSettings.query.filter_by(campaign_id=campaign.id).count() == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"diagonal_mode": "teleport"},
        {"initiative_tie_mode": "coin_flip"},
        {"crit_mode": "triple"},
        "not-an-object",
    ],
)
def test_save_rejects_invalid_values(payload):
    campaign = _make_campaign(f"set-gm-bad-{abs(hash(str(payload))) % 10000}")
    with pytest.raises(CombatValidationError):
        settings_service.save_settings(campaign.id, payload)


def test_unknown_keys_are_dropped():
    campaign = _make_campaign("set-gm-3")
    saved = settings_service.save_settings(
        campaign.id, {"homebrew_rule": True, "flanking": True}
    )
    db.session.commit()
    assert "homebrew_rule" not in saved
    assert saved["flanking"] is True


def test_encounter_snapshots_settings_at_creation():
    campaign = _make_campaign("set-gm-4")
    settings_service.save_settings(campaign.id, {"diagonal_mode": "always_five"})
    db.session.commit()
    encounter = encounter_service.create_encounter(campaign.id)
    db.session.commit()
    assert encounter.settings_json["diagonal_mode"] == "always_five"

    # Changing campaign settings later does not rewrite the snapshot.
    settings_service.save_settings(campaign.id, {"diagonal_mode": "euclidean"})
    db.session.commit()
    assert encounter_service.settings_for(encounter)["diagonal_mode"] == "always_five"
