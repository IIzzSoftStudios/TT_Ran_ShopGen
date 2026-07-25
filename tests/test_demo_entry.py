"""Anonymous Demo: snapshot restore, isolation, Register For Access CTA."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import Campaign, Region, User
from app.services.demo_snapshot import (
    SNAPSHOT_SCHEMA_VERSION,
    restore_demo_snapshot,
    write_snapshot_file,
)
from app.services.demo_session import DEMO_ANON_PREFIX
from app.services.user_capabilities import ensure_gm_profile


def _complete_demo_lead(client, *, name="Demo User", email="demo@example.com"):
    return client.post(
        "/demo/lead",
        data={"contact_name": name, "email": email},
        follow_redirects=False,
    )


@pytest.fixture(autouse=True)
def _db_tables(tmp_path):
    flask_app.config["WTF_CSRF_ENABLED"] = False
    snap = tmp_path / "demo_template_v1.json"
    write_snapshot_file(_minimal_snapshot(), snap)
    previous = flask_app.config.get("DEMO_SNAPSHOT_PATH", "")
    flask_app.config["DEMO_SNAPSHOT_PATH"] = str(snap)
    with flask_app.app_context():
        db.create_all()
        yield
        db.session.rollback()
        db.drop_all()
    flask_app.config["DEMO_SNAPSHOT_PATH"] = previous


def _minimal_snapshot() -> dict:
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "source_campaign_id": 1,
        "campaign": {
            "name": "Demo World",
            "system_type": "dnd5e",
            "allow_player_debt": False,
            "current_game_day": 1,
        },
        "world_config": {
            "settings_json": {
                "schema_version": 2,
                "campaign_name": "Demo World",
                "system_type": "dnd5e",
                "setup_stage": "complete",
                "pending_generation": False,
                "ranges": {},
            },
            "schema_version": 2,
            "world_seed": 1,
        },
        "regions": [
            {
                "id": 10,
                "name": "Father's Castel-bari",
                "local_flavor": {"axis_position": 5},
                "main_color": None,
                "secondary_color": None,
            }
        ],
        "cities": [
            {
                "city_id": 20,
                "name": "Demo City",
                "government_type": None,
                "size": "Town",
                "population": 1000,
                "region": "Father's Castel-bari",
                "region_id": 10,
            }
        ],
        "shops": [
            {
                "shop_id": 30,
                "type": "General",
                "name": "Demo Shop",
                "preferred_region": None,
                "next_restock_day": None,
            }
        ],
        "shop_cities": [{"shop_id": 30, "city_id": 20}],
        "item_folders": [],
        "items": [],
        "shop_inventory": [],
        "regional_markets": [],
        "global_markets": [],
        "map_canvases": [
            {
                "id": 40,
                "city_id": None,
                "shop_id": None,
                "scope": "world",
                "source_type": "generated",
                "image_path": None,
                "underlay_path": None,
                "generation_json": {
                    "features": [{"type": "region_tint", "region_id": 10}]
                },
                "width": 512,
                "height": 512,
            }
        ],
        "map_markers": [],
        "map_pois": [],
        "include_empty_gm_world_state": False,
    }


def test_landing_hero_cta_is_try_demo(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Try Demo" in body
    assert 'href="/demo"' in body


def test_demo_without_snapshot_safe_failure(client, tmp_path):
    missing = tmp_path / "missing.json"
    flask_app.config["DEMO_SNAPSHOT_PATH"] = str(missing)
    _complete_demo_lead(client)
    resp = client.get("/demo", follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert resp.headers["Location"].endswith("/")
    with client.session_transaction() as sess:
        flashes = [msg for _cat, msg in sess.get("_flashes", [])]
    assert any("not configured" in msg.lower() or "not available" in msg.lower() for msg in flashes)


def test_demo_get_provisions_anonymous_and_redirects(client):
    _complete_demo_lead(client)
    resp = client.get("/demo", follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert "/gm" in resp.headers["Location"]
    with client.session_transaction() as sess:
        assert sess.get("demo_mode") is True
        assert sess.get("demo_step") == 1
        assert sess.get("demo_anon_id")
        assert sess.get("campaign_id")
        assert sess.get("demo_email") is None


def test_demo_isolation_between_clients(client):
    _complete_demo_lead(client)
    client.get("/demo", follow_redirects=False)
    with client.session_transaction() as sess:
        camp_a = sess.get("campaign_id")

    # Mutate A's world
    with flask_app.app_context():
        region = Region.query.filter_by(campaign_id=camp_a).one()
        region.name = "Alice Nation"
        db.session.commit()

    # Fresh client = fresh anonymous session
    from app import app as app_mod

    with app_mod.test_client() as client_b:
        _complete_demo_lead(client_b, email="b@example.com")
        client_b.get("/demo", follow_redirects=False)
        with client_b.session_transaction() as sess:
            camp_b = sess.get("campaign_id")
            assert camp_b != camp_a
            assert sess.get("demo_step") == 1

    with flask_app.app_context():
        assert Region.query.filter_by(campaign_id=camp_a).one().name == "Alice Nation"
        assert (
            Region.query.filter_by(campaign_id=camp_b).one().name
            == "Father's Castel-bari"
        )


def test_demo_reentry_resets_step_and_world(client):
    _complete_demo_lead(client)
    client.get("/demo", follow_redirects=False)
    with client.session_transaction() as sess:
        first_id = sess.get("campaign_id")
        sess["demo_step"] = 99

    with flask_app.app_context():
        Region.query.filter_by(campaign_id=first_id).one().name = "Dirty"
        db.session.commit()

    client.get("/demo", follow_redirects=False)
    with client.session_transaction() as sess:
        second_id = sess.get("campaign_id")
        assert sess.get("demo_step") == 1
        assert second_id is not None

    with flask_app.app_context():
        regions = Region.query.filter_by(campaign_id=second_id).all()
        assert any(r.name == "Father's Castel-bari" for r in regions)
        assert all(r.name != "Dirty" for r in regions)


def test_demo_gm_home_has_register_cta(client):
    client.post(
        "/demo/lead",
        data={"contact_name": "Demo User", "email": "demo@example.com"},
        follow_redirects=False,
    )
    client.get("/demo", follow_redirects=True)
    resp = client.get("/gm/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Welcome to Econo-Forge Demo" in body
    assert "Register For Access" in body
    assert "/subscribe" in body
    assert "Father's Castel-bari" in body or "Father&#39;s Castel-bari" in body
    assert "create your own" not in body.lower()
    assert "demo_tutorial.js" in body or "demo-tutorial-arrow" in body
    assert "gm-dashboard--demo" in body


def test_stale_demo_mode_does_not_leak_to_real_gm(client):
    """A leftover demo_mode session flag must not lock a real GM dashboard."""
    from tests.session_helpers import seed_client_session

    with flask_app.app_context():
        user = User(username="real_gm_no_demo_leak", password="x", role="Both")
        user.set_password("Secret1!")
        db.session.add(user)
        db.session.commit()
        ensure_gm_profile(user)
        db.session.commit()
        db.session.refresh(user)
        campaign = Campaign(
            gm_profile_id=user.gm_profile.id,
            name="Real Campaign",
            system_type="generic",
            is_active=True,
            current_game_day=1,
        )
        db.session.add(campaign)
        db.session.commit()
        seed_client_session(
            client,
            user,
            campaign_id=campaign.id,
            session_mode="gm",
            demo_mode=True,
            demo_step=1,
        )

    resp = client.get("/gm/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Welcome to Econo-Forge Demo" not in body
    assert "gm-dashboard--demo" not in body
    assert "demo-tutorial-root" not in body
    with client.session_transaction() as sess:
        assert sess.get("demo_mode") is None
        assert sess.get("demo_step") is None


def test_login_clears_demo_flags(client):
    _complete_demo_lead(client)
    client.get("/demo", follow_redirects=False)
    with client.session_transaction() as sess:
        assert sess.get("demo_mode") is True

    with flask_app.app_context():
        user = User(username="post_demo_login", password="x", role="Both")
        user.set_password("Secret1!")
        db.session.add(user)
        db.session.commit()

    resp = client.post(
        "/auth/login",
        data={"username": "post_demo_login", "password": "Secret1!"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    with client.session_transaction() as sess:
        assert sess.get("demo_mode") is None
        assert sess.get("demo_step") is None


def test_restore_remaps_region_ids_in_generation_json():
    with flask_app.app_context():
        user = User(username=f"{DEMO_ANON_PREFIX}testrestore", password="x", role="Both")
        user.set_password("Secret1!")
        db.session.add(user)
        db.session.commit()
        ensure_gm_profile(user)
        db.session.commit()
        db.session.refresh(user)

        camp = restore_demo_snapshot(
            _minimal_snapshot(), gm_profile_id=user.gm_profile.id
        )
        db.session.commit()
        from app.models import MapCanvas

        canvas = MapCanvas.query.filter_by(campaign_id=camp.id, scope="world").one()
        feat = (canvas.generation_json or {}).get("features") or []
        new_region = Region.query.filter_by(campaign_id=camp.id).one()
        assert feat[0]["region_id"] == new_region.id
