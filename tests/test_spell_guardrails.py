"""Regression tests for spell scope guardrails and concentration lifecycle."""

from __future__ import annotations

import json
from pathlib import Path
from random import Random

import pytest

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import (
    BattleCombatant,
    Campaign,
    Player,
    PlayerCharacterSheet,
    User,
)
from app.services.character_creation.dnd5e_spells import CORE_SPELLS
from app.services.combat import encounter_service
from app.services.combat import settings_service
from app.services.spells_compendium_service import (
    AUTOMATION_DIRECT_NUMERIC,
    AUTOMATION_MANUAL,
    SpellsValidationError,
    combat_spell_snapshots,
    create_spell,
    ensure_spells_compendium,
    get_spell_entry,
    normalize_automation,
    update_spell,
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


def _make_gm_with_campaign(username: str = "guard-gm") -> tuple[User, Campaign]:
    user = User(username=username, password="x", role="GM")
    user.set_password("Secret1!")
    db.session.add(user)
    db.session.commit()
    ensure_gm_profile(user)
    db.session.commit()
    db.session.refresh(user)
    campaign = Campaign(
        gm_profile_id=user.gm_profile.id,
        name="Guard Camp",
        system_type="dnd5e",
        is_active=True,
        current_game_day=1,
        join_code=f"CAMP-{username[:8]}",
    )
    db.session.add(campaign)
    db.session.commit()
    return user, campaign


def _encounter_settings(**overrides) -> dict:
    settings = dict(settings_service.DEFAULT_SETTINGS)
    settings.update(overrides)
    return settings


def _setup_encounter(campaign, *, settings=None, prepared=None):
    encounter = encounter_service.create_encounter(campaign.id, name="Guard Encounter")
    encounter.settings_json = settings or _encounter_settings(track_spell_slots=True)
    db.session.flush()

    player = Player(campaign_id=campaign.id, user_id=None, is_npc=False)
    db.session.add(player)
    db.session.flush()
    sheet = PlayerCharacterSheet(
        player_id=player.id,
        campaign_id=campaign.id,
        sheet_json={
            "level": 5,
            "abilities": {
                "int": 16,
                "dex": 14,
                "con": 14,
                "wis": 12,
                "str": 10,
                "cha": 10,
            },
            "defenses": {"hp_max": 30, "hp_current": 30, "ac": 12},
            "creation": {"class_key": "wizard"},
            "spells": {
                "cantrips": ["fire_bolt"],
                "prepared": prepared or ["magic_missile", "hold_person", "fireball"],
                "slots_used": {"1": 1},
            },
        },
    )
    db.session.add(sheet)
    db.session.flush()

    caster = encounter_service.add_player_combatant(encounter, player, campaign, x=0, y=0)
    target = BattleCombatant(
        encounter_id=encounter.id,
        campaign_id=encounter.campaign_id,
        name="Target",
        side="foe",
        status="active",
        x=1,
        y=0,
        hp_max=40,
        hp_current=40,
        temp_hp=0,
        ac=10,
        speed_ft=30,
        dex_mod=0,
        ability_json={"dex": 10, "con": 12},
        action_data_json={"attacks": []},
        resources_json=encounter_service._fresh_resources(),
        spell_slots_json={},
        conditions_json=[],
    )
    db.session.add(target)
    db.session.flush()
    encounter.status = "active"
    encounter.turn_index = 0
    caster.initiative_order = 0
    target.initiative_order = 1
    db.session.flush()
    return encounter, caster, target, sheet


def _spell_snapshot(caster, key: str) -> dict:
    spells = (caster.action_data_json or {}).get("spells") or []
    return next(row for row in spells if row["key"] == key)


def test_unsupported_srd_categories_normalize_to_manual():
    _, campaign = _make_gm_with_campaign("guard-srd")
    ensure_spells_compendium(campaign.id)
    manual_keys = {
        "fireball",
        "magic_missile",
        "hold_person",
        "counterspell",
        "misty_step",
        "floating_disk",
    }
    for key in manual_keys:
        entry = get_spell_entry(campaign.id, key)
        assert entry is not None, key
        assert entry["automation"] == AUTOMATION_MANUAL, key


def test_direct_numeric_allowlist_can_auto_resolve():
    _, campaign = _make_gm_with_campaign("guard-direct")
    ensure_spells_compendium(campaign.id)
    entry = create_spell(
        campaign.id,
        {
            "name": "Numeric Bolt",
            "level": 0,
            "school": "evocation",
            "summary": "Single-target force damage.",
            "attack_type": "spell_attack",
            "damage": "1d10",
            "damage_type": "force",
            "automation": "direct_numeric",
        },
    )
    assert entry["automation"] == AUTOMATION_DIRECT_NUMERIC


def test_unknown_automation_defaults_to_manual():
    _, campaign = _make_gm_with_campaign("guard-unknown")
    ensure_spells_compendium(campaign.id)
    entry = create_spell(
        campaign.id,
        {
            "name": "Odd Spell",
            "level": 1,
            "school": "illusion",
            "summary": "Strange effect.",
            "automation": "expression_engine",
        },
    )
    assert entry["automation"] == AUTOMATION_MANUAL


def test_manual_cast_logs_without_forbidden_side_effects():
    _, campaign = _make_gm_with_campaign("guard-manual-side")
    encounter, caster, target, _sheet = _setup_encounter(campaign)
    caster.spell_slots_json = {"2": {"total": 2, "remaining": 2}}
    db.session.commit()

    before_combatants = BattleCombatant.query.filter_by(encounter_id=encounter.id).count()
    result = encounter_service.cast_spell_action(
        encounter, caster, target.id, "hold_person", 2, Random(3)
    )
    db.session.commit()

    assert result["manual_resolution"] is True
    assert "damage_roll" not in result
    assert BattleCombatant.query.filter_by(encounter_id=encounter.id).count() == before_combatants
    assert encounter.map_canvas_id is None or encounter.grid_width == encounter.grid_width


def test_combat_spell_slots_are_battlecombatant_only():
    _, campaign = _make_gm_with_campaign("guard-slot-scope")
    encounter, caster, target, sheet = _setup_encounter(campaign)
    caster.spell_slots_json = {"1": {"total": 2, "remaining": 2}}
    db.session.commit()

    encounter_service.cast_spell_action(
        encounter, caster, target.id, "magic_missile", 1, Random(4)
    )
    db.session.commit()
    db.session.refresh(caster)
    db.session.refresh(sheet)

    assert caster.spell_slots_json["1"]["remaining"] == 1
    assert sheet.sheet_json["spells"]["slots_used"] == {"1": 1}


def test_manual_leveled_spell_consumes_encounter_slot_when_tracking_enabled():
    _, campaign = _make_gm_with_campaign("guard-manual-slot")
    encounter, caster, target, _sheet = _setup_encounter(campaign)
    caster.spell_slots_json = {"2": {"total": 1, "remaining": 1}}
    db.session.commit()

    encounter_service.cast_spell_action(
        encounter, caster, target.id, "hold_person", 2, Random(1)
    )
    db.session.commit()
    assert caster.spell_slots_json["2"]["remaining"] == 0


def test_manual_leveled_spell_does_not_consume_slot_when_tracking_disabled():
    _, campaign = _make_gm_with_campaign("guard-no-track")
    settings = _encounter_settings(track_spell_slots=False)
    encounter, caster, target, _sheet = _setup_encounter(campaign, settings=settings)
    caster.spell_slots_json = {"2": {"total": 1, "remaining": 1}}
    db.session.commit()

    encounter_service.cast_spell_action(
        encounter, caster, target.id, "hold_person", 2, Random(1)
    )
    db.session.commit()
    assert caster.spell_slots_json["2"]["remaining"] == 1


def test_post_combat_does_not_persist_source_sheet_slot_usage():
    _, campaign = _make_gm_with_campaign("guard-post")
    encounter, caster, target, sheet = _setup_encounter(campaign)
    caster.spell_slots_json = {"1": {"total": 2, "remaining": 2}}
    db.session.commit()

    encounter_service.cast_spell_action(
        encounter, caster, target.id, "magic_missile", 1, Random(2)
    )
    encounter.status = "ended"
    db.session.commit()
    db.session.refresh(sheet)
    assert sheet.sheet_json["spells"]["slots_used"] == {"1": 1}


def test_manual_ui_does_not_offer_auto_controls():
    js = Path("app/static/js/gm_battle.js").read_text(encoding="utf-8")
    assert "Log Cast" in js
    assert "Manual resolution required" in js
    assert "display only" in js
    assert "spellCastButtonLabel" in js


def test_spell_metadata_size_caps_are_enforced():
    _, campaign = _make_gm_with_campaign("guard-size")
    ensure_spells_compendium(campaign.id)
    huge_summary = "x" * 600
    with pytest.raises(SpellsValidationError):
        create_spell(
            campaign.id,
            {
                "name": "Huge Notes",
                "level": 1,
                "school": "evocation",
                "summary": huge_summary,
            },
        )


def test_oversized_spell_metadata_is_rejected():
    _, campaign = _make_gm_with_campaign("guard-reject")
    ensure_spells_compendium(campaign.id)
    payload = {
        "name": "Blob Spell",
        "level": 1,
        "school": "evocation",
        "summary": "Too big",
        "notes": "n" * 2000,
    }
    with pytest.raises(SpellsValidationError):
        create_spell(campaign.id, payload)
    assert get_spell_entry(campaign.id, "blob_spell") is None


def test_automation_mode_constants_are_single_source():
    assert normalize_automation("auto") == AUTOMATION_DIRECT_NUMERIC
    assert normalize_automation(AUTOMATION_DIRECT_NUMERIC) == AUTOMATION_DIRECT_NUMERIC
    assert normalize_automation("manual") == AUTOMATION_MANUAL
    js = Path("app/static/js/gm_battle.js").read_text(encoding="utf-8")
    assert "direct_numeric" in js
    assert "SPELL_AUTOMATION_MANUAL" in js


def test_snapshot_reclassifies_manual_before_combat():
    _, campaign = _make_gm_with_campaign("guard-snapshot")
    ensure_spells_compendium(campaign.id)
    update_spell(
        campaign.id,
        "fire_bolt",
        {
            **get_spell_entry(campaign.id, "fire_bolt"),
            "area": {"shape": "sphere", "size_ft": 10},
            "summary": "Now an area spell.",
        },
    )
    db.session.commit()
    encounter, caster, _target, _sheet = _setup_encounter(
        campaign, prepared=["fire_bolt"]
    )
    snap = _spell_snapshot(caster, "fire_bolt")
    assert snap["automation"] == AUTOMATION_MANUAL


def test_multi_target_or_area_spells_remain_manual():
    _, campaign = _make_gm_with_campaign("guard-area")
    ensure_spells_compendium(campaign.id)
    for key in ("fireball", "thunderwave", "magic_missile", "scorching_ray"):
        entry = get_spell_entry(campaign.id, key)
        assert entry["automation"] == AUTOMATION_MANUAL, key


def test_concentration_starts_on_concentration_spell():
    _, campaign = _make_gm_with_campaign("guard-conc-start")
    encounter, caster, target, _sheet = _setup_encounter(campaign)
    caster.spell_slots_json = {"2": {"total": 2, "remaining": 2}}
    db.session.commit()

    result = encounter_service.cast_spell_action(
        encounter, caster, target.id, "hold_person", 2, Random(1)
    )
    db.session.commit()
    resources = caster.resources_json or {}
    assert result.get("concentration")
    assert resources["concentration"]["spell_key"] == "hold_person"
    assert resources["concentrating"] is True


def test_new_concentration_replaces_prior_concentration():
    _, campaign = _make_gm_with_campaign("guard-conc-replace")
    encounter, caster, target, _sheet = _setup_encounter(campaign)
    caster.spell_slots_json = {"2": {"total": 2, "remaining": 2}}
    target.conditions_json = ["paralyzed"]
    caster.resources_json = {
        **encounter_service._fresh_resources(),
        "concentration": {
            "spell_key": "hold_person",
            "spell_name": "Hold Person",
            "target_id": target.id,
            "round_number": 1,
            "linked_effects": [
                {
                    "type": "condition",
                    "target_id": target.id,
                    "value": "paralyzed",
                    "applied": True,
                }
            ],
        },
        "concentrating": True,
    }
    db.session.commit()

    encounter_service.cast_spell_action(
        encounter, caster, target.id, "hold_person", 2, Random(2)
    )
    db.session.commit()
    assert caster.resources_json["concentration"]["spell_key"] == "hold_person"
    assert "paralyzed" not in (target.conditions_json or [])


def test_manual_concentration_end_authorization():
    _, campaign = _make_gm_with_campaign("guard-conc-auth")
    settings = _encounter_settings(player_concentration_end=False)
    encounter, caster, _target, _sheet = _setup_encounter(campaign, settings=settings)
    caster.resources_json = {
        **encounter_service._fresh_resources(),
        "concentration": {
            "spell_key": "hold_person",
            "spell_name": "Hold Person",
            "target_id": _target.id,
            "round_number": 1,
            "linked_effects": [],
        },
        "concentrating": True,
    }
    db.session.commit()

    with pytest.raises(encounter_service.CombatValidationError):
        encounter_service.end_concentration_action(
            encounter, caster, role="player"
        )

    encounter_service.end_concentration_action(encounter, caster, role="gm")
    db.session.commit()
    assert caster.resources_json.get("concentration") is None


def test_damage_check_success_preserves_concentration():
    _, campaign = _make_gm_with_campaign("guard-conc-success")
    settings = _encounter_settings(concentration_check_mode="gm_entered")
    encounter, caster, target, _sheet = _setup_encounter(campaign, settings=settings)
    caster.resources_json = {
        **encounter_service._fresh_resources(),
        "concentration": {
            "spell_key": "hold_person",
            "spell_name": "Hold Person",
            "target_id": target.id,
            "round_number": 1,
            "linked_effects": [],
        },
        "concentrating": True,
    }
    db.session.commit()

    outcome = encounter_service._apply_outcome_to_target(
        encounter,
        caster,
        12,
        encounter_service.settings_for(encounter),
        Random(1),
        concentration_check_override={"success": True},
    )
    db.session.refresh(caster)
    assert outcome["concentration"]["success"] is True
    assert caster.resources_json.get("concentration") is not None


def test_damage_check_failure_ends_concentration_and_tracked_effects():
    _, campaign = _make_gm_with_campaign("guard-conc-fail")
    settings = _encounter_settings(concentration_check_mode="gm_entered")
    encounter, caster, target, sheet = _setup_encounter(campaign, settings=settings)
    target.conditions_json = ["paralyzed"]
    caster.resources_json = {
        **encounter_service._fresh_resources(),
        "concentration": {
            "spell_key": "hold_person",
            "spell_name": "Hold Person",
            "target_id": target.id,
            "round_number": 1,
            "linked_effects": [
                {
                    "type": "condition",
                    "target_id": target.id,
                    "value": "paralyzed",
                    "applied": True,
                }
            ],
        },
        "concentrating": True,
    }
    db.session.commit()

    encounter_service._apply_outcome_to_target(
        encounter,
        caster,
        22,
        encounter_service.settings_for(encounter),
        Random(1),
        concentration_check_override={"success": False},
    )
    db.session.commit()
    assert caster.resources_json.get("concentration") is None
    assert "paralyzed" not in (target.conditions_json or [])
    assert sheet.sheet_json["spells"]["slots_used"] == {"1": 1}


def test_concentration_renders_authoritative_field_and_badge():
    from app.services.combat.serializers import serialize_combatant

    _, campaign = _make_gm_with_campaign("guard-conc-serialize")
    encounter, caster, _target, _sheet = _setup_encounter(campaign)
    caster.resources_json = {
        **encounter_service._fresh_resources(),
        "concentration": {
            "spell_key": "hold_person",
            "spell_name": "Hold Person",
            "target_id": _target.id,
            "round_number": 1,
            "linked_effects": [],
        },
        "concentrating": True,
    }
    db.session.commit()

    payload = serialize_combatant(caster, for_gm=True)
    assert payload["concentration"]["spell_key"] == "hold_person"
    assert "concentrating" in payload["conditions"]


def test_manual_concentration_cast_cleanup_is_state_only_when_untracked():
    _, campaign = _make_gm_with_campaign("guard-conc-untracked")
    encounter, caster, target, _sheet = _setup_encounter(campaign)
    caster.spell_slots_json = {"2": {"total": 2, "remaining": 2}}
    db.session.commit()

    result = encounter_service.cast_spell_action(
        encounter, caster, target.id, "hold_person", 2, Random(3)
    )
    encounter_service.end_concentration_action(encounter, caster, role="gm")
    db.session.commit()

    assert result["concentration"]["linked_effects"]
    assert result["concentration"]["linked_effects"][0]["applied"] is False
    assert caster.resources_json.get("concentration") is None


def test_death_or_defeat_ends_concentration_when_supported():
    _, campaign = _make_gm_with_campaign("guard-conc-death")
    settings = _encounter_settings(death_saves=False)
    encounter, caster, target, _sheet = _setup_encounter(campaign, settings=settings)
    caster.resources_json = {
        **encounter_service._fresh_resources(),
        "concentration": {
            "spell_key": "hold_person",
            "spell_name": "Hold Person",
            "target_id": target.id,
            "round_number": 1,
            "linked_effects": [],
        },
        "concentrating": True,
    }
    caster.hp_current = 5
    db.session.commit()

    encounter_service._apply_outcome_to_target(
        encounter,
        caster,
        50,
        encounter_service.settings_for(encounter),
        Random(1),
    )
    db.session.commit()
    assert caster.status == "dead"
    assert caster.resources_json.get("concentration") is None


def test_upcast_scaling_stays_manual_without_explicit_numeric_rule():
    _, campaign = _make_gm_with_campaign("guard-upcast")
    ensure_spells_compendium(campaign.id)
    entry = get_spell_entry(campaign.id, "fireball")
    assert entry["automation"] == AUTOMATION_MANUAL
    assert entry["upcast"].get("damage_per_slot") == "1d6"


def test_battle_settings_exposes_spell_rule_toggles():
    js = Path("app/static/js/gm_battle.js").read_text(encoding="utf-8")
    for key in (
        "direct_numeric_auto_resolution",
        "manual_spell_slot_consumption",
        "concentration_tracking",
        "concentration_auto_replace",
        "concentration_cleanup_tracked_effects",
        "player_concentration_end",
        "concentration_check_mode",
    ):
        assert key in js


def test_disabled_direct_numeric_auto_resolution_logs_manual():
    _, campaign = _make_gm_with_campaign("guard-disable-auto")
    settings = _encounter_settings(
        track_spell_slots=False,
        direct_numeric_auto_resolution=False,
    )
    encounter, caster, target, _sheet = _setup_encounter(
        campaign, settings=settings, prepared=["fire_bolt"]
    )
    db.session.commit()

    result = encounter_service.cast_spell_action(
        encounter, caster, target.id, "fire_bolt", 0, Random(9)
    )
    assert result["manual_resolution"] is True
    assert "damage_roll" not in result


def test_disabled_manual_slot_consumption_preserves_slots():
    _, campaign = _make_gm_with_campaign("guard-disable-manual-slot")
    settings = _encounter_settings(
        track_spell_slots=True,
        manual_spell_slot_consumption=False,
    )
    encounter, caster, target, _sheet = _setup_encounter(campaign, settings=settings)
    caster.spell_slots_json = {"2": {"total": 1, "remaining": 1}}
    db.session.commit()

    encounter_service.cast_spell_action(
        encounter, caster, target.id, "hold_person", 2, Random(1)
    )
    db.session.commit()
    assert caster.spell_slots_json["2"]["remaining"] == 1


def test_disabled_concentration_tracking_skips_concentration_state():
    _, campaign = _make_gm_with_campaign("guard-disable-conc")
    settings = _encounter_settings(concentration_tracking=False)
    encounter, caster, target, _sheet = _setup_encounter(campaign, settings=settings)
    db.session.commit()

    result = encounter_service.cast_spell_action(
        encounter, caster, target.id, "hold_person", 2, Random(1)
    )
    db.session.commit()
    assert "concentration" not in result or result.get("concentration") is None
    assert caster.resources_json.get("concentration") is None


def test_disabled_concentration_damage_checks_preserves_concentration():
    _, campaign = _make_gm_with_campaign("guard-disable-checks")
    settings = _encounter_settings(concentration_checks=False)
    encounter, caster, _target, _sheet = _setup_encounter(campaign, settings=settings)
    caster.resources_json = {
        **encounter_service._fresh_resources(),
        "concentration": {
            "spell_key": "hold_person",
            "spell_name": "Hold Person",
            "target_id": _target.id,
            "round_number": 1,
            "linked_effects": [],
        },
        "concentrating": True,
    }
    db.session.commit()

    outcome = encounter_service._apply_outcome_to_target(
        encounter,
        caster,
        5,
        encounter_service.settings_for(encounter),
        Random(1),
    )
    db.session.refresh(caster)
    assert "concentration" not in outcome
    assert caster.resources_json.get("concentration") is not None


def test_disabled_concentration_cleanup_keeps_tracked_effects_for_gm():
    _, campaign = _make_gm_with_campaign("guard-disable-clean")
    settings = _encounter_settings(concentration_cleanup_tracked_effects=False)
    encounter, caster, target, _sheet = _setup_encounter(campaign, settings=settings)
    target.conditions_json = ["paralyzed"]
    caster.resources_json = {
        **encounter_service._fresh_resources(),
        "concentration": {
            "spell_key": "hold_person",
            "spell_name": "Hold Person",
            "target_id": target.id,
            "round_number": 1,
            "linked_effects": [
                {
                    "type": "condition",
                    "target_id": target.id,
                    "value": "paralyzed",
                    "applied": True,
                }
            ],
        },
        "concentrating": True,
    }
    db.session.commit()

    encounter_service.end_concentration_action(encounter, caster, role="gm")
    db.session.commit()
    assert caster.resources_json.get("concentration") is None
    assert "paralyzed" in (target.conditions_json or [])


def test_player_manual_concentration_end_respects_setting():
    js = Path("app/static/js/gm_battle.js").read_text(encoding="utf-8")
    assert "player_concentration_end" in js
    assert "canEndConcentration" in js

    _, campaign = _make_gm_with_campaign("guard-player-end")
    settings = _encounter_settings(player_concentration_end=True)
    encounter, caster, _target, _sheet = _setup_encounter(campaign, settings=settings)
    caster.resources_json = {
        **encounter_service._fresh_resources(),
        "concentration": {
            "spell_key": "hold_person",
            "spell_name": "Hold Person",
            "target_id": _target.id,
            "round_number": 1,
            "linked_effects": [],
        },
        "concentrating": True,
    }
    db.session.commit()

    encounter_service.end_concentration_action(encounter, caster, role="player")
    db.session.commit()
    assert caster.resources_json.get("concentration") is None


def test_combat_snapshot_automation_recomputed():
    _, campaign = _make_gm_with_campaign("guard-snap-auto")
    ensure_spells_compendium(campaign.id)
    snaps = combat_spell_snapshots(campaign.id, ["fire_bolt", "fireball"])
    by_key = {row["key"]: row for row in snaps}
    assert by_key["fire_bolt"]["automation"] == AUTOMATION_DIRECT_NUMERIC
    assert by_key["fireball"]["automation"] == AUTOMATION_MANUAL


def test_legacy_auto_alias_normalizes_to_direct_numeric():
    _, campaign = _make_gm_with_campaign("guard-legacy")
    ensure_spells_compendium(campaign.id)
    entry = get_spell_entry(campaign.id, "fire_bolt")
    assert entry["automation"] == AUTOMATION_DIRECT_NUMERIC


def test_compendium_entry_size_limit_rejects_blob():
    _, campaign = _make_gm_with_campaign("guard-entry-bytes")
    ensure_spells_compendium(campaign.id)
    blob = {"notes": "z" * 70000}
    with pytest.raises(SpellsValidationError):
        create_spell(
            campaign.id,
            {
                "name": "Byte Blob",
                "level": 1,
                "school": "evocation",
                "summary": "Too large overall",
                **blob,
            },
        )
