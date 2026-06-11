"""Tests for the GM interactive map API (/gm/maps/*) and dashboard markup."""

from __future__ import annotations

import io

import pytest
from PIL import Image
from werkzeug.datastructures import MultiDict

from app import app as flask_app
from pathlib import Path
from app.extensions import db
import app.models  # noqa: F401
from app.models import (
    Campaign,
    CampaignWorldConfig,
    City,
    Item,
    MapCanvas,
    MapMarker,
    MapPointOfInterest,
    Shop,
    ShopInventory,
    User,
)
from app.services import gm_maps
from app.services.world_generator import validator as wg_validator
from app.services.world_generator.defaults import RANGE_SETTINGS
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


def _make_gm_with_campaign(username: str):
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
        system_type="generic",
        is_active=True,
        current_game_day=1,
    )
    db.session.add(campaign)
    db.session.commit()
    return user, campaign


def _add_city(campaign: Campaign, name: str) -> City:
    city = City(name=name, size="Town", population=1000, campaign_id=campaign.id)
    db.session.add(city)
    db.session.commit()
    return city


def _add_shop(campaign: Campaign, city: City | None, name: str) -> Shop:
    shop = Shop(campaign_id=campaign.id, name=name, type="General")
    if city is not None:
        shop.cities.append(city)
    db.session.add(shop)
    db.session.commit()
    return shop


def _gm_client(user, campaign):
    client = flask_app.test_client()
    seed_client_session(client, user, campaign_id=campaign.id)
    return client


def _tiny_png() -> io.BytesIO:
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), color=(40, 80, 120)).save(buf, format="PNG")
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Auth and payloads
# ---------------------------------------------------------------------------
def test_world_map_requires_login():
    client = flask_app.test_client()
    resp = client.get("/gm/maps/world")
    assert resp.status_code in (302, 401)


def test_marker_post_requires_login():
    client = flask_app.test_client()
    resp = client.post("/gm/maps/markers", json={})
    assert resp.status_code in (302, 401)


def test_world_map_payload_for_gm_with_campaign():
    user, campaign = _make_gm_with_campaign("gm-map-1")
    city = _add_city(campaign, "Rivermouth")
    client = _gm_client(user, campaign)

    resp = client.get("/gm/maps/world")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["canvas"]["scope"] == "world"
    assert data["canvas"]["source_type"] == "generated"
    assert data["canvas"]["generation"].get("features")
    assert data["canvas"]["generation"]["schema_version"] == gm_maps.GENERATION_SCHEMA_VERSION
    feature_types = {
        feature["type"] for feature in data["canvas"]["generation"]["features"]
    }
    assert {"landmass", "river", "trade_route", "mountain_range", "forest"} <= feature_types
    names = [e["name"] for e in data["entities"]]
    assert "Rivermouth" in names
    entity = next(e for e in data["entities"] if e["id"] == city.city_id)
    assert entity["is_on_map"] is False
    assert entity["is_suggested"] is False
    assert entity["x"] is None and entity["y"] is None

    # Lazily-created canvas was committed.
    assert MapCanvas.query.filter_by(campaign_id=campaign.id, scope="world").count() == 1


def test_world_map_city_entity_includes_summary_card_data():
    user, campaign = _make_gm_with_campaign("gm-map-city-card")
    city = _add_city(campaign, "Abbey-on-Marsh-fell")
    city.population = 1000
    shop_a = _add_shop(campaign, city, "Abbey Market")
    shop_b = _add_shop(campaign, city, "Marsh Exchange")
    sword = Item(
        name="Silver Sword",
        type="Weapon",
        rarity="Rare",
        base_price=200,
        campaign_id=campaign.id,
    )
    grain = Item(
        name="Barley",
        type="Trade Good",
        rarity="Common",
        base_price=2,
        campaign_id=campaign.id,
    )
    db.session.add_all([sword, grain])
    db.session.flush()
    db.session.add_all(
        [
            ShopInventory(
                shop_id=shop_a.shop_id,
                item_id=sword.item_id,
                campaign_id=campaign.id,
                stock=2,
                dynamic_price=500,
            ),
            ShopInventory(
                shop_id=shop_b.shop_id,
                item_id=sword.item_id,
                campaign_id=campaign.id,
                stock=4,
                dynamic_price=700,
            ),
            ShopInventory(
                shop_id=shop_a.shop_id,
                item_id=grain.item_id,
                campaign_id=campaign.id,
                stock=80,
                dynamic_price=3,
            ),
        ]
    )
    db.session.add(
        CampaignWorldConfig(
            campaign_id=campaign.id,
            settings_json={
                "species_distribution": [
                    {"name": "Human", "percent": 60.0, "source": "default"},
                    {"name": "Elf", "percent": 40.0, "source": "default"},
                ]
            },
            schema_version=2,
        )
    )
    db.session.commit()
    client = _gm_client(user, campaign)

    resp = client.get("/gm/maps/world")

    assert resp.status_code == 200
    entity = next(e for e in resp.get_json()["entities"] if e["id"] == city.city_id)
    summary = entity["summary"]
    assert summary["population"] == 1000
    assert summary["species_population"] == [
        {"key": "human", "name": "Human", "percent": 60.0, "population": 600},
        {"key": "elf", "name": "Elf", "percent": 40.0, "population": 400},
    ]
    assert summary["top_goods_by_price"][0]["name"] == "Silver Sword"
    assert summary["top_goods_by_price"][0]["average_price"] == 600.0
    assert summary["top_goods_by_average_volume"][0]["name"] == "Barley"
    assert summary["top_goods_by_average_volume"][0]["average_volume"] == 80.0


def test_edit_city_saves_population_by_species():
    user, campaign = _make_gm_with_campaign("gm-city-species-edit")
    city = _add_city(campaign, "Riverhold")
    db.session.add(
        CampaignWorldConfig(
            campaign_id=campaign.id,
            settings_json={
                "species_distribution": [
                    {"name": "Human", "percent": 75.0, "source": "default"},
                    {"name": "Elf", "percent": 25.0, "source": "default"},
                ]
            },
            schema_version=2,
        )
    )
    db.session.commit()
    client = _gm_client(user, campaign)

    form = client.get(f"/gm/cities/edit/{city.city_id}")
    assert form.status_code == 200
    html = form.data.decode("utf-8")
    assert "Population by Species" in html
    assert 'name="species_human_population"' in html
    assert 'name="species_elf_population"' in html

    resp = client.post(
        f"/gm/cities/edit/{city.city_id}",
        data={
            "name": "Riverhold",
            "size": "Small Town",
            "population": "999",
            "region": "Trade Crossroads",
            "species_key": ["human", "elf"],
            "species_human_name": "Human",
            "species_human_population": "800",
            "species_elf_name": "Elf",
            "species_elf_population": "200",
        },
        follow_redirects=False,
    )

    assert resp.status_code == 302
    db.session.refresh(city)
    assert city.population == 1000
    cfg = CampaignWorldConfig.query.filter_by(campaign_id=campaign.id).one()
    rows = cfg.settings_json["city_species_population"][str(city.city_id)]
    assert rows == [
        {"key": "human", "name": "Human", "population": 800, "percent": 80.0},
        {"key": "elf", "name": "Elf", "population": 200, "percent": 20.0},
    ]

    summary = next(
        e
        for e in client.get("/gm/maps/world").get_json()["entities"]
        if e["id"] == city.city_id
    )["summary"]
    assert summary["species_population"] == rows


def test_world_map_requires_active_campaign():
    user, campaign = _make_gm_with_campaign("gm-map-nocamp")
    client = flask_app.test_client()
    seed_client_session(client, user)  # no campaign_id in session
    resp = client.get("/gm/maps/world")
    assert resp.status_code == 400


def test_city_map_payload_only_includes_attached_shops():
    user, campaign = _make_gm_with_campaign("gm-map-2")
    city_a = _add_city(campaign, "Aldergate")
    city_b = _add_city(campaign, "Branholm")
    shop = _add_shop(campaign, city_a, "Alder Smithy")
    _add_shop(campaign, city_b, "Bran Apothecary")
    hammer = Item(
        name="Guild Hammer",
        type="Tool",
        rarity="Uncommon",
        base_price=30,
        campaign_id=campaign.id,
    )
    nails = Item(
        name="Nails",
        type="Trade Good",
        rarity="Common",
        base_price=1,
        campaign_id=campaign.id,
    )
    db.session.add_all([hammer, nails])
    db.session.flush()
    db.session.add_all(
        [
            ShopInventory(
                shop_id=shop.shop_id,
                item_id=hammer.item_id,
                campaign_id=campaign.id,
                stock=3,
                dynamic_price=75,
            ),
            ShopInventory(
                shop_id=shop.shop_id,
                item_id=nails.item_id,
                campaign_id=campaign.id,
                stock=90,
                dynamic_price=2,
            ),
        ]
    )
    db.session.commit()

    client = _gm_client(user, campaign)
    resp = client.get(f"/gm/maps/cities/{city_a.city_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["canvas"]["scope"] == "city"
    assert data["city"]["id"] == city_a.city_id
    feature_types = {
        feature["type"] for feature in data["canvas"]["generation"]["features"]
    }
    assert {"city_wall", "district", "road", "plaza"} <= feature_types
    names = [e["name"] for e in data["entities"]]
    assert names == ["Alder Smithy"]
    shop_entity = data["entities"][0]
    assert shop_entity["summary"]["top_goods_by_price"][0]["name"] == "Guild Hammer"
    assert shop_entity["summary"]["top_goods_by_average_volume"][0]["name"] == "Nails"


def test_generated_map_metadata_is_upgraded_when_old_schema_seen():
    user, campaign = _make_gm_with_campaign("gm-map-upgrade")
    client = _gm_client(user, campaign)
    canvas = MapCanvas(
        campaign_id=campaign.id,
        scope="world",
        source_type="generated",
        generation_json={
            "schema_version": 1,
            "seed": 123,
            "scope": "world",
            "palette": "parchment",
            "features": [{"type": "landmass", "x": 0.5, "y": 0.5, "size": 0.2}],
        },
    )
    db.session.add(canvas)
    db.session.commit()

    data = client.get("/gm/maps/world").get_json()
    assert data["canvas"]["generation"]["schema_version"] == gm_maps.GENERATION_SCHEMA_VERSION
    assert any(
        feature["type"] == "river" for feature in data["canvas"]["generation"]["features"]
    )


def test_city_map_cross_campaign_404():
    user, campaign = _make_gm_with_campaign("gm-map-3")
    _other_user, other_campaign = _make_gm_with_campaign("gm-map-3b")
    foreign_city = _add_city(other_campaign, "Foreign City")

    client = _gm_client(user, campaign)
    resp = client.get(f"/gm/maps/cities/{foreign_city.city_id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Marker upsert
# ---------------------------------------------------------------------------
def _world_canvas_id(client):
    return client.get("/gm/maps/world").get_json()["canvas"]["id"]


def test_save_city_marker_valid_coords():
    user, campaign = _make_gm_with_campaign("gm-marker-1")
    city = _add_city(campaign, "Pinholt")
    client = _gm_client(user, campaign)
    canvas_id = _world_canvas_id(client)

    resp = client.post(
        "/gm/maps/markers",
        json={
            "canvas_id": canvas_id,
            "entity_type": "city",
            "entity_id": city.city_id,
            "x": 0.45,
            "y": 0.82,
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    marker = MapMarker.query.filter_by(canvas_id=canvas_id, city_id=city.city_id).one()
    assert marker.x == pytest.approx(0.45)
    assert marker.y == pytest.approx(0.82)

    # Payload reflects the saved (non-suggested) position after reload.
    data = client.get("/gm/maps/world").get_json()
    entity = next(e for e in data["entities"] if e["id"] == city.city_id)
    assert entity["is_on_map"] is True
    assert entity["is_suggested"] is False
    assert entity["x"] == pytest.approx(0.45)


def test_remove_city_marker_from_world_map():
    user, campaign = _make_gm_with_campaign("gm-marker-remove")
    city = _add_city(campaign, "Removeton")
    client = _gm_client(user, campaign)
    canvas_id = _world_canvas_id(client)
    assert client.post(
        "/gm/maps/markers",
        json={
            "canvas_id": canvas_id,
            "entity_type": "city",
            "entity_id": city.city_id,
            "x": 0.25,
            "y": 0.75,
        },
    ).status_code == 200

    resp = client.post(
        "/gm/maps/markers/remove",
        json={
            "canvas_id": canvas_id,
            "entity_type": "city",
            "entity_id": city.city_id,
        },
    )
    assert resp.status_code == 200
    assert resp.get_json()["removed"] is True
    assert MapMarker.query.count() == 0
    entity = next(
        e for e in client.get("/gm/maps/world").get_json()["entities"]
        if e["id"] == city.city_id
    )
    assert entity["is_on_map"] is False
    assert entity["x"] is None


def test_repeated_marker_save_updates_instead_of_duplicating():
    user, campaign = _make_gm_with_campaign("gm-marker-2")
    city = _add_city(campaign, "Duplicheck")
    client = _gm_client(user, campaign)
    canvas_id = _world_canvas_id(client)

    for x in (0.2, 0.7):
        resp = client.post(
            "/gm/maps/markers",
            json={
                "canvas_id": canvas_id,
                "entity_type": "city",
                "entity_id": city.city_id,
                "x": x,
                "y": 0.5,
            },
        )
        assert resp.status_code == 200

    markers = MapMarker.query.filter_by(canvas_id=canvas_id, city_id=city.city_id).all()
    assert len(markers) == 1
    assert markers[0].x == pytest.approx(0.7)


def test_marker_rejects_out_of_bounds_coords():
    user, campaign = _make_gm_with_campaign("gm-marker-3")
    city = _add_city(campaign, "Boundsville")
    client = _gm_client(user, campaign)
    canvas_id = _world_canvas_id(client)

    for x, y in ((1.5, 0.5), (-0.1, 0.5), (0.5, 2.0)):
        resp = client.post(
            "/gm/maps/markers",
            json={
                "canvas_id": canvas_id,
                "entity_type": "city",
                "entity_id": city.city_id,
                "x": x,
                "y": y,
            },
        )
        assert resp.status_code == 400
    assert MapMarker.query.count() == 0


def test_marker_rejects_non_numeric_coords():
    user, campaign = _make_gm_with_campaign("gm-marker-4")
    city = _add_city(campaign, "Numville")
    client = _gm_client(user, campaign)
    canvas_id = _world_canvas_id(client)

    resp = client.post(
        "/gm/maps/markers",
        json={
            "canvas_id": canvas_id,
            "entity_type": "city",
            "entity_id": city.city_id,
            "x": "abc",
            "y": 0.5,
        },
    )
    assert resp.status_code == 400


def test_marker_cross_campaign_city_404():
    user, campaign = _make_gm_with_campaign("gm-marker-5")
    _other_user, other_campaign = _make_gm_with_campaign("gm-marker-5b")
    foreign_city = _add_city(other_campaign, "Not Yours")
    client = _gm_client(user, campaign)
    canvas_id = _world_canvas_id(client)

    resp = client.post(
        "/gm/maps/markers",
        json={
            "canvas_id": canvas_id,
            "entity_type": "city",
            "entity_id": foreign_city.city_id,
            "x": 0.5,
            "y": 0.5,
        },
    )
    assert resp.status_code == 404
    assert MapMarker.query.count() == 0


def test_marker_foreign_canvas_404():
    user, campaign = _make_gm_with_campaign("gm-marker-6")
    city = _add_city(campaign, "Hometown")
    _other_user, other_campaign = _make_gm_with_campaign("gm-marker-6b")
    foreign_canvas = gm_maps.get_or_create_world_canvas(other_campaign.id)
    db.session.commit()

    client = _gm_client(user, campaign)
    resp = client.post(
        "/gm/maps/markers",
        json={
            "canvas_id": foreign_canvas.id,
            "entity_type": "city",
            "entity_id": city.city_id,
            "x": 0.5,
            "y": 0.5,
        },
    )
    assert resp.status_code == 404


def test_marker_session_is_campaign_authority():
    """A spoofed campaign_id in the body is ignored; the session decides."""
    user, campaign = _make_gm_with_campaign("gm-marker-7")
    _other_user, other_campaign = _make_gm_with_campaign("gm-marker-7b")
    city = _add_city(campaign, "Sessionton")
    client = _gm_client(user, campaign)
    canvas_id = _world_canvas_id(client)

    resp = client.post(
        "/gm/maps/markers",
        json={
            "campaign_id": other_campaign.id,  # spoof attempt, must be ignored
            "canvas_id": canvas_id,
            "entity_type": "city",
            "entity_id": city.city_id,
            "x": 0.3,
            "y": 0.3,
        },
    )
    assert resp.status_code == 200
    marker = MapMarker.query.one()
    assert marker.campaign_id == campaign.id


def test_shop_marker_rejected_on_world_canvas():
    user, campaign = _make_gm_with_campaign("gm-scope-1")
    city = _add_city(campaign, "Scopeton")
    shop = _add_shop(campaign, city, "Scoped Goods")
    client = _gm_client(user, campaign)
    canvas_id = _world_canvas_id(client)

    resp = client.post(
        "/gm/maps/markers",
        json={
            "canvas_id": canvas_id,
            "entity_type": "shop",
            "entity_id": shop.shop_id,
            "x": 0.5,
            "y": 0.5,
        },
    )
    assert resp.status_code == 400


def test_city_marker_rejected_on_city_canvas():
    user, campaign = _make_gm_with_campaign("gm-scope-2")
    city = _add_city(campaign, "Innermap")
    client = _gm_client(user, campaign)
    city_canvas_id = client.get(f"/gm/maps/cities/{city.city_id}").get_json()["canvas"]["id"]

    resp = client.post(
        "/gm/maps/markers",
        json={
            "canvas_id": city_canvas_id,
            "entity_type": "city",
            "entity_id": city.city_id,
            "x": 0.5,
            "y": 0.5,
        },
    )
    assert resp.status_code == 400


def test_shop_marker_rejected_on_other_citys_canvas():
    user, campaign = _make_gm_with_campaign("gm-scope-3")
    city_a = _add_city(campaign, "Atown")
    city_b = _add_city(campaign, "Btown")
    shop_b = _add_shop(campaign, city_b, "B-Only Shop")
    client = _gm_client(user, campaign)
    canvas_a_id = client.get(f"/gm/maps/cities/{city_a.city_id}").get_json()["canvas"]["id"]

    resp = client.post(
        "/gm/maps/markers",
        json={
            "canvas_id": canvas_a_id,
            "entity_type": "shop",
            "entity_id": shop_b.shop_id,
            "x": 0.5,
            "y": 0.5,
        },
    )
    assert resp.status_code == 400


def test_shop_marker_saved_on_own_city_canvas():
    user, campaign = _make_gm_with_campaign("gm-scope-4")
    city = _add_city(campaign, "Shopville")
    shop = _add_shop(campaign, city, "Corner Store")
    client = _gm_client(user, campaign)
    canvas_id = client.get(f"/gm/maps/cities/{city.city_id}").get_json()["canvas"]["id"]

    resp = client.post(
        "/gm/maps/markers",
        json={
            "canvas_id": canvas_id,
            "entity_type": "shop",
            "entity_id": shop.shop_id,
            "x": 0.25,
            "y": 0.75,
        },
    )
    assert resp.status_code == 200
    marker = MapMarker.query.filter_by(canvas_id=canvas_id, shop_id=shop.shop_id).one()
    assert marker.entity_type == "shop"
    assert marker.y == pytest.approx(0.75)


def test_marker_rejects_unknown_entity_type():
    user, campaign = _make_gm_with_campaign("gm-scope-5")
    city = _add_city(campaign, "Typetown")
    client = _gm_client(user, campaign)
    canvas_id = _world_canvas_id(client)

    resp = client.post(
        "/gm/maps/markers",
        json={
            "canvas_id": canvas_id,
            "entity_type": "region",
            "entity_id": city.city_id,
            "x": 0.5,
            "y": 0.5,
        },
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Points of interest
# ---------------------------------------------------------------------------
def test_poi_create_update_and_remove_on_world_map():
    user, campaign = _make_gm_with_campaign("gm-poi-1")
    client = _gm_client(user, campaign)
    canvas_id = _world_canvas_id(client)

    resp = client.post(
        "/gm/maps/pois",
        json={
            "canvas_id": canvas_id,
            "label": "Ancient Standing Stones",
            "note": "The locals avoid this hill after sunset.",
            "x": 0.33,
            "y": 0.44,
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    poi_id = body["point_of_interest"]["id"]
    poi = MapPointOfInterest.query.filter_by(id=poi_id, campaign_id=campaign.id).one()
    assert poi.label == "Ancient Standing Stones"
    assert poi.note == "The locals avoid this hill after sunset."
    assert poi.x == pytest.approx(0.33)

    data = client.get("/gm/maps/world").get_json()
    assert data["points_of_interest"] == [
        {
            "id": poi_id,
            "label": "Ancient Standing Stones",
            "note": "The locals avoid this hill after sunset.",
            "x": pytest.approx(0.33),
            "y": pytest.approx(0.44),
            "visible_to_players": False,
        }
    ]

    update = client.post(
        "/gm/maps/pois",
        json={
            "canvas_id": canvas_id,
            "poi_id": poi_id,
            "label": "Moonlit Standing Stones",
            "note": "Glows during the new moon.",
            "x": 0.35,
            "y": 0.46,
            "visible_to_players": True,
        },
    )
    assert update.status_code == 200
    assert MapPointOfInterest.query.count() == 1
    poi = db.session.get(MapPointOfInterest, poi_id)
    assert poi.label == "Moonlit Standing Stones"
    assert poi.visible_to_players is True

    remove = client.post(
        "/gm/maps/pois/remove",
        json={"canvas_id": canvas_id, "poi_id": poi_id},
    )
    assert remove.status_code == 200
    assert remove.get_json()["removed"] is True
    assert MapPointOfInterest.query.count() == 0


def test_poi_rejects_city_canvas_and_bad_label():
    user, campaign = _make_gm_with_campaign("gm-poi-2")
    city = _add_city(campaign, "Poi City")
    client = _gm_client(user, campaign)
    city_canvas_id = client.get(f"/gm/maps/cities/{city.city_id}").get_json()["canvas"]["id"]

    resp = client.post(
        "/gm/maps/pois",
        json={
            "canvas_id": city_canvas_id,
            "label": "City-only",
            "note": "",
            "x": 0.5,
            "y": 0.5,
        },
    )
    assert resp.status_code == 404

    world_canvas_id = _world_canvas_id(client)
    missing_label = client.post(
        "/gm/maps/pois",
        json={"canvas_id": world_canvas_id, "label": " ", "x": 0.5, "y": 0.5},
    )
    assert missing_label.status_code == 400


def test_poi_foreign_canvas_404():
    user, campaign = _make_gm_with_campaign("gm-poi-3")
    _other_user, other_campaign = _make_gm_with_campaign("gm-poi-3b")
    foreign_canvas = gm_maps.get_or_create_world_canvas(other_campaign.id)
    db.session.commit()
    client = _gm_client(user, campaign)

    resp = client.post(
        "/gm/maps/pois",
        json={
            "canvas_id": foreign_canvas.id,
            "label": "Not Yours",
            "note": "",
            "x": 0.5,
            "y": 0.5,
        },
    )
    assert resp.status_code == 404
    assert MapPointOfInterest.query.count() == 0


# ---------------------------------------------------------------------------
# Background upload / regenerate
# ---------------------------------------------------------------------------
def test_background_upload_rejects_oversized_file():
    user, campaign = _make_gm_with_campaign("gm-bg-1")
    client = _gm_client(user, campaign)
    big = io.BytesIO(b"x" * (4 * 1024 * 1024 + 1))
    resp = client.post(
        "/gm/maps/world/background",
        data={"map_image": (big, "big.png")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400


def test_background_upload_rejects_unsupported_format():
    user, campaign = _make_gm_with_campaign("gm-bg-2")
    client = _gm_client(user, campaign)
    bmp = io.BytesIO()
    Image.new("RGB", (8, 8)).save(bmp, format="BMP")
    bmp.seek(0)
    resp = client.post(
        "/gm/maps/world/background",
        data={"map_image": (bmp, "map.bmp")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400


def test_background_upload_accepts_png_and_serves_image():
    user, campaign = _make_gm_with_campaign("gm-bg-3")
    client = _gm_client(user, campaign)
    resp = client.post(
        "/gm/maps/world/background",
        data={"map_image": (_tiny_png(), "world.png")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["canvas"]["source_type"] == "uploaded"
    assert body["canvas"]["has_image"] is True
    canvas_id = body["canvas"]["id"]

    try:
        img_resp = client.get(f"/gm/maps/image/{canvas_id}")
        assert img_resp.status_code == 200
        assert img_resp.mimetype == "image/webp"

        # Other GMs cannot fetch this campaign's map image.
        other_user, other_campaign = _make_gm_with_campaign("gm-bg-3b")
        other_client = _gm_client(other_user, other_campaign)
        assert other_client.get(f"/gm/maps/image/{canvas_id}").status_code == 404
    finally:
        canvas = db.session.get(MapCanvas, canvas_id)
        if canvas is not None:
            gm_maps.delete_map_image(canvas)


def test_background_regenerate_clears_upload():
    user, campaign = _make_gm_with_campaign("gm-bg-4")
    client = _gm_client(user, campaign)
    up = client.post(
        "/gm/maps/world/background",
        data={"map_image": (_tiny_png(), "world.png")},
        content_type="multipart/form-data",
    )
    assert up.status_code == 200
    canvas_id = up.get_json()["canvas"]["id"]

    regen = client.post("/gm/maps/world/background", data={})
    assert regen.status_code == 200
    body = regen.get_json()
    assert body["canvas"]["source_type"] == "generated"
    assert body["canvas"]["has_image"] is False
    assert body["canvas"]["generation"].get("features")
    assert not gm_maps.map_image_file(canvas_id).exists()


# ---------------------------------------------------------------------------
# World generation map setup (skip-generation path exercises the shared flag)
# ---------------------------------------------------------------------------
def test_skip_world_generation_creates_world_canvas_by_default():
    user = User(username="gm-gen-1", password="x", role="GM")
    user.set_password("Secret1!")
    db.session.add(user)
    db.session.commit()
    ensure_gm_profile(user)
    db.session.commit()
    db.session.refresh(user)

    client = flask_app.test_client()
    seed_client_session(client, user)
    resp = client.post(
        "/gm/generate_world/skip",
        data={"campaign_name": "Skip Camp", "system_type": "generic"},
    )
    assert resp.status_code in (302, 303)
    campaign = Campaign.query.filter_by(name="Skip Camp").one()
    assert (
        MapCanvas.query.filter_by(campaign_id=campaign.id, scope="world").count() == 1
    )


def test_skip_world_generation_always_creates_world_canvas():
    user = User(username="gm-gen-2", password="x", role="GM")
    user.set_password("Secret1!")
    db.session.add(user)
    db.session.commit()
    ensure_gm_profile(user)
    db.session.commit()
    db.session.refresh(user)

    client = flask_app.test_client()
    seed_client_session(client, user)
    resp = client.post(
        "/gm/generate_world/skip",
        data={
            "campaign_name": "No Map Camp",
            "system_type": "generic",
        },
    )
    assert resp.status_code in (302, 303)
    campaign = Campaign.query.filter_by(name="No Map Camp").one()
    assert MapCanvas.query.filter_by(campaign_id=campaign.id, scope="world").count() == 1


# ---------------------------------------------------------------------------
# Dashboard markup smoke test
# ---------------------------------------------------------------------------
def test_dashboard_has_map_tab_and_existing_tabs():
    user, campaign = _make_gm_with_campaign("gm-dash-1")
    city = _add_city(campaign, "Button City")
    _add_shop(campaign, city, "Button Shop")
    client = _gm_client(user, campaign)
    resp = client.get("/gm/")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert 'data-target="map-pane-content"' in html
    assert 'id="map-pane-content"' in html
    assert "max-width: 1320px;" in html
    assert "gm-dashboard-shell" in html
    assert 'id="gm-section-menu-btn"' in html
    assert 'id="gm-dashboard-sidebar"' in html
    assert 'id="gm-dashboard-backdrop"' in html
    assert "World" in html
    assert "Characters" in html
    assert ".map-add-city-controls[hidden]" in html
    assert "No cities available" in html
    assert "No shops available" in html
    assert "mapAddCityBtn.disabled = true" in html
    assert 'data-target="sim-pane-content"' in html
    assert 'data-target="market-pane-content"' in html
    assert html.index('data-target="map-pane-content"') < html.index('data-target="sim-pane-content"')
    assert '<button type="button" class="gm-panel-tab active" data-target="map-pane-content"' in html
    assert '<div id="map-pane-content" class="tab-panel-content active" role="tabpanel">' in html
    assert '<div id="sim-pane-content" class="tab-panel-content" role="tabpanel" hidden>' in html
    assert 'id="map-stage"' in html
    assert "Add City" in html
    assert "Remove city from map" in html
    assert "Add Shop" in html
    assert "Remove shop from map" in html
    assert "shopItems:" in html
    assert "/gm/shops/999999999/items" in html
    assert "Max 4 MB" in html
    assert "Add point of interest" in html
    assert 'id="map-poi-label"' in html
    assert 'id="map-poi-note"' in html
    assert 'id="map-poi-visible-to-players"' in html
    assert "Show to players" in html
    assert "function clampPopoutInsideStage" in html
    assert "function buildShopSummaryCard" in html
    entity_marker_block = html.split("function renderMarkers()", 1)[1].split(
        "function formatNumber", 1
    )[0]
    assert "dot.addEventListener('pointerdown'" not in entity_marker_block


def test_dark_mode_styles_map_entity_popout():
    theme_css = Path(flask_app.root_path, "static", "css", "theme.css").read_text()
    assert "html.dark-mode .simulation-panel .map-entity-popout" in theme_css
    assert "html.dark-mode .simulation-panel .map-entity-popout h3" in theme_css
    assert "html.dark-mode .simulation-panel .map-city-goods-list" in theme_css


def test_generate_world_form_has_map_setup_controls():
    user, _campaign = _make_gm_with_campaign("gm-dash-2")
    client = flask_app.test_client()
    seed_client_session(client, user)
    resp = client.get("/gm/generate_world")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert '<label for="campaign_name">World Name</label>' in html
    assert 'id="map-setup-fieldset"' not in html
    assert 'name="map_setup_choice"' not in html
    assert 'data-setting="population_scale"' in html
    assert 'data-setting="map_landmass_scale"' in html
    assert 'data-setting="map_waterways"' in html
    assert 'data-setting="map_terrain_roughness"' in html
    assert "Species Population" in html
    assert 'name="species_percent_Human"' in html
    assert 'name="species_percent_Half_Orc"' in html
    assert 'id="add-custom-species-btn"' in html
    assert 'id="setup-tutorial-interest-btn"' in html
    assert "Would a setup tutorial be useful?" in html
    assert "Thank you, your response has been noted." in html
    assert '"/auth/account/submissions"' in html
    assert 'prompted_key: "setup_tutorial"' in html


def test_world_generator_validator_persists_species_distribution():
    form = MultiDict(
        {
            "campaign_name": "Species World",
            "system_type": "dnd5e",
            "inventory_mode": "axis",
        }
    )
    for key, (_floor, _ceiling, d_min, d_max) in RANGE_SETTINGS.items():
        form.add(f"{key}_min", str(d_min))
        form.add(f"{key}_max", str(d_max))
    form.add("species_percent_Human", "40")
    form.add("species_percent_Elf", "12")
    form.add("species_percent_Half_Orc", "6")
    form.add("species_percent_Half_Elf", "8")
    form.add("species_percent_Dwarf", "10")
    form.add("species_percent_Halfling", "7")
    form.add("species_percent_Gnome", "5")
    form.add("species_percent_Tiefling", "4")
    form.add("species_percent_Dragonborn", "3")
    form.add("custom_species_name", "Crystal Folk")
    form.add("custom_species_percent", "5")

    settings = wg_validator.validate(form)

    species = settings["species_distribution"]
    assert {"name": "Crystal Folk", "percent": 5.0, "source": "custom"} in species
    assert sum(row["percent"] for row in species) == 100.0


def test_dashboard_includes_species_compendium_for_dnd5e_campaign():
    user, campaign = _make_gm_with_campaign("gm-species-tab")
    campaign.system_type = "dnd5e"
    db.session.commit()
    client = flask_app.test_client()
    seed_client_session(client, user, campaign_id=campaign.id)

    resp = client.get("/gm/")

    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert 'id="species-tab-btn"' in html
    assert "Species Compendium" in html
    assert 'id="species-compendium-body"' in html
    assert 'id="species-editor"' in html
    assert 'id="species-add-btn"' in html
    assert 'id="character-options-tab-btn"' not in html


def test_custom_species_builder_saves_species_details():
    user, campaign = _make_gm_with_campaign("gm-species-builder")
    campaign.system_type = "dnd5e"
    db.session.add(
        CampaignWorldConfig(
            campaign_id=campaign.id,
            settings_json={
                "species_distribution": [
                    {"name": "Human", "percent": 90.0, "source": "default"},
                    {"name": "Crystal Folk", "percent": 10.0, "source": "custom"},
                ]
            },
            schema_version=2,
        )
    )
    db.session.commit()
    client = flask_app.test_client()
    seed_client_session(client, user, campaign_id=campaign.id)

    resp = client.get("/gm/species/build")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "Crystal Folk" in html
    assert "Skip for now" in html

    save = client.post(
        "/gm/species/build",
        data={
            "builder_action": "save",
            "species_key": "crystal-folk",
            "species_crystal-folk_name": "Crystal Folk",
            "species_crystal-folk_population_percent": "10",
            "species_crystal-folk_str": "1",
            "species_crystal-folk_dex": "0",
            "species_crystal-folk_con": "2",
            "species_crystal-folk_int": "0",
            "species_crystal-folk_wis": "0",
            "species_crystal-folk_cha": "1",
            "species_crystal-folk_traits": "Faceted Memory: Remembers trade routes",
            "species_crystal-folk_stat_modifiers": "Speed 30 ft.",
            "species_crystal-folk_notes": "Use for gem-rich regions.",
        },
        follow_redirects=False,
    )
    assert save.status_code == 302

    cfg = CampaignWorldConfig.query.filter_by(campaign_id=campaign.id).one()
    species = cfg.settings_json["species_compendium"]
    crystal = next(row for row in species if row["key"] == "crystal-folk")
    assert crystal["ability_modifiers"]["con"] == 2
    assert crystal["stat_modifiers"] == "Speed 30 ft."
    assert crystal["notes"] == "Use for gem-rich regions."


def test_species_compendium_json_updates_base_species():
    user, campaign = _make_gm_with_campaign("gm-species-json")
    campaign.system_type = "dnd5e"
    db.session.commit()
    client = flask_app.test_client()
    seed_client_session(client, user, campaign_id=campaign.id)

    listed = client.get("/gm/species/compendium")
    assert listed.status_code == 200
    assert any(row["name"] == "Human" for row in listed.get_json()["species"])

    resp = client.post(
        "/gm/species/compendium/human",
        json={
            "name": "Human",
            "population_percent": 45,
            "ability_modifiers": {
                "str": 1,
                "dex": 0,
                "con": 0,
                "int": 0,
                "wis": 0,
                "cha": 0,
            },
            "traits": [{"name": "Adaptable", "description": "GM-authored note."}],
            "stat_modifiers": "GM-authored stat guidance.",
            "notes": "Use as baseline.",
        },
    )

    assert resp.status_code == 200
    payload = resp.get_json()["species"]
    assert payload["ability_modifiers"]["str"] == 1
    assert payload["traits"][0]["name"] == "Adaptable"


def test_species_compendium_json_creates_custom_species():
    user, campaign = _make_gm_with_campaign("gm-species-create")
    campaign.system_type = "dnd5e"
    db.session.commit()
    client = flask_app.test_client()
    seed_client_session(client, user, campaign_id=campaign.id)

    resp = client.post(
        "/gm/species/compendium",
        json={
            "name": "Crystal Folk",
            "population_percent": 5,
            "ability_modifiers": {
                "str": 0,
                "dex": 0,
                "con": 2,
                "int": 0,
                "wis": 0,
                "cha": 1,
            },
            "traits": [{"name": "Faceted Memory", "description": "GM-authored note."}],
            "stat_modifiers": "Speed 30 ft.",
            "notes": "Use for gem-rich regions.",
        },
    )

    assert resp.status_code == 201
    payload = resp.get_json()["species"]
    assert payload["key"] == "crystal-folk"
    assert payload["source"] == "custom"
    cfg = CampaignWorldConfig.query.filter_by(campaign_id=campaign.id).one()
    species = cfg.settings_json["species_compendium"]
    assert any(row["key"] == "crystal-folk" for row in species)
    assert {
        "name": "Crystal Folk",
        "percent": 5.0,
        "source": "custom",
    } in cfg.settings_json["species_distribution"]


def _settings_with_ranges(**ranges):
    return {
        "ranges": {
            key: {"min": value, "max": value}
            for key, value in ranges.items()
        }
    }


def test_map_geography_sliders_change_world_background_shape():
    calm = gm_maps.generate_canvas_background(
        "world",
        123,
        gm_maps.map_generation_profile(
            _settings_with_ranges(
                map_landmass_scale=8,
                map_waterways=0,
                map_terrain_roughness=0,
                num_regions=2,
                num_cities=3,
            )
        ),
    )
    rugged = gm_maps.generate_canvas_background(
        "world",
        123,
        gm_maps.map_generation_profile(
            _settings_with_ranges(
                map_landmass_scale=3,
                map_waterways=10,
                map_terrain_roughness=10,
                num_regions=8,
                num_cities=20,
            )
        ),
    )

    def count(features, kind):
        return sum(1 for item in features if item["type"] == kind)

    assert count(rugged["features"], "river") > count(calm["features"], "river")
    assert count(rugged["features"], "mountain_range") > count(calm["features"], "mountain_range")
    assert count(rugged["features"], "region_tint") > count(calm["features"], "region_tint")
    assert rugged["profile"]["terrain_roughness"] == 10


def test_economy_and_society_sliders_change_city_background_shape():
    sparse = gm_maps.generate_canvas_background(
        "city",
        456,
        gm_maps.map_generation_profile(
            _settings_with_ranges(
                global_item_pool_size=25,
                items_per_shop=1,
                city_size_variation=1,
                tech_magic_balance=1,
                map_waterways=0,
            )
        ),
    )
    dense = gm_maps.generate_canvas_background(
        "city",
        456,
        gm_maps.map_generation_profile(
            _settings_with_ranges(
                global_item_pool_size=500,
                items_per_shop=30,
                city_size_variation=20,
                tech_magic_balance=10,
                map_waterways=10,
            )
        ),
    )

    def count(features, kind):
        return sum(1 for item in features if item["type"] == kind)

    assert count(dense["features"], "district") > count(sparse["features"], "district")
    assert count(dense["features"], "road") > count(sparse["features"], "road")
    assert count(dense["features"], "canal") > count(sparse["features"], "canal")
    ring_roads = [
        item for item in dense["features"]
        if item["type"] == "road" and item["points"][0] == item["points"][-1]
    ]
    assert ring_roads
