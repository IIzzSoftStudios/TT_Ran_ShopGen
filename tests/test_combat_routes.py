"""Route tests for /api/combat/* (auth, D&D 5e gate, stale-turn 409,
cross-encounter denial, GM vs player payloads, Battle tab markup)."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import patch

import pytest
from flask import g
from PIL import Image

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import BattleActionLog, BattleCombatant, BattleEncounter, Campaign, Player, User
from app.services.combat import battle_map_service, encounter_service
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


def _make_gm_with_campaign(username: str, system_type: str = "dnd5e"):
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
        system_type=system_type,
        is_active=True,
        current_game_day=1,
    )
    db.session.add(campaign)
    db.session.commit()
    return user, campaign


def _make_player_in_campaign(username: str, campaign: Campaign):
    user = User(username=username, password="x", role="Player")
    user.set_password("Secret1!")
    db.session.add(user)
    db.session.commit()
    player = Player(user_id=user.id, campaign_id=campaign.id, currency=0)
    db.session.add(player)
    db.session.commit()
    return user, player


def _fresh_identity_client():
    """Test client that drops flask-login's per-app-context user cache.

    The ``_db_tables`` fixture keeps one app context alive for the whole test,
    so ``g._login_user`` set by one client's request would otherwise leak into
    requests made by a different client (different user) in the same test.
    """
    client = flask_app.test_client()
    orig_open = client.open

    def open_with_fresh_identity(*args, **kwargs):
        g.pop("_login_user", None)
        return orig_open(*args, **kwargs)

    client.open = open_with_fresh_identity
    return client


def _gm_client(user, campaign):
    client = _fresh_identity_client()
    seed_client_session(client, user, campaign_id=campaign.id)
    return client


def _player_client(user):
    client = _fresh_identity_client()
    seed_client_session(client, user, session_mode="player")
    return client


_MONSTER_STATS = {
    "hp_max": 12,
    "ac": 12,
    "speed_ft": 30,
    "abilities": {"str": 12, "dex": 12, "con": 12, "int": 6, "wis": 10, "cha": 6},
    "attacks": [
        {
            "key": "claw",
            "name": "Claw",
            "kind": "melee",
            "attack_mod": 30,
            "damage": "1d4+1",
            "damage_type": "slashing",
            "range_ft": 5,
        }
    ],
}


def _setup_running_encounter(client, campaign):
    """Create an encounter with two monsters and roll initiative via the API."""
    enc = client.post("/api/combat/encounters", json={"name": "Fight"}).get_json()
    eid = enc["encounter"]["id"]
    monster = client.post(
        "/api/combat/monsters",
        json={"name": "Pit Beast", "stats": _MONSTER_STATS},
    ).get_json()["monster"]
    client.post(
        f"/api/combat/encounters/{eid}/monsters/{monster['id']}/add",
        json={"count": 2},
    )
    state = client.get(f"/api/combat/encounters/{eid}").get_json()
    resp = client.post(
        f"/api/combat/encounters/{eid}/initiative",
        json={"turn_version": state["turn_version"]},
    )
    assert resp.status_code == 200
    return eid, client.get(f"/api/combat/encounters/{eid}").get_json()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def test_combat_api_requires_login():
    client = flask_app.test_client()
    assert client.get("/api/combat/encounters").status_code in (302, 401)
    assert client.post("/api/combat/encounters", json={}).status_code in (302, 401)


def test_player_session_cannot_use_gm_endpoints():
    gm, campaign = _make_gm_with_campaign("rt-gm-mode")
    client = flask_app.test_client()
    seed_client_session(client, gm, campaign_id=campaign.id, session_mode="player")
    resp = client.post("/api/combat/encounters", json={"name": "X"})
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# D&D 5e gate
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("system_type", ["pf2e", "generic"])
def test_non_dnd5e_campaigns_get_403(system_type):
    gm, campaign = _make_gm_with_campaign(f"rt-gm-{system_type}", system_type)
    client = _gm_client(gm, campaign)
    for method, path, body in (
        ("post", "/api/combat/encounters", {"name": "Nope"}),
        ("get", "/api/combat/encounters", None),
        ("post", "/api/combat/settings", {"settings": {}}),
        ("get", "/api/combat/settings", None),
        ("post", "/api/combat/monsters", {"name": "X", "stats": _MONSTER_STATS}),
        ("post", "/api/combat/monsters/generate", {"seed": "s"}),
    ):
        resp = getattr(client, method)(path, json=body) if body is not None else getattr(client, method)(path)
        assert resp.status_code == 403, path
        assert "D&D 5e" in resp.get_json()["error"]


def test_dnd5e_alias_system_types_pass_gate():
    gm, campaign = _make_gm_with_campaign("rt-gm-alias", "5e")
    client = _gm_client(gm, campaign)
    resp = client.post("/api/combat/encounters", json={"name": "Alias Fight"})
    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Full tactical loop through the API
# ---------------------------------------------------------------------------
def test_full_loop_create_add_initiative_move_attack_end_turn():
    gm, campaign = _make_gm_with_campaign("rt-gm-loop")
    client = _gm_client(gm, campaign)
    eid, state = _setup_running_encounter(client, campaign)
    assert state["status"] == "active"
    assert state["round_number"] == 1
    assert len(state["combatants"]) == 2

    current_id = state["current_combatant_id"]
    current = next(c for c in state["combatants"] if c["id"] == current_id)
    target = next(c for c in state["combatants"] if c["id"] != current_id)

    # Move one tile down.
    resp = client.post(
        f"/api/combat/encounters/{eid}/move",
        json={
            "combatant_id": current_id,
            "x": current["x"],
            "y": current["y"] + 1,
            "turn_version": state["turn_version"],
        },
    )
    assert resp.status_code == 200
    state = client.get(f"/api/combat/encounters/{eid}").get_json()

    # Reposition adjacent via direct DB tweak for the attack.
    atk = db.session.get(BattleCombatant, current_id)
    tgt = db.session.get(BattleCombatant, target["id"])
    atk.x, atk.y = 0, 0
    tgt.x, tgt.y = 1, 0
    db.session.commit()

    resp = client.post(
        f"/api/combat/encounters/{eid}/action",
        json={
            "type": "attack",
            "combatant_id": current_id,
            "target_id": target["id"],
            "attack_key": "claw",
            "turn_version": state["turn_version"],
        },
    )
    assert resp.status_code == 200
    result = resp.get_json()["result"]
    assert "to_hit" in result

    state = client.get(f"/api/combat/encounters/{eid}").get_json()
    resp = client.post(
        f"/api/combat/encounters/{eid}/end-turn",
        json={"turn_version": state["turn_version"]},
    )
    assert resp.status_code == 200
    assert resp.get_json()["next_combatant_id"] == target["id"]


def test_wait_endpoint_moves_combatant_to_bottom():
    gm, campaign = _make_gm_with_campaign("rt-gm-wait")
    client = _gm_client(gm, campaign)
    eid, state = _setup_running_encounter(client, campaign)
    current_id = state["current_combatant_id"]
    resp = client.post(
        f"/api/combat/encounters/{eid}/wait",
        json={"combatant_id": current_id, "turn_version": state["turn_version"]},
    )
    assert resp.status_code == 200
    after = client.get(f"/api/combat/encounters/{eid}").get_json()
    assert after["round_number"] == state["round_number"]
    waited = next(c for c in after["combatants"] if c["id"] == current_id)
    assert waited["has_waited"] is True


# ---------------------------------------------------------------------------
# Stale turn_version -> 409 with unchanged state
# ---------------------------------------------------------------------------
def test_stale_turn_version_returns_409_and_state_unchanged():
    gm, campaign = _make_gm_with_campaign("rt-gm-stale")
    client = _gm_client(gm, campaign)
    eid, state = _setup_running_encounter(client, campaign)
    current_id = state["current_combatant_id"]
    current = next(c for c in state["combatants"] if c["id"] == current_id)

    resp = client.post(
        f"/api/combat/encounters/{eid}/move",
        json={
            "combatant_id": current_id,
            "x": current["x"],
            "y": current["y"] + 1,
            "turn_version": state["turn_version"] + 99,
        },
    )
    assert resp.status_code == 409

    after = client.get(f"/api/combat/encounters/{eid}").get_json()
    unchanged = next(c for c in after["combatants"] if c["id"] == current_id)
    assert (unchanged["x"], unchanged["y"]) == (current["x"], current["y"])
    assert unchanged["hp_current"] == current["hp_current"]
    assert after["turn_version"] == state["turn_version"]


# ---------------------------------------------------------------------------
# Cross-encounter / cross-campaign denial
# ---------------------------------------------------------------------------
def test_cross_encounter_target_denied():
    gm, campaign = _make_gm_with_campaign("rt-gm-cross")
    client = _gm_client(gm, campaign)
    eid, state = _setup_running_encounter(client, campaign)

    with flask_app.app_context():
        other = encounter_service.create_encounter(campaign.id, "Other")
        db.session.commit()
        foreign = BattleCombatant(
            encounter_id=other.id,
            campaign_id=campaign.id,
            name="Foreign",
            side="foe",
            status="active",
            x=1,
            y=0,
            hp_max=5,
            hp_current=5,
            ac=10,
            speed_ft=30,
            dex_mod=0,
        )
        db.session.add(foreign)
        db.session.commit()
        foreign_id = foreign.id

    resp = client.post(
        f"/api/combat/encounters/{eid}/action",
        json={
            "type": "attack",
            "combatant_id": state["current_combatant_id"],
            "target_id": foreign_id,
            "attack_key": "claw",
            "turn_version": state["turn_version"],
        },
    )
    assert resp.status_code == 400


def test_other_gm_cannot_touch_foreign_encounter():
    gm_a, campaign_a = _make_gm_with_campaign("rt-gm-owner")
    client_a = _gm_client(gm_a, campaign_a)
    eid, state = _setup_running_encounter(client_a, campaign_a)

    gm_b, campaign_b = _make_gm_with_campaign("rt-gm-intruder")
    client_b = _gm_client(gm_b, campaign_b)
    resp = client_b.post(
        f"/api/combat/encounters/{eid}/initiative",
        json={"turn_version": state["turn_version"]},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Player access
# ---------------------------------------------------------------------------
def test_player_sees_encounter_with_foe_hp_hidden():
    gm, campaign = _make_gm_with_campaign("rt-gm-pview")
    client = _gm_client(gm, campaign)
    eid, _ = _setup_running_encounter(client, campaign)
    p_user, _player = _make_player_in_campaign("rt-player-1", campaign)

    p_client = _player_client(p_user)
    assert p_client.get(f"/api/combat/encounters/{eid}").status_code == 404
    show = client.post(
        f"/api/combat/encounters/{eid}/visibility",
        json={"visible_to_players": True},
    )
    assert show.status_code == 200
    assert show.get_json()["encounter"]["visible_to_players"] is True
    resp = p_client.get(f"/api/combat/encounters/{eid}")
    assert resp.status_code == 200
    payload = resp.get_json()
    foes = [c for c in payload["combatants"] if c["side"] == "foe"]
    assert foes
    for foe in foes:
        assert "hp_current" not in foe
        assert foe["health_state"] in ("healthy", "bloodied", "down")


def test_player_outside_campaign_gets_403():
    gm, campaign = _make_gm_with_campaign("rt-gm-pout")
    client = _gm_client(gm, campaign)
    eid, _ = _setup_running_encounter(client, campaign)

    other_gm, other_campaign = _make_gm_with_campaign("rt-gm-pother")
    p_user, _ = _make_player_in_campaign("rt-player-2", other_campaign)
    p_client = _player_client(p_user)
    assert p_client.get(f"/api/combat/encounters/{eid}").status_code == 403


def test_player_cannot_act_through_foe_combatant():
    gm, campaign = _make_gm_with_campaign("rt-gm-pact")
    client = _gm_client(gm, campaign)
    eid, state = _setup_running_encounter(client, campaign)
    client.post(
        f"/api/combat/encounters/{eid}/visibility",
        json={"visible_to_players": True},
    )
    p_user, _ = _make_player_in_campaign("rt-player-3", campaign)
    p_client = _player_client(p_user)

    resp = p_client.post(
        f"/api/combat/encounters/{eid}/move",
        json={
            "combatant_id": state["current_combatant_id"],
            "x": 5,
            "y": 5,
            "turn_version": state["turn_version"],
        },
    )
    assert resp.status_code == 400
    assert "own character" in resp.get_json()["error"]


def test_player_can_place_own_character_once():
    gm, campaign = _make_gm_with_campaign("rt-gm-place-own")
    client = _gm_client(gm, campaign)
    enc = client.post("/api/combat/encounters", json={"name": "Visible fight"}).get_json()
    eid = enc["encounter"]["id"]
    client.post(
        f"/api/combat/encounters/{eid}/visibility",
        json={"visible_to_players": True},
    )
    p_user, player = _make_player_in_campaign("rt-player-place-own", campaign)
    p_client = _player_client(p_user)
    state = p_client.get(f"/api/combat/encounters/{eid}").get_json()

    resp = p_client.post(
        f"/api/combat/encounters/{eid}/own-combatant",
        json={
            "player_id": player.id,
            "x": 4,
            "y": 5,
            "turn_version": state["turn_version"],
        },
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["combatant"]["player_id"] == player.id
    assert body["combatant"]["x"] == 4
    assert body["combatant"]["y"] == 5

    duplicate = p_client.post(
        f"/api/combat/encounters/{eid}/own-combatant",
        json={
            "player_id": player.id,
            "x": 6,
            "y": 6,
            "turn_version": body["turn_version"],
        },
    )
    assert duplicate.status_code == 400
    assert "already placed" in duplicate.get_json()["error"]


# ---------------------------------------------------------------------------
# Settings + compendium via API
# ---------------------------------------------------------------------------
def test_settings_roundtrip_via_api():
    gm, campaign = _make_gm_with_campaign("rt-gm-set")
    client = _gm_client(gm, campaign)
    resp = client.get("/api/combat/settings")
    assert resp.status_code == 200
    defaults = resp.get_json()["settings"]
    assert defaults["track_spell_slots"] is False

    resp = client.post(
        "/api/combat/settings",
        json={"settings": {"track_spell_slots": True, "diagonal_mode": "euclidean"}},
    )
    assert resp.status_code == 200
    saved = client.get("/api/combat/settings").get_json()["settings"]
    assert saved["track_spell_slots"] is True
    assert saved["diagonal_mode"] == "euclidean"

    resp = client.post(
        "/api/combat/settings", json={"settings": {"diagonal_mode": "warp"}}
    )
    assert resp.status_code == 400


def test_monster_generate_same_seed_same_stats():
    gm, campaign = _make_gm_with_campaign("rt-gm-genapi")
    client = _gm_client(gm, campaign)
    a = client.post(
        "/api/combat/monsters/generate", json={"seed": "api-seed", "challenge": 3}
    ).get_json()["monster"]
    b = client.post(
        "/api/combat/monsters/generate", json={"seed": "api-seed", "challenge": 3}
    ).get_json()["monster"]
    assert a["stats"] == b["stats"]
    assert a["name"] == b["name"]


def test_monsters_are_campaign_scoped_via_api():
    gm_a, campaign_a = _make_gm_with_campaign("rt-gm-ma")
    client_a = _gm_client(gm_a, campaign_a)
    monster = client_a.post(
        "/api/combat/monsters", json={"name": "Mine", "stats": _MONSTER_STATS}
    ).get_json()["monster"]

    gm_b, campaign_b = _make_gm_with_campaign("rt-gm-mb")
    client_b = _gm_client(gm_b, campaign_b)
    listed = client_b.get("/api/combat/monsters").get_json()["monsters"]
    assert all(m["id"] != monster["id"] for m in listed)
    resp = client_b.post(f"/api/combat/monsters/{monster['id']}/delete")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Battle tab markup gating
# ---------------------------------------------------------------------------
def test_encounter_rename_via_api():
    gm, campaign = _make_gm_with_campaign("rt-gm-rename")
    client = _gm_client(gm, campaign)
    enc = client.post("/api/combat/encounters", json={"name": "Old Name"}).get_json()
    eid = enc["encounter"]["id"]
    resp = client.post(
        "/api/combat/encounters/" + str(eid) + "/rename",
        json={"name": "New Name"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["encounter"]["name"] == "New Name"
    detail = client.get("/api/combat/encounters/" + str(eid)).get_json()
    assert detail["name"] == "New Name"


def test_encounter_rename_rejects_blank_name():
    gm, campaign = _make_gm_with_campaign("rt-gm-rename-blank")
    client = _gm_client(gm, campaign)
    eid = client.post("/api/combat/encounters", json={"name": "X"}).get_json()["encounter"]["id"]
    resp = client.post(
        "/api/combat/encounters/" + str(eid) + "/rename",
        json={"name": "   "},
    )
    assert resp.status_code == 400


def test_delete_encounter_via_api_removes_battle_state():
    gm, campaign = _make_gm_with_campaign("rt-gm-delete")
    client = _gm_client(gm, campaign)
    eid = client.post("/api/combat/encounters", json={"name": "Delete Me"}).get_json()["encounter"]["id"]
    combatant = BattleCombatant(
        encounter_id=eid,
        campaign_id=campaign.id,
        name="Goblin",
        side="foe",
        x=0,
        y=0,
        hp_max=7,
        hp_current=7,
        ac=12,
    )
    log = BattleActionLog(
        encounter_id=eid,
        campaign_id=campaign.id,
        round_number=0,
        action_type="note",
        payload_json={"text": "created"},
    )
    db.session.add_all([combatant, log])
    db.session.commit()

    resp = client.delete("/api/combat/encounters/" + str(eid))
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True
    assert client.get("/api/combat/encounters/" + str(eid)).status_code == 404
    listed = client.get("/api/combat/encounters").get_json()["encounters"]
    assert all(enc["id"] != eid for enc in listed)
    assert BattleCombatant.query.filter_by(encounter_id=eid).count() == 0
    assert BattleActionLog.query.filter_by(encounter_id=eid).count() == 0


def test_encounter_for_canvas_via_api():
    gm, campaign = _make_gm_with_campaign("rt-gm-canvas")
    client = _gm_client(gm, campaign)
    from app.models import MapCanvas

    canvas = MapCanvas(campaign_id=campaign.id, scope="world", source_type="generated")
    db.session.add(canvas)
    db.session.commit()

    lookup = client.get("/api/combat/encounters/for-canvas/" + str(canvas.id))
    assert lookup.status_code == 200
    assert lookup.get_json()["encounter"] is None

    created = client.post(
        "/api/combat/encounters/for-canvas/" + str(canvas.id),
        json={"name": "Map Fight", "x": 0.2, "y": 0.8},
    )
    assert created.status_code == 201
    body = created.get_json()
    assert body["created"] is True
    assert body["encounter"]["map_canvas_id"] == canvas.id
    assert body["encounter"]["map_x"] == 0.2
    assert body["encounter"]["map_y"] == 0.8

    again = client.post(
        "/api/combat/encounters/for-canvas/" + str(canvas.id),
        json={"x": 0.4, "y": 0.6},
    )
    assert again.status_code == 200
    assert again.get_json()["created"] is False
    assert again.get_json()["encounter"]["id"] == body["encounter"]["id"]
    assert again.get_json()["encounter"]["map_x"] == 0.4
    assert again.get_json()["encounter"]["map_y"] == 0.6

    placed = client.post(
        "/api/combat/encounters/" + str(body["encounter"]["id"]) + "/place",
        json={"map_canvas_id": canvas.id, "x": 0.1, "y": 0.3},
    )
    assert placed.status_code == 200
    assert placed.get_json()["encounter"]["map_x"] == 0.1
    assert placed.get_json()["encounter"]["map_y"] == 0.3


def test_create_encounter_can_start_placed_on_canvas():
    gm, campaign = _make_gm_with_campaign("rt-gm-canvas-create")
    client = _gm_client(gm, campaign)
    from app.models import MapCanvas

    canvas = MapCanvas(campaign_id=campaign.id, scope="world", source_type="generated")
    db.session.add(canvas)
    db.session.commit()

    resp = client.post(
        "/api/combat/encounters",
        json={
            "name": "Fresh map fight",
            "map_canvas_id": canvas.id,
            "x": 0.33,
            "y": 0.44,
        },
    )
    assert resp.status_code == 201
    encounter = resp.get_json()["encounter"]
    assert encounter["map_canvas_id"] == canvas.id
    assert encounter["map_x"] == 0.33
    assert encounter["map_y"] == 0.44


def test_battle_tab_rendered_only_for_dnd5e_dashboard():
    gm, campaign = _make_gm_with_campaign("rt-gm-tab5e", "dnd5e")
    client = _gm_client(gm, campaign)
    html = client.get("/gm/").data.decode("utf-8")
    assert 'id="players-npcs-tab-btn"' in html
    assert 'data-target="players-npcs-pane-content"' in html
    assert 'id="players-npcs-pane-content"' in html
    assert '<a href="/gm/players/" class="gm-panel-tab" id="players-npcs-tab-btn"' not in html
    assert 'id="battle-tab-btn"' in html
    assert 'title="Encounters"' in html
    assert 'id="battle-encounter-window"' in html
    assert "gm-nav-rail" in html
    assert "gm_battle.js" in html
    assert 'id="battle-pane-content"' not in html
    assert 'id="battle-encounter-menu"' in html
    assert 'id="battle-encounter-select"' not in html
    assert 'id="battle-rename-btn"' in html
    assert 'id="battle-rename-popout"' in html
    assert 'id="battle-rename-input"' in html
    assert html.index("Save name") < html.index('id="battle-rename-cancel"')
    assert "position: fixed;" in html
    assert "window.prompt('Rename encounter'" not in html
    js = Path("app/static/js/gm_battle.js").read_text(encoding="utf-8")
    css = Path("app/static/css/battle.css").read_text(encoding="utf-8")
    assert "function positionBattleRenamePopout" in js
    assert "positionBattleRenamePopout(popout, renameBtn)" in js
    assert 'id="battle-delete-popout"' in html
    assert 'id="battle-delete-confirm"' in html
    assert "battle-encounter-remove-btn" in js
    assert "Permanently delete this" in js
    assert "api('/encounters/' + encounterId, 'DELETE')" in js
    assert "setEncounterPlayerVisibility" in js
    assert "'/visibility'" in js
    assert "battle-player-visible-setting" in js
    assert "dataset.playerVisibility" in js
    assert "Show to players" in js
    assert "battle-player-visible-setting" in css
    assert "isOwnPlayerCombatant" in js
    assert "battle-token-own-player" in js
    assert "battle-token-own-player" in css
    assert "#facc15" in css
    assert ".battle-radial[hidden]" in css
    assert "display: none !important" in css
    assert "function resetBattleUiAfterMutation" in js
    assert "function hideRadialMenu" in js
    assert "battle-place-own-character-btn" in js
    assert "/own-combatant" in js
    assert "function refreshMapEncounters" in js
    assert "refreshMapEncounters();" in js
    assert 'id="map-add-encounter-controls"' in html
    assert 'id="map-encounter-select"' in html
    assert 'id="map-encounter-btn"' in html
    assert "Add Encounter" in html
    assert "No encounters available" in html
    assert "mapEncounterBtn.disabled = true" in html
    assert "refreshEncounters: function ()" in html
    assert 'id="battle-monster-cr-min"' in html
    assert 'id="battle-monster-cr-max"' in html
    assert 'id="battle-monster-select"' in html
    assert 'id="battle-monster-place-count"' in html
    assert 'id="battle-add-monster-btn"' in html
    assert 'id="battle-monster-import-btn"' in html
    assert 'id="battle-monster-import-popout"' in html
    assert 'id="battle-monster-import-file-type"' in html
    assert 'id="battle-monster-import-file-type-other"' in html
    assert 'data-import-title="Monster import request"' in html
    assert 'data-import-prompted-key="monster_import"' in html
    assert 'data-monster-source-filter="srd_only"' in html
    assert 'data-monster-source-filter="all"' in html
    assert 'data-monster-source-filter="custom_only"' in html
    assert 'SRD and Custom' in html
    assert 'Custom only' in html
    assert 'id="battle-monsters-count"' in html
    assert 'SRD only' in html
    assert 'id="market-import-btn"' in html
    assert 'id="market-import-popout"' in html
    assert 'id="market-import-file-type"' in html
    assert 'id="market-import-file-type-other"' in html
    assert 'data-import-title="Market data import request"' in html
    assert 'data-import-prompted-key="market_import"' in html
    assert 'class="battle-sidebar-heading"' in html
    assert 'id="battle-settings-btn"' in html
    assert "register player-only accounts" in html
    assert "continue into character setup" in html
    assert 'id="monsters-tab-btn"' in html
    assert 'id="monsters-pane-content"' in html
    assert 'id="battle-map-bg"' in html
    assert 'id="battle-setup-popout"' in html
    assert 'id="battle-setup-edit-btn"' in html
    assert 'loadEncounterMap' in js
    assert 'data-monster-source-filter' in js
    assert 'monsterSourceFilter' in js
    assert 'renderBattleMapBackground' in js
    assert 'pointer-events: none' in css
    assert '.battle-map-bg' in css
    assert 'var OVERSCAN = 3' in js
    assert 'function visibleCellBounds' in js
    assert 'function scheduleVirtualRender' in js
    assert 'requestAnimationFrame' in js
    assert 'battle-visible-layer' in js
    assert 'battle-board-virtual' in js
    assert 'translate3d' in js
    assert '1000 750' not in js
    assert 'function focusCameraOnCell' in js
    assert 'function loadVisibleMapChunks' in js
    assert 'function onStagePointerDown' not in js or 'initBattleViewport' in js
    assert 'battle-viewport-layer' in js or 'battle-viewport-layer' in html
    assert 'battle-encounter-window' in html
    assert 'openEncounterWindow' in js
    assert 'MapViewport' in js or 'map_viewport.js' in html
    assert 'Drag to pan' in html
    assert '/map/chunk' in js
    assert '.battle-visible-layer' in css
    assert '.battle-viewport-layer' in css or '.battle-encounter-window' in css
    assert 'overflow: hidden' in css
    assert 'min 5' in html
    assert 'max="1000"' in html

    gm2, campaign2 = _make_gm_with_campaign("rt-gm-tabgen", "generic")
    client2 = _gm_client(gm2, campaign2)
    html2 = client2.get("/gm/").data.decode("utf-8")
    assert 'id="battle-tab-btn"' not in html2
    assert 'id="monsters-tab-btn"' not in html2


def test_player_battle_templates_include_map_background():
    player_battle = Path("app/templates/Player_Battle.html").read_text(encoding="utf-8")
    player_home = Path("app/templates/Player_Home.html").read_text(encoding="utf-8")
    assert 'id="battle-map-bg"' in player_battle
    assert 'id="battle-map-bg"' in player_home
    js = Path("app/static/js/gm_battle.js").read_text(encoding="utf-8")
    assert "loadEncounterMap" in js
    assert "/encounters/' + state.encounterId + '/map'" in js


# ---------------------------------------------------------------------------
# Battle map routes
# ---------------------------------------------------------------------------
@pytest.fixture
def memory_map_storage():
    storage = battle_map_service.MemoryBattleMapStorage()
    battle_map_service.set_storage(storage)
    yield storage
    battle_map_service.set_storage(None)


def _tiny_png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color="green").save(buf, format="PNG")
    return buf.getvalue()


def _create_setup_encounter(client, **kwargs):
    payload = {"name": "Map test", **kwargs}
    resp = client.post("/api/combat/encounters", json=payload)
    assert resp.status_code == 201
    return resp.get_json()["encounter"]


def _add_monster_at(client, eid, x=0, y=0):
    monster = client.post(
        "/api/combat/monsters",
        json={"name": "Map Gob", "stats": _MONSTER_STATS},
    ).get_json()["monster"]
    client.post(
        f"/api/combat/encounters/{eid}/monsters/{monster['id']}/add",
        json={"count": 1, "x": x, "y": y},
    )


def test_create_encounter_custom_grid_and_bounds(memory_map_storage):
    gm, campaign = _make_gm_with_campaign("rt-map-grid")
    client = _gm_client(gm, campaign)
    enc = _create_setup_encounter(
        client,
        grid_width=12,
        grid_height=15,
        terrain_preset="forest",
    )
    assert enc["grid_width"] == 12
    assert enc["grid_height"] == 15
    assert enc["map"]["source_type"] == "generated"
    assert enc["map"]["terrain_preset"] == "forest"
    assert "terrain_metadata" not in enc["map"]

    for bad in (
        {"grid_width": 4},
        {"grid_height": 1001},
        {"grid_width": encounter_service.MAX_GRID_ABUSE + 1},
        {"grid_width": 0},
    ):
        resp = client.post("/api/combat/encounters", json={"name": "Bad", **bad})
        assert resp.status_code == 400

    ok_large = _create_setup_encounter(client, grid_width=500, grid_height=750)
    assert ok_large["grid_width"] == 500
    assert ok_large["grid_height"] == 750


def test_poll_payload_excludes_terrain_metadata(memory_map_storage):
    gm, campaign = _make_gm_with_campaign("rt-map-poll")
    client = _gm_client(gm, campaign)
    enc = _create_setup_encounter(client, terrain_preset="plains")
    eid = enc["id"]
    poll = client.get(f"/api/combat/encounters/{eid}").get_json()
    assert "terrain_metadata" not in poll
    assert "terrain_metadata" not in poll.get("map", {})
    heavy = client.get(f"/api/combat/encounters/{eid}/map").get_json()
    assert "terrain_metadata" in heavy["map"]
    assert heavy["map"]["terrain_metadata"]["preset"] == "plains"


def test_resize_grid_setup_only_and_token_bounds(memory_map_storage):
    gm, campaign = _make_gm_with_campaign("rt-map-resize")
    client = _gm_client(gm, campaign)
    enc = _create_setup_encounter(client, grid_width=10, grid_height=10)
    eid = enc["id"]
    _add_monster_at(client, eid, x=9, y=9)

    ok = client.post(
        f"/api/combat/encounters/{eid}/grid",
        json={"grid_width": 10, "grid_height": 10},
    )
    assert ok.status_code == 200

    shrink = client.post(
        f"/api/combat/encounters/{eid}/grid",
        json={"grid_width": 9, "grid_height": 9},
    )
    assert shrink.status_code == 400
    assert "too small" in shrink.get_json()["error"]

    grow = client.post(
        f"/api/combat/encounters/{eid}/grid",
        json={"grid_width": 12, "grid_height": 12},
    )
    assert grow.status_code == 200
    assert grow.get_json()["encounter"]["grid_width"] == 12


def test_resize_and_map_mutations_rejected_after_initiative(memory_map_storage):
    gm, campaign = _make_gm_with_campaign("rt-map-active-lock")
    client = _gm_client(gm, campaign)
    eid, state = _setup_running_encounter(client, campaign)

    for path, body in (
        (f"/api/combat/encounters/{eid}/grid", {"grid_width": 15, "grid_height": 15}),
        (f"/api/combat/encounters/{eid}/map/generate", {"terrain_preset": "river"}),
    ):
        resp = client.post(path, json=body)
        assert resp.status_code == 400
        assert "setup" in resp.get_json()["error"].lower()

    data = {"map_image": (io.BytesIO(_tiny_png_bytes()), "map.png")}
    upload = client.post(f"/api/combat/encounters/{eid}/map/upload", data=data)
    assert upload.status_code == 400


def test_upload_validates_size_and_format(memory_map_storage):
    gm, campaign = _make_gm_with_campaign("rt-map-upload-val")
    client = _gm_client(gm, campaign)
    eid = _create_setup_encounter(client)["id"]

    big = io.BytesIO(b"x" * (4 * 1024 * 1024 + 1))
    resp = client.post(
        f"/api/combat/encounters/{eid}/map/upload",
        data={"map_image": (big, "big.bin")},
    )
    assert resp.status_code == 400

    bad = client.post(
        f"/api/combat/encounters/{eid}/map/upload",
        data={"map_image": (io.BytesIO(b"not-an-image"), "bad.png")},
    )
    assert bad.status_code == 400

    ok = client.post(
        f"/api/combat/encounters/{eid}/map/upload",
        data={"map_image": (io.BytesIO(_tiny_png_bytes()), "map.png")},
    )
    assert ok.status_code == 200
    body = ok.get_json()["encounter"]
    assert body["map"]["source_type"] == "uploaded"
    assert body["map"]["has_image"] is True
    assert body["map"]["map_version"] == 1


def test_regenerate_clears_uploaded_asset_key(memory_map_storage):
    gm, campaign = _make_gm_with_campaign("rt-map-regen")
    client = _gm_client(gm, campaign)
    eid = _create_setup_encounter(client)["id"]
    client.post(
        f"/api/combat/encounters/{eid}/map/upload",
        data={"map_image": (io.BytesIO(_tiny_png_bytes()), "map.png")},
    )
    encounter = db.session.get(BattleEncounter, eid)
    old_key = encounter.map_asset_key
    assert old_key
    assert memory_map_storage.read(old_key)

    regen = client.post(
        f"/api/combat/encounters/{eid}/map/generate",
        json={"terrain_preset": "mountains"},
    )
    assert regen.status_code == 200
    db.session.refresh(encounter)
    assert encounter.map_asset_key is None
    assert encounter.map_source_type == "generated"
    assert encounter.terrain_preset == "mountains"
    assert memory_map_storage.read(old_key) is None


def test_map_version_stable_on_turn_updates(memory_map_storage):
    gm, campaign = _make_gm_with_campaign("rt-map-version")
    client = _gm_client(gm, campaign)
    eid, state = _setup_running_encounter(client, campaign)
    before = client.get(f"/api/combat/encounters/{eid}").get_json()["map"]["map_version"]

    resp = client.post(
        f"/api/combat/encounters/{eid}/end-turn",
        json={"turn_version": state["turn_version"]},
    )
    assert resp.status_code == 200
    after = client.get(f"/api/combat/encounters/{eid}").get_json()["map"]["map_version"]
    assert after == before


def test_map_version_increments_on_generate(memory_map_storage):
    gm, campaign = _make_gm_with_campaign("rt-map-version-bump")
    client = _gm_client(gm, campaign)
    eid = _create_setup_encounter(client, terrain_preset="plains")["id"]
    v0 = client.get(f"/api/combat/encounters/{eid}").get_json()["map"]["map_version"]
    client.post(
        f"/api/combat/encounters/{eid}/map/generate",
        json={"terrain_preset": "forest"},
    )
    v1 = client.get(f"/api/combat/encounters/{eid}").get_json()["map"]["map_version"]
    assert v1 == v0 + 1


def test_player_map_image_auth(memory_map_storage):
    gm, campaign = _make_gm_with_campaign("rt-map-img-auth")
    client = _gm_client(gm, campaign)
    eid = _create_setup_encounter(client)["id"]
    client.post(
        f"/api/combat/encounters/{eid}/map/upload",
        data={"map_image": (io.BytesIO(_tiny_png_bytes()), "map.png")},
    )
    client.post(
        f"/api/combat/encounters/{eid}/visibility",
        json={"visible_to_players": True},
    )

    p_user, _ = _make_player_in_campaign("rt-map-player", campaign)
    p_client = _player_client(p_user)
    assert p_client.get(f"/api/combat/encounters/{eid}/map/image").status_code == 200

    other_gm, other_campaign = _make_gm_with_campaign("rt-map-outsider")
    outsider, _ = _make_player_in_campaign("rt-map-outsider-p", other_campaign)
    o_client = _player_client(outsider)
    assert o_client.get(f"/api/combat/encounters/{eid}/map/image").status_code == 403


def test_player_can_fetch_map_metadata_when_visible(memory_map_storage):
    gm, campaign = _make_gm_with_campaign("rt-map-player-meta")
    client = _gm_client(gm, campaign)
    eid = _create_setup_encounter(client, terrain_preset="village")["id"]
    client.post(
        f"/api/combat/encounters/{eid}/visibility",
        json={"visible_to_players": True},
    )
    p_user, _ = _make_player_in_campaign("rt-map-meta-p", campaign)
    p_client = _player_client(p_user)
    assert p_client.get(f"/api/combat/encounters/{eid}").status_code == 200
    meta = p_client.get(f"/api/combat/encounters/{eid}/map").get_json()
    assert meta["map"]["terrain_metadata"]["preset"] == "village"


def test_upload_commit_failure_keeps_prior_asset(memory_map_storage):
    gm, campaign = _make_gm_with_campaign("rt-map-commit-fail")
    client = _gm_client(gm, campaign)
    eid = _create_setup_encounter(client)["id"]
    first = client.post(
        f"/api/combat/encounters/{eid}/map/upload",
        data={"map_image": (io.BytesIO(_tiny_png_bytes()), "first.png")},
    )
    assert first.status_code == 200
    encounter = db.session.get(BattleEncounter, eid)
    old_key = encounter.map_asset_key
    assert memory_map_storage.read(old_key)

    with patch.object(db.session, "commit", side_effect=RuntimeError("commit failed")):
        resp = client.post(
            f"/api/combat/encounters/{eid}/map/upload",
            data={"map_image": (io.BytesIO(_tiny_png_bytes()), "second.png")},
        )
    assert resp.status_code == 500
    db.session.rollback()
    db.session.refresh(encounter)
    assert encounter.map_asset_key == old_key
    assert memory_map_storage.read(old_key) is not None


def test_storage_write_failure_rolls_back_without_version_bump(memory_map_storage):
    gm, campaign = _make_gm_with_campaign("rt-map-storage-fail")
    client = _gm_client(gm, campaign)
    eid = _create_setup_encounter(client, terrain_preset="road")["id"]
    version_before = client.get(f"/api/combat/encounters/{eid}").get_json()["map"]["map_version"]

    class FailingStorage(battle_map_service.MemoryBattleMapStorage):
        def write(self, key, data):
            raise OSError("storage unavailable")

    battle_map_service.set_storage(FailingStorage())
    resp = client.post(
        f"/api/combat/encounters/{eid}/map/upload",
        data={"map_image": (io.BytesIO(_tiny_png_bytes()), "map.png")},
    )
    assert resp.status_code == 400
    version_after = client.get(f"/api/combat/encounters/{eid}").get_json()["map"]["map_version"]
    assert version_after == version_before


def test_orphan_asset_discovery(memory_map_storage):
    orphan_key = "encounter_0_deadbeef.webp"
    memory_map_storage.write(orphan_key, b"webp")
    gm, campaign = _make_gm_with_campaign("rt-map-orphan")
    eid = _create_setup_encounter(_gm_client(gm, campaign))["id"]
    encounter = db.session.get(BattleEncounter, eid)
    encounter.map_asset_key = f"encounter_{eid}_live.webp"
    memory_map_storage.write(encounter.map_asset_key, b"live")
    db.session.commit()
    orphans = battle_map_service.find_orphan_asset_keys()
    assert orphan_key in orphans
    assert encounter.map_asset_key not in orphans


def test_grid_dimension_integer_validation(memory_map_storage):
    gm, campaign = _make_gm_with_campaign("rt-grid-int-val")
    client = _gm_client(gm, campaign)
    for bad in (
        {"grid_width": 10.5},
        {"grid_width": "1e6"},
        {"grid_width": True},
        {"grid_height": "-3"},
        {"grid_width": "12.0"},
    ):
        resp = client.post("/api/combat/encounters", json={"name": "Bad", **bad})
        assert resp.status_code == 400


def test_chunked_map_manifest_and_player_access(memory_map_storage):
    gm, campaign = _make_gm_with_campaign("rt-map-chunk")
    client = _gm_client(gm, campaign)
    enc = _create_setup_encounter(
        client,
        grid_width=200,
        grid_height=200,
        terrain_preset="forest",
    )
    eid = enc["id"]
    meta = client.get(f"/api/combat/encounters/{eid}/map").get_json()["map"]
    assert meta["chunked"] is True
    assert meta.get("terrain_metadata") == {}
    assert meta["chunk_size"] == battle_map_service.CHUNK_CELL_SIZE

    chunk = client.get(
        f"/api/combat/encounters/{eid}/map/chunk?chunk_x=0&chunk_y=0"
    ).get_json()["map_chunk"]
    assert chunk["chunk_x"] == 0
    assert chunk["chunk_y"] == 0
    assert "terrain_metadata" in chunk
    assert "features" in chunk["terrain_metadata"]

    client.post(
        f"/api/combat/encounters/{eid}/visibility",
        json={"visible_to_players": True},
    )
    p_user, _ = _make_player_in_campaign("rt-map-chunk-p", campaign)
    p_client = _player_client(p_user)
    player_meta = p_client.get(f"/api/combat/encounters/{eid}/map").get_json()["map"]
    assert player_meta["chunked"] is True
    assert player_meta.get("terrain_metadata") == {}
    assert p_client.get(
        f"/api/combat/encounters/{eid}/map/chunk?chunk_x=1&chunk_y=1"
    ).status_code == 200

    other_gm, other_campaign = _make_gm_with_campaign("rt-map-chunk-outsider")
    outsider, _ = _make_player_in_campaign("rt-map-chunk-outsider-p", other_campaign)
    assert _player_client(outsider).get(
        f"/api/combat/encounters/{eid}/map/chunk?chunk_x=0&chunk_y=0"
    ).status_code == 403


def test_chunk_route_rejects_non_chunked_map(memory_map_storage):
    gm, campaign = _make_gm_with_campaign("rt-map-chunk-small")
    client = _gm_client(gm, campaign)
    eid = _create_setup_encounter(client, grid_width=20, grid_height=20)["id"]
    resp = client.get(f"/api/combat/encounters/{eid}/map/chunk?chunk_x=0&chunk_y=0")
    assert resp.status_code == 400


def test_chunk_route_rejects_out_of_range_coordinates(memory_map_storage):
    gm, campaign = _make_gm_with_campaign("rt-map-chunk-range")
    client = _gm_client(gm, campaign)
    eid = _create_setup_encounter(client, grid_width=200, grid_height=200)["id"]
    resp = client.get(f"/api/combat/encounters/{eid}/map/chunk?chunk_x=999&chunk_y=0")
    assert resp.status_code == 400


def test_map_regenerate_invalidates_chunk_payload(memory_map_storage):
    gm, campaign = _make_gm_with_campaign("rt-map-chunk-version")
    client = _gm_client(gm, campaign)
    eid = _create_setup_encounter(
        client,
        grid_width=200,
        grid_height=200,
        terrain_preset="plains",
    )["id"]
    before = client.get(
        f"/api/combat/encounters/{eid}/map/chunk?chunk_x=0&chunk_y=0"
    ).get_json()["map_chunk"]
    client.post(
        f"/api/combat/encounters/{eid}/map/generate",
        json={"terrain_preset": "mountains"},
    )
    after = client.get(
        f"/api/combat/encounters/{eid}/map/chunk?chunk_x=0&chunk_y=0"
    ).get_json()["map_chunk"]
    assert after["map_version"] == before["map_version"] + 1


def test_virtual_grid_static_assertions():
    js = Path("app/static/js/gm_battle.js").read_text(encoding="utf-8")
    css = Path("app/static/css/battle.css").read_text(encoding="utf-8")
    assert "c.x < x0 || c.x >= x1 || c.y < y0 || c.y >= y1" in js
    assert "battle-board-virtual" in js
    assert "setAttribute('viewBox', bounds.x0" in js
    assert "appendFeaturesToSvg" in js
    assert "p[0] * gw" in js
    assert ".battle-board-virtual .battle-tile" in css
    assert "position: absolute" in css

