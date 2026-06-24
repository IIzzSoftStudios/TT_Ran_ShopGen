"""Tests for the three-step map-first world setup wizard."""

from __future__ import annotations

import copy

import pytest

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import Campaign, CampaignWorldConfig, City, MapCanvas, User
from app.services.user_capabilities import ensure_gm_profile
from app.services.world_generator import defaults as wg_defaults
from app.services.world_generator.validator import _species_field_key
from app.services.world_setup_state import (
    SETUP_STAGE_COMPLETE,
    SETUP_STAGE_ECONOMY,
    SETUP_STAGE_MAP,
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


def _make_gm(username: str = "setup-gm") -> User:
    user = User(username=username, password="x", role="GM")
    user.set_password("Secret1!")
    db.session.add(user)
    db.session.commit()
    ensure_gm_profile(user)
    db.session.commit()
    db.session.refresh(user)
    return user


def _economy_form_data(**overrides):
    data = {}
    for key, (_floor, _ceiling, d_min, d_max) in wg_defaults.RANGE_SETTINGS.items():
        if key in wg_defaults.RANGE_SETTINGS:
            lo = overrides.get(f"{key}_min", d_min)
            hi = overrides.get(f"{key}_max", d_max)
            data[f"{key}_min"] = str(lo)
            data[f"{key}_max"] = str(hi)
    for name, percent in wg_defaults.DEFAULT_SPECIES_DISTRIBUTION:
        data[_species_field_key(name)] = str(percent)
    data["market_volatility"] = "5"
    data.update(overrides)
    return data


def _minimal_economy_data():
    return _economy_form_data(
        num_regions_min=1,
        num_regions_max=1,
        num_cities_min=1,
        num_cities_max=1,
        population_scale_min=1,
        population_scale_max=1,
        global_item_pool_size_min=25,
        global_item_pool_size_max=30,
        city_size_variation_min=1,
        city_size_variation_max=1,
        items_per_shop_min=1,
        items_per_shop_max=1,
        tech_magic_balance_min=4,
        tech_magic_balance_max=4,
    )


def test_step1_post_creates_draft_campaign():
    user = _make_gm("step1-gm")
    client = flask_app.test_client()
    seed_client_session(client, user)

    resp = client.post(
        "/gm/generate_world",
        data={"campaign_name": "Draft World", "system_type": "generic"},
    )

    assert resp.status_code == 303
    assert "/gm/generate_world/map" in resp.headers["Location"]
    campaign = Campaign.query.filter_by(gm_profile_id=user.gm_profile.id).one()
    config = CampaignWorldConfig.query.filter_by(campaign_id=campaign.id).one()
    settings = config.settings_json
    assert settings["setup_stage"] == SETUP_STAGE_MAP
    assert settings["pending_generation"] is True
    assert MapCanvas.query.filter_by(campaign_id=campaign.id).count() == 1
    with client.session_transaction() as sess:
        assert sess.get("session_mode") == "gm"


def test_world_map_json_works_during_setup_in_player_session_mode():
    """Map builder JSON must load while session_mode is still player (HTML allowlist)."""
    user = _make_gm("map-json-player-mode")
    client = flask_app.test_client()
    seed_client_session(
        client,
        user,
        campaign_id=None,
        session_mode="player",
    )
    client.post(
        "/gm/generate_world",
        data={"campaign_name": "Player Mode Draft", "system_type": "generic"},
    )
    campaign = Campaign.query.filter_by(gm_profile_id=user.gm_profile.id).one()
    with client.session_transaction() as sess:
        sess["session_mode"] = "player"
        sess["campaign_id"] = campaign.id

    resp = client.get("/gm/maps/world")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload.get("canvas")
    with client.session_transaction() as sess:
        assert sess.get("session_mode") == "gm"


def test_step2_continue_advances_to_economy():
    user = _make_gm("step2-gm")
    client = flask_app.test_client()
    seed_client_session(client, user)
    client.post(
        "/gm/generate_world",
        data={"campaign_name": "Map World", "system_type": "generic"},
    )
    campaign = Campaign.query.filter_by(gm_profile_id=user.gm_profile.id).one()

    resp = client.post(
        "/gm/generate_world/map/continue",
        data={
            "map_landmass_scale_min": "5",
            "map_landmass_scale_max": "7",
            "map_waterways_min": "3",
            "map_waterways_max": "5",
            "map_terrain_roughness_min": "4",
            "map_terrain_roughness_max": "6",
        },
    )

    assert resp.status_code == 303
    assert "/gm/generate_world/economy" in resp.headers["Location"]
    config = CampaignWorldConfig.query.filter_by(campaign_id=campaign.id).one()
    assert config.settings_json["setup_stage"] == SETUP_STAGE_ECONOMY


def test_economy_back_link_returns_to_map_step():
    user = _make_gm("economy-back-gm")
    client = flask_app.test_client()
    seed_client_session(client, user)
    client.post(
        "/gm/generate_world",
        data={"campaign_name": "Back Nav World", "system_type": "generic"},
    )
    campaign = Campaign.query.filter_by(gm_profile_id=user.gm_profile.id).one()
    client.post(
        "/gm/generate_world/map/continue",
        data={
            "map_landmass_scale_min": "5",
            "map_landmass_scale_max": "7",
            "map_waterways_min": "3",
            "map_waterways_max": "5",
            "map_terrain_roughness_min": "4",
            "map_terrain_roughness_max": "6",
        },
    )

    resp = client.get("/gm/generate_world/economy")
    assert resp.status_code == 200

    resp = client.get("/gm/generate_world/map")
    assert resp.status_code == 200
    assert b"map" in resp.data.lower()
    config = CampaignWorldConfig.query.filter_by(campaign_id=campaign.id).one()
    assert config.settings_json["setup_stage"] == SETUP_STAGE_MAP


def test_step3_generates_world_and_preserves_canvas():
    user = _make_gm("step3-gm")
    client = flask_app.test_client()
    seed_client_session(client, user)
    client.post(
        "/gm/generate_world",
        data={"campaign_name": "Full World", "system_type": "generic"},
    )
    campaign = Campaign.query.filter_by(gm_profile_id=user.gm_profile.id).one()
    canvas = MapCanvas.query.filter_by(campaign_id=campaign.id).one()
    generation = copy.deepcopy(canvas.generation_json or {})
    terrain_before = copy.deepcopy(generation.get("terrain_grid"))

    client.post(
        "/gm/generate_world/map/continue",
        data={
            "map_landmass_scale_min": "5",
            "map_landmass_scale_max": "7",
            "map_waterways_min": "3",
            "map_waterways_max": "5",
            "map_terrain_roughness_min": "4",
            "map_terrain_roughness_max": "6",
        },
    )

    resp = client.post("/gm/generate_world/economy", data=_minimal_economy_data())
    assert resp.status_code == 303

    db.session.refresh(campaign)
    config = CampaignWorldConfig.query.filter_by(campaign_id=campaign.id).one()
    assert config.settings_json["setup_stage"] == SETUP_STAGE_COMPLETE
    assert config.settings_json["pending_generation"] is False
    assert City.query.filter_by(campaign_id=campaign.id).count() >= 1

    db.session.refresh(canvas)
    assert canvas.generation_json.get("terrain_grid") == terrain_before


def test_incomplete_campaign_gm_home_redirects_to_setup():
    user = _make_gm("resume-gm")
    client = flask_app.test_client()
    seed_client_session(client, user)
    client.post(
        "/gm/generate_world",
        data={"campaign_name": "Resume World", "system_type": "generic"},
    )
    campaign = Campaign.query.filter_by(gm_profile_id=user.gm_profile.id).one()
    seed_client_session(client, user, campaign_id=campaign.id)

    resp = client.get("/gm/", follow_redirects=False)

    assert resp.status_code == 303
    assert "/gm/generate_world/map" in resp.headers["Location"]


def test_skip_from_step1_marks_complete():
    user = _make_gm("skip-gm")
    client = flask_app.test_client()
    seed_client_session(client, user)

    resp = client.post(
        "/gm/generate_world/skip",
        data={"campaign_name": "Skipped", "system_type": "generic"},
    )

    assert resp.status_code == 303
    campaign = Campaign.query.filter_by(gm_profile_id=user.gm_profile.id).one()
    config = CampaignWorldConfig.query.filter_by(campaign_id=campaign.id).one()
    assert config.settings_json.get("generation_skipped") is True
    assert config.settings_json["setup_stage"] == SETUP_STAGE_COMPLETE


def test_step1_billing_402_does_not_create_campaign():
    user = _make_gm("capped-setup")
    db.session.add(
        Campaign(
            gm_profile_id=user.gm_profile.id,
            name="Existing",
            system_type="generic",
            is_active=True,
        )
    )
    db.session.commit()

    client = flask_app.test_client()
    seed_client_session(client, user)
    resp = client.post(
        "/gm/generate_world",
        data={"campaign_name": "Blocked", "system_type": "generic"},
    )

    assert resp.status_code == 402
    assert Campaign.query.filter_by(gm_profile_id=user.gm_profile.id).count() == 1


def test_generate_world_form_is_identity_only():
    user = _make_gm("form-gm")
    client = flask_app.test_client()
    seed_client_session(client, user)
    resp = client.get("/gm/generate_world")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "Step" in html and "1" in html
    assert 'name="campaign_name"' in html
    assert "Continue to map" in html
    assert 'name="species_percent_Human"' not in html
    assert 'data-setting="num_cities"' not in html
