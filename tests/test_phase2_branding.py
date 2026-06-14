"""Phase 2 branding: changelog, retired routes, thank-you redirect, copy markers."""

from __future__ import annotations

import pytest

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import (
    BattleEncounter,
    Campaign,
    City,
    GMProfile,
    Item,
    MapCanvas,
    MapMarker,
    MapPointOfInterest,
    Player,
    PlayerCharacterSheet,
    Shop,
    ShopInventory,
    User,
)
from tests.session_helpers import seed_client_session


@pytest.fixture(autouse=True)
def _db_tables():
    flask_app.config["WTF_CSRF_ENABLED"] = False
    with flask_app.app_context():
        db.create_all()
        yield
        db.session.rollback()
        db.drop_all()


def _player_with_campaign():
    gm_user = User(username="gm-p2", password="x", role="GM")
    gm_user.set_password("Secret1!")
    db.session.add(gm_user)
    db.session.flush()
    gm_profile = GMProfile(user_id=gm_user.id)
    db.session.add(gm_profile)
    db.session.flush()
    campaign = Campaign(
        gm_profile_id=gm_profile.id,
        name="Brand Camp",
        system_type="generic",
        is_active=True,
    )
    db.session.add(campaign)
    db.session.flush()
    player_user = User(username="player-p2", password="x", role="Player")
    player_user.set_password("Secret1!")
    db.session.add(player_user)
    db.session.flush()
    player = Player(
        user_id=player_user.id,
        campaign_id=campaign.id,
        is_npc=False,
        currency=100,
    )
    db.session.add(player)
    db.session.commit()
    return player_user, player, campaign


def test_docs_changelog_section_renders(client):
    resp = client.get("/docs?section=changelog")
    assert resp.status_code == 200
    assert b'id="section-changelog"' in resp.data
    assert b"Patch Notes" in resp.data
    assert b"Alpha 1.1 Map and Encounter Update" in resp.data
    assert b"Alpha 1.2 GM Workspace Update" in resp.data
    assert b'id="patch-1-2-4"' in resp.data
    assert b"population and species visibility" in resp.data
    assert b"Species Compendium" in resp.data
    assert b"Monster Compendium" in resp.data
    assert b"character creation wizard" in resp.data
    assert b"Alpha 1.0" in resp.data
    assert b"Release notes for Econo-Forge Alpha" in resp.data
    assert b"Alpha status" in resp.data


def test_thank_you_redirects_to_access_request(client):
    resp = client.get("/thank-you", follow_redirects=False)
    assert resp.status_code in (301, 302)
    assert "/access-request" in (resp.location or "")


def test_legacy_player_routes_redirect_to_home(client):
    user, player, _campaign = _player_with_campaign()
    seed_client_session(
        client,
        user,
        campaign_id=player.campaign_id,
        player_id=player.id,
        session_mode="player",
    )
    for path in ("/player/shops", "/player/cities", "/player/market"):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code in (301, 302)
        assert "/player/home" in (resp.location or "")


def test_player_home_uses_browse_shops_not_market_route(client):
    user, player, _campaign = _player_with_campaign()
    seed_client_session(
        client,
        user,
        campaign_id=player.campaign_id,
        player_id=player.id,
        session_mode="player",
    )
    resp = client.get("/player/home")
    assert resp.status_code == 200
    assert b"Browse Shops" in resp.data
    assert b"#player-shops-browse" in resp.data
    assert b'id="player-character-tab"' in resp.data
    assert b'id="player-spells-tab"' in resp.data
    assert b'id="player-inventory-tab"' in resp.data
    assert b'id="player-map-tab"' in resp.data
    assert b'id="player-market-tab"' in resp.data
    assert b'id="player-character-panel"' in resp.data
    assert b'id="player-spells-panel"' in resp.data
    assert b'id="player-inventory-panel"' in resp.data
    assert b'id="player-map-panel"' in resp.data
    assert b'id="player-market-panel"' in resp.data
    assert b'id="player-map-stage"' in resp.data
    assert b'class="map-stage"' in resp.data
    assert b'id="player-map-bg-image"' in resp.data
    assert b'class="map-bg-image"' in resp.data
    assert b'id="player-map-gen-bg"' in resp.data
    assert b'class="map-gen-bg"' in resp.data
    assert b'id="player-map-markers"' in resp.data
    assert b'class="map-marker-layer"' in resp.data
    assert b"grid-template-columns: 240px minmax(0, 1fr)" in resp.data
    assert b"min-height: 558px" in resp.data
    assert b'className = "map-marker"' in resp.data
    assert b'className = "map-marker poi"' in resp.data
    assert b'className = "map-entity-popout"' in resp.data
    assert b'className = "map-poi-popout"' in resp.data
    assert b'className = "map-encounter-popout"' in resp.data
    assert b".map-encounter-popout {" in resp.data
    assert b'id="playerSpellsContent"' in resp.data
    assert b"renderPlayerSpellsPanel(data.spell_details || {})" in resp.data
    assert b"showPurchaseToast(data.message || \"Purchase complete.\", \"success\")" in resp.data
    assert b"setTimeout(function () { location.reload(); }, 3000)" in resp.data
    assert b"Add Region" not in resp.data
    assert b"Import market data" not in resp.data
    assert b"Supply On" not in resp.data
    assert b"Debt Off" not in resp.data
    assert b"player.view_market" not in resp.data


def test_player_character_data_includes_class_available_spells(client):
    user, player, campaign = _player_with_campaign()
    campaign.system_type = "dnd5e"
    db.session.add(
        PlayerCharacterSheet(
            player_id=player.id,
            campaign_id=campaign.id,
            sheet_json={
                "system_type": "dnd5e",
                "name": "Spell Tester",
                "class_name": "Wizard",
                "level": 1,
                "creation": {"class_key": "wizard"},
                "abilities": {"int": 16},
                "defenses": {"hp_max": 8, "hp_current": 8, "ac": 12},
                "spells": {},
            },
        )
    )
    db.session.commit()
    seed_client_session(
        client,
        user,
        campaign_id=player.campaign_id,
        player_id=player.id,
        session_mode="player",
    )

    resp = client.get("/player/character-data")
    assert resp.status_code == 200
    spell_details = resp.get_json()["spell_details"]
    by_key = {row["key"]: row for row in spell_details["class_available"]}
    assert spell_details["class_key"] == "wizard"
    assert "fire_bolt" in by_key
    assert "magic_missile" in by_key


def test_player_home_shows_encounter_tab_for_dnd5e_campaign(client):
    user, player, campaign = _player_with_campaign()
    campaign.system_type = "dnd5e"
    hidden = BattleEncounter(
        campaign_id=campaign.id,
        name="Hidden Ambush",
        status="setup",
        visible_to_players=False,
    )
    encounter = BattleEncounter(
        campaign_id=campaign.id,
        name="Road Ambush",
        status="setup",
        visible_to_players=True,
    )
    db.session.add_all([hidden, encounter])
    db.session.commit()
    seed_client_session(
        client,
        user,
        campaign_id=player.campaign_id,
        player_id=player.id,
        session_mode="player",
    )
    resp = client.get("/player/home")
    assert resp.status_code == 200
    assert b'id="player-encounter-tab"' in resp.data
    assert b">Encounters</button>" in resp.data
    assert b'id="player-encounter-panel"' in resp.data
    assert b"Encounters: Road Ambush" in resp.data
    assert b"Hidden Ambush" not in resp.data
    assert b'data-player-encounter-id="' not in resp.data
    assert b'id="battle-round-label"' not in resp.data
    assert b'id="battle-place-own-character-btn"' in resp.data
    assert b"id=\"battle-stage\"" in resp.data
    assert b"role: 'player'" in resp.data
    assert b"ownPlayerIds" in resp.data
    assert b"initialEncounterId:" in resp.data
    assert b"js/gm_battle.js" in resp.data
    assert b'id="battle-create-btn"' not in resp.data
    assert b'id="battle-add-monster-btn"' not in resp.data
    assert b'id="battle-rename-btn"' not in resp.data


def test_player_readonly_map_apis_scope_to_active_campaign(client):
    user, player, campaign = _player_with_campaign()
    city = City(
        name="Rivermouth",
        size="Town",
        population=1000,
        campaign_id=campaign.id,
    )
    shop = Shop(campaign_id=campaign.id, name="Rivermouth Market", type="General")
    shop.cities.append(city)
    db.session.add_all([city, shop])
    db.session.flush()
    world_canvas = MapCanvas(campaign_id=campaign.id, scope="world")
    city_canvas = MapCanvas(campaign_id=campaign.id, scope="city", city_id=city.city_id)
    db.session.add_all([world_canvas, city_canvas])
    db.session.flush()
    db.session.add_all(
        [
            MapMarker(
                canvas_id=world_canvas.id,
                campaign_id=campaign.id,
                entity_type="city",
                city_id=city.city_id,
                x=0.4,
                y=0.5,
            ),
            MapMarker(
                canvas_id=city_canvas.id,
                campaign_id=campaign.id,
                entity_type="shop",
                shop_id=shop.shop_id,
                x=0.6,
                y=0.7,
            ),
            MapPointOfInterest(
                canvas_id=world_canvas.id,
                campaign_id=campaign.id,
                label="Visible Shrine",
                note="Players can see this.",
                x=0.2,
                y=0.3,
                visible_to_players=True,
            ),
            MapPointOfInterest(
                canvas_id=world_canvas.id,
                campaign_id=campaign.id,
                label="Hidden Shrine",
                note="GM secret.",
                x=0.25,
                y=0.35,
                visible_to_players=False,
            ),
            BattleEncounter(
                campaign_id=campaign.id,
                name="Visible Map Ambush",
                status="setup",
                visible_to_players=True,
                map_canvas_id=world_canvas.id,
                map_x=0.7,
                map_y=0.8,
            ),
            BattleEncounter(
                campaign_id=campaign.id,
                name="Hidden Map Ambush",
                status="setup",
                visible_to_players=False,
                map_canvas_id=world_canvas.id,
                map_x=0.75,
                map_y=0.85,
            ),
        ]
    )

    other_gm = User(username="gm-other-map", password="x", role="GM")
    other_gm.set_password("Secret1!")
    db.session.add(other_gm)
    db.session.flush()
    other_profile = GMProfile(user_id=other_gm.id)
    db.session.add(other_profile)
    db.session.flush()
    other_campaign = Campaign(
        gm_profile_id=other_profile.id,
        name="Other Camp",
        system_type="generic",
        is_active=True,
    )
    db.session.add(other_campaign)
    db.session.flush()
    other_city = City(name="Other City", campaign_id=other_campaign.id)
    other_canvas = MapCanvas(campaign_id=other_campaign.id, scope="world")
    db.session.add_all([other_city, other_canvas])
    db.session.commit()

    seed_client_session(
        client,
        user,
        campaign_id=player.campaign_id,
        player_id=player.id,
        session_mode="player",
    )

    world_resp = client.get("/player/maps/world")
    assert world_resp.status_code == 200
    world = world_resp.get_json()
    assert any(
        entity["name"] == "Rivermouth" and entity["is_on_map"]
        for entity in world["entities"]
    )
    assert [poi["label"] for poi in world["points_of_interest"]] == ["Visible Shrine"]
    assert [encounter["name"] for encounter in world["encounters"]] == ["Visible Map Ambush"]

    city_resp = client.get(f"/player/maps/cities/{city.city_id}")
    assert city_resp.status_code == 200
    city_payload = city_resp.get_json()
    assert city_payload["city"]["name"] == "Rivermouth"
    assert any(entity["name"] == "Rivermouth Market" for entity in city_payload["entities"])
    assert city_payload["points_of_interest"] == []
    assert city_payload["encounters"] == []

    assert client.get(f"/player/maps/cities/{other_city.city_id}").status_code == 404
    assert client.get(f"/player/maps/image/{other_canvas.id}").status_code == 404


def test_player_market_overview_api_uses_active_campaign(client):
    user, player, campaign = _player_with_campaign()
    city = City(name="Trade City", campaign_id=campaign.id)
    shop = Shop(campaign_id=campaign.id, name="Trade Shop", type="General")
    shop.cities.append(city)
    item = Item(
        campaign_id=campaign.id,
        name="Iron Ration",
        type="Provision",
        rarity="Common",
        base_price=2,
    )
    db.session.add_all([city, shop, item])
    db.session.flush()
    db.session.add(
        ShopInventory(
            shop_id=shop.shop_id,
            item_id=item.item_id,
            campaign_id=campaign.id,
            stock=8,
            dynamic_price=3,
        )
    )
    db.session.commit()
    seed_client_session(
        client,
        user,
        campaign_id=player.campaign_id,
        player_id=player.id,
        session_mode="player",
    )

    resp = client.get("/player/api/market-overview")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["items"][0]["name"] == "Iron Ration"
    assert data["items"][0]["current_avg_price"] == 3.0


def test_404_page_shows_econo_forge_branding(client):
    resp = client.get("/this-route-does-not-exist-phase2")
    assert resp.status_code == 404
    assert b"Page not found" in resp.data
    assert b"Econo-Forge" in resp.data or b"Back to home" in resp.data


def test_access_request_copy_uses_registration_key(client):
    resp = client.get("/access-request")
    assert resp.status_code == 200
    assert b"registration key" in resp.data.lower()


def test_docs_faq_explains_auto_access_vs_admin_triage(client):
    resp = client.get("/docs?section=faq")
    assert resp.status_code == 200
    assert b"auto-issues your registration key" in resp.data.lower() or b"auto-issues" in resp.data.lower()
    assert b"Manual Triage" in resp.data or b"admin triage" in resp.data.lower()
    assert b"What are the Species and Monster Compendiums?" in resp.data
    assert b"Where does city population by species appear?" in resp.data
    assert b"How does D&amp;D 5e character creation work?" in resp.data
    assert b"Why can't players see a map point or encounter?" in resp.data
    assert b"Show to players" in resp.data
    assert b"Can players use the battle board?" in resp.data
