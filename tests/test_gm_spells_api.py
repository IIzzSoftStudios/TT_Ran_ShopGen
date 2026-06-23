"""Tests for GM spell compendium API, SRD seed guardrails, and combat casting."""

from __future__ import annotations

import re

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
from app.services.character_creation.dnd5e_spells import CORE_SPELLS, spell_slug
from app.services.character_creation.srd_spell_manifest import (
    SRD_SPELL_COUNT,
    SRD_SPELLS_BY_LEVEL,
)
from app.services.combat import encounter_service
from app.services.combat import settings_service
from app.services.spells_compendium_service import (
    create_spell,
    ensure_spells_compendium,
    get_spell_entry,
    list_visible_spells,
    resolve_character_spells,
    update_spell,
)
from app.services.user_capabilities import ensure_gm_profile
from tests.session_helpers import seed_client_session


_LORE_DENY = re.compile(
    r"\b(bigby|melf|mordenkainen|nystul|otiluke|leomund|drawmij|otto|tasha|tenser|evard)\b",
    re.I,
)

_REQUIRED_FIELDS = (
    "key",
    "name",
    "level",
    "school",
    "casting_time",
    "range_text",
    "components",
    "duration",
    "automation",
    "summary",
)


@pytest.fixture(autouse=True)
def _db_tables():
    flask_app.config["WTF_CSRF_ENABLED"] = False
    with flask_app.app_context():
        db.create_all()
        yield
        db.session.rollback()
        db.drop_all()


def _make_gm_with_campaign(username: str = "gm-spells") -> tuple[User, Campaign]:
    user = User(username=username, password="x", role="GM")
    user.set_password("Secret1!")
    db.session.add(user)
    db.session.commit()
    ensure_gm_profile(user)
    db.session.commit()
    db.session.refresh(user)
    campaign = Campaign(
        gm_profile_id=user.gm_profile.id,
        name="Spell Camp",
        system_type="dnd5e",
        is_active=True,
        current_game_day=1,
        join_code="CAMP-SPELLS-01",
    )
    db.session.add(campaign)
    db.session.commit()
    return user, campaign


def test_core_spells_matches_srd_manifest():
    assert len(CORE_SPELLS) == SRD_SPELL_COUNT == 319
    manifest_names = {
        (level, name)
        for level, names in SRD_SPELLS_BY_LEVEL.items()
        for name in names
    }
    core_names = {(spell["level"], spell["name"]) for spell in CORE_SPELLS}
    assert core_names == manifest_names


def test_core_spells_unique_keys_and_no_product_identity():
    keys = [spell["key"] for spell in CORE_SPELLS]
    names = [spell["name"] for spell in CORE_SPELLS]
    assert len(keys) == len(set(keys))
    assert len(names) == len(set(names))
    for spell in CORE_SPELLS:
        assert spell_slug(spell["name"]) == spell["key"]
        assert 0 <= int(spell["level"]) <= 9
        assert spell.get("classes")
        for field in _REQUIRED_FIELDS:
            assert spell.get(field) not in (None, "")
        assert not _LORE_DENY.search(spell["name"])
    assert any(spell["name"] == "Floating Disk" for spell in CORE_SPELLS)
    assert any(spell["name"] == "Arcane Hand" for spell in CORE_SPELLS)
    fire_bolt = next(spell for spell in CORE_SPELLS if spell["key"] == "fire_bolt")
    assert set(fire_bolt["classes"]) == {"sorcerer", "wizard"}


def test_representative_spell_mechanics():
    by_key = {spell["key"]: spell for spell in CORE_SPELLS}
    assert by_key["fire_bolt"]["damage"] == "1d10"
    assert by_key["magic_missile"]["damage"] == "3d4+3"
    assert by_key["cure_wounds"]["healing"] == "1d8"
    assert by_key["hold_person"]["concentration"] is True
    assert by_key["floating_disk"]["ritual"] is True
    assert by_key["fireball"]["upcast"].get("damage_per_slot") == "1d6"
    assert by_key["misty_step"]["automation"] == "manual"
    assert by_key["counterspell"]["automation"] == "manual"


def test_ensure_spells_compendium_seeds_core_spells():
    _, campaign = _make_gm_with_campaign("gm-seed-spells")
    entries = ensure_spells_compendium(campaign.id)
    assert len(entries) == 319
    fire_bolt = get_spell_entry(campaign.id, "fire_bolt")
    assert fire_bolt is not None
    assert fire_bolt["name"] == "Fire Bolt"


def test_hidden_spell_filtered_for_players():
    _, campaign = _make_gm_with_campaign("gm-hidden-spell")
    ensure_spells_compendium(campaign.id)
    update_spell(
        campaign.id,
        "fire_bolt",
        {
            **get_spell_entry(campaign.id, "fire_bolt"),
            "is_hidden": True,
            "visible_to_owner": False,
        },
    )
    db.session.commit()
    visible = list_visible_spells(campaign.id)
    assert all(row["key"] != "fire_bolt" for row in visible)


def test_create_custom_spell_and_validation():
    _, campaign = _make_gm_with_campaign("gm-custom-spell")
    ensure_spells_compendium(campaign.id)
    entry = create_spell(
        campaign.id,
        {
            "name": "Crystal Lance",
            "level": 1,
            "school": "evocation",
            "summary": "A homebrew evocation.",
            "attack_type": "spell_attack",
            "damage": "2d8",
            "damage_type": "force",
            "automation": "auto",
        },
    )
    db.session.commit()
    assert entry["key"] == "crystal_lance"
    assert entry["source"] == "custom"
    assert entry["automation"] == "direct_numeric"


def test_spell_without_automation_fields_forced_manual():
    _, campaign = _make_gm_with_campaign("gm-manual-spell")
    ensure_spells_compendium(campaign.id)
    entry = create_spell(
        campaign.id,
        {
            "name": "Story Spark",
            "level": 0,
            "school": "illusion",
            "summary": "Pure narrative.",
            "automation": "auto",
        },
    )
    assert entry["automation"] == "manual"


def test_gm_spells_api_routes(client):
    user, campaign = _make_gm_with_campaign("gm-spells-api")
    client = flask_app.test_client()
    seed_client_session(client, user, campaign_id=campaign.id)

    listed = client.get("/gm/spells/compendium")
    assert listed.status_code == 200
    payload = listed.get_json()
    assert len(payload["spells"]) == 319

    created = client.post(
        "/gm/spells/compendium",
        json={
            "name": "Test Bolt",
            "level": 0,
            "school": "evocation",
            "summary": "Test cantrip.",
            "attack_type": "spell_attack",
            "damage": "1d4",
            "damage_type": "force",
            "automation": "auto",
        },
    )
    assert created.status_code == 201
    key = created.get_json()["spell"]["key"]

    updated = client.post(
        f"/gm/spells/compendium/{key}",
        json={
            **created.get_json()["spell"],
            "summary": "Updated summary.",
        },
    )
    assert updated.status_code == 200
    assert updated.get_json()["spell"]["summary"] == "Updated summary."


def test_dashboard_includes_spell_search_and_click_sort_controls():
    user, campaign = _make_gm_with_campaign("gm-spells-dashboard")
    client = flask_app.test_client()
    seed_client_session(client, user, campaign_id=campaign.id)

    resp = client.get("/gm/")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert 'id="spells-tab-btn"' in html
    assert 'id="spells-search-input"' in html
    assert 'class="species-compendium-table"' in html
    assert 'id="spells-compendium-body"' in html
    assert 'data-spell-sort="name"' in html
    assert 'data-spell-sort="level"' in html
    assert 'data-spell-sort="school"' in html
    assert 'data-spell-sort="ritual"' in html
    assert 'data-spell-sort="classes"' in html
    assert "Ritual Casting" in html
    assert ">Classes</button>" in html
    assert 'id="spells-folder-select"' not in html
    assert 'id="spells-sort-select"' not in html
    assert "levelDetails.open = true" not in html
    assert "classDetails.open = true" not in html
    assert 'id="spells-compendium-count"' in html


def test_resolve_character_spells_from_sheet_keys():
    _, campaign = _make_gm_with_campaign("gm-resolve-spells")
    ensure_spells_compendium(campaign.id)
    sheet = {
        "spells": {
            "cantrips": ["fire_bolt"],
            "prepared": ["magic_missile"],
            "known": ["fire_bolt", "magic_missile"],
        }
    }
    resolved = resolve_character_spells(campaign.id, sheet)
    assert {row["key"] for row in resolved["cantrips"]} == {"fire_bolt"}
    assert {row["key"] for row in resolved["prepared"]} == {"magic_missile"}


def _setup_encounter_with_caster(campaign, *, track_slots=True):
    encounter = encounter_service.create_encounter(campaign.id, name="Spell Test")
    settings = dict(settings_service.DEFAULT_SETTINGS)
    settings["track_spell_slots"] = track_slots
    encounter.settings_json = settings
    db.session.flush()

    player = Player(campaign_id=campaign.id, user_id=None, is_npc=False)
    db.session.add(player)
    db.session.flush()
    sheet = PlayerCharacterSheet(
        player_id=player.id,
        campaign_id=campaign.id,
        sheet_json={
            "level": 3,
            "abilities": {"int": 16, "dex": 14, "con": 12, "wis": 10, "str": 10, "cha": 10},
            "defenses": {"hp_max": 20, "hp_current": 20, "ac": 12},
            "creation": {"class_key": "wizard"},
            "spells": {
                "cantrips": ["fire_bolt"],
                "prepared": ["magic_missile", "fireball"],
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
        hp_max=30,
        hp_current=30,
        temp_hp=0,
        ac=10,
        speed_ft=30,
        dex_mod=0,
        ability_json={"dex": 10},
        action_data_json={"attacks": []},
        resources_json={"action": True, "bonus_action": True, "reaction": True},
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
    return encounter, caster, target


def test_cast_spell_consumes_slot_and_logs():
    _, campaign = _make_gm_with_campaign("gm-cast-slot")
    encounter, caster, target = _setup_encounter_with_caster(campaign, track_slots=True)
    caster.spell_slots_json = {"1": {"total": 1, "remaining": 1}}
    db.session.commit()

    from random import Random

    result = encounter_service.cast_spell_action(
        encounter,
        caster,
        target.id,
        "magic_missile",
        1,
        Random(1),
    )
    db.session.commit()
    assert result["spell"]["key"] == "magic_missile"
    assert caster.spell_slots_json["1"]["remaining"] == 0


def test_cast_spell_rejects_missing_slot():
    _, campaign = _make_gm_with_campaign("gm-no-slot")
    encounter, caster, target = _setup_encounter_with_caster(campaign, track_slots=True)
    caster.spell_slots_json = {"1": {"total": 0, "remaining": 0}}
    db.session.commit()

    from random import Random

    with pytest.raises(encounter_service.CombatValidationError):
        encounter_service.cast_spell_action(
            encounter,
            caster,
            target.id,
            "magic_missile",
            1,
            Random(1),
        )


def test_cast_spell_without_slot_tracking():
    _, campaign = _make_gm_with_campaign("gm-no-track")
    encounter, caster, target = _setup_encounter_with_caster(campaign, track_slots=False)
    caster.spell_slots_json = {"1": {"total": 0, "remaining": 0}}
    db.session.commit()

    from random import Random

    result = encounter_service.cast_spell_action(
        encounter,
        caster,
        target.id,
        "fire_bolt",
        0,
        Random(2),
    )
    assert result["spell"]["key"] == "fire_bolt"
    assert caster.spell_slots_json["1"]["remaining"] == 0


def test_combat_snapshot_isolated_from_compendium_edit():
    _, campaign = _make_gm_with_campaign("gm-snapshot")
    ensure_spells_compendium(campaign.id)
    encounter, caster, _target = _setup_encounter_with_caster(campaign, track_slots=False)
    before = (caster.action_data_json or {}).get("spells") or []
    fire = next(row for row in before if row["key"] == "fire_bolt")
    assert fire["damage"] == "1d10"

    update_spell(
        campaign.id,
        "fire_bolt",
        {
            **get_spell_entry(campaign.id, "fire_bolt"),
            "damage": "9d9",
            "summary": "Edited after snapshot.",
        },
    )
    db.session.commit()

    db.session.refresh(caster)
    after = (caster.action_data_json or {}).get("spells") or []
    snap = next(row for row in after if row["key"] == "fire_bolt")
    assert snap["damage"] == "1d10"

    live = get_spell_entry(campaign.id, "fire_bolt")
    assert live["damage"] == "9d9"
