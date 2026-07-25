"""Demo analytics: start events, beacon gate, vault aggregates."""

from __future__ import annotations

import pytest

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import DemoAnalyticsEvent, User
from app.services.demo_analytics import (
    EVENT_DEMO_START,
    EVENT_REGISTER_CLICK,
    EVENT_STEP_VIEW,
    aggregate_demo_analytics,
    mint_demo_run_id,
    record_demo_event,
)
from app.services.demo_snapshot import (
    SNAPSHOT_SCHEMA_VERSION,
    write_snapshot_file,
)
from app.services.user_capabilities import ensure_gm_profile


def _complete_demo_lead(client, *, name="Demo User", email="demo@example.com"):
    return client.post(
        "/demo/lead",
        data={"contact_name": name, "email": email},
        follow_redirects=False,
    )


from tests.session_helpers import seed_client_session


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


def test_demo_start_records_analytics_event(client):
    _complete_demo_lead(client)
    resp = client.get("/demo", follow_redirects=False)
    assert resp.status_code in (302, 303)
    with client.session_transaction() as sess:
        assert sess.get("demo_mode") is True
        assert sess.get("demo_run_id")
        run_id = sess["demo_run_id"]
    starts = DemoAnalyticsEvent.query.filter_by(
        event_type=EVENT_DEMO_START, demo_run_id=run_id
    ).all()
    assert len(starts) == 1
    assert starts[0].demo_anon_id
    assert starts[0].surface == "gm_tutorial"


def test_analytics_beacon_rejects_non_demo_user(client):
    user = User(username="real-gm", password="!", role="Both", email=None)
    user.set_password("ValidPass1!")
    db.session.add(user)
    db.session.flush()
    ensure_gm_profile(user)
    db.session.commit()

    from tests.session_helpers import seed_client_session

    seed_client_session(client, user, session_mode="gm")
    with client.session_transaction() as sess:
        sess["demo_mode"] = True
        sess["demo_run_id"] = "00000000-0000-0000-0000-000000000001"

    resp = client.post(
        "/demo/analytics/event",
        json={"event_type": "step_view", "step_key": "welcome"},
    )
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "demo_mode_required"


def test_analytics_beacon_accepts_step_and_register(client):
    _complete_demo_lead(client)
    resp = client.get("/demo", follow_redirects=False)
    assert resp.status_code in (302, 303)

    step = client.post(
        "/demo/analytics/event",
        json={"event_type": "step_view", "step_key": "point_nations"},
    )
    assert step.status_code == 200
    assert step.get_json()["ok"] is True

    step2 = client.post(
        "/demo/analytics/event",
        json={"event_type": "step_view", "step_key": "point_nations"},
    )
    assert step2.status_code == 200
    assert (
        DemoAnalyticsEvent.query.filter_by(
            event_type=EVENT_STEP_VIEW, step_key="point_nations"
        ).count()
        == 1
    )

    reg = client.post(
        "/demo/analytics/event",
        json={"event_type": "register_click", "step_key": "point_nations"},
    )
    assert reg.status_code == 200
    assert (
        DemoAnalyticsEvent.query.filter_by(event_type=EVENT_REGISTER_CLICK).count()
        == 1
    )


def test_analytics_beacon_rejects_demo_start_and_unknown_step(client):
    _complete_demo_lead(client)
    client.get("/demo", follow_redirects=False)
    bad_start = client.post(
        "/demo/analytics/event",
        json={"event_type": "demo_start"},
    )
    assert bad_start.status_code == 400

    bad_step = client.post(
        "/demo/analytics/event",
        json={"event_type": "step_view", "step_key": "hack;drop"},
    )
    assert bad_step.status_code == 400


def test_aggregate_demo_analytics_funnel():
    with flask_app.test_request_context("/"):
        from flask import session

        session["demo_anon_id"] = "a" * 16
        run_a = mint_demo_run_id()
    record_demo_event(
        event_type=EVENT_DEMO_START,
        demo_run_id=run_a,
        demo_anon_id="a" * 16,
        commit=True,
    )
    record_demo_event(
        event_type=EVENT_STEP_VIEW,
        demo_run_id=run_a,
        demo_anon_id="a" * 16,
        step_key="welcome",
        commit=True,
    )
    record_demo_event(
        event_type=EVENT_STEP_VIEW,
        demo_run_id=run_a,
        demo_anon_id="a" * 16,
        step_key="point_nations",
        commit=True,
    )
    record_demo_event(
        event_type=EVENT_REGISTER_CLICK,
        demo_run_id=run_a,
        demo_anon_id="a" * 16,
        step_key="point_nations",
        commit=True,
    )

    with flask_app.test_request_context("/"):
        from flask import session

        session["demo_anon_id"] = "b" * 16
        run_b = mint_demo_run_id()
    record_demo_event(
        event_type=EVENT_DEMO_START,
        demo_run_id=run_b,
        demo_anon_id="b" * 16,
        commit=True,
    )
    record_demo_event(
        event_type=EVENT_STEP_VIEW,
        demo_run_id=run_b,
        demo_anon_id="b" * 16,
        step_key="welcome",
        commit=True,
    )

    payload = aggregate_demo_analytics()
    assert payload["total_runs"] == 2
    assert payload["runs_with_register_click"] == 1
    assert payload["register_conversion_pct"] == 50.0
    by_key = {row["step_key"]: row for row in payload["steps"]}
    assert by_key["welcome"]["runs_reached"] == 2
    assert by_key["welcome"]["reach_pct"] == 100.0
    assert by_key["point_nations"]["runs_reached"] == 1
    assert by_key["point_nations"]["register_clicks"] == 1


def test_vault_demo_analytics_api_ok_for_vault_keeper(client):
    keeper = User(username="vault-demo", password="!", role="vault_keeper", email=None)
    keeper.set_password("ValidPass1!")
    db.session.add(keeper)
    db.session.commit()
    from tests.session_helpers import seed_client_session

    seed_client_session(client, keeper, session_mode="gm")
    resp = client.get("/admin/vault/demo-analytics")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "total_runs" in data
    assert "steps" in data


def test_keys_template_includes_demo_analytics_tab():
    from flask import render_template

    with flask_app.test_request_context("/"):
        html = render_template(
            "admin/keys.html",
            show_gm_usage_tab=True,
            keys=[],
            admin_keys=[],
            stats={"total": 0, "used": 0, "available": 0},
            admin_stats={"total": 0, "used": 0, "available": 0},
            access_requests=[],
            prompted_feedback_rows=[],
            prompted_feedback_questions=[],
            vault_phase_slugs=["forge_master"],
            all_phase_slugs=["forge_master"],
            gm_simulation_rows=[],
            demo_analytics={
                "total_runs": 3,
                "runs_with_register_click": 1,
                "register_conversion_pct": 33.3,
                "steps": [
                    {
                        "step_key": "welcome",
                        "runs_reached": 3,
                        "reach_pct": 100.0,
                        "register_clicks": 0,
                    }
                ],
            },
            campaign_code_redemptions=[],
            campaign_character_rows=[],
            bug_reports=[],
            feedback_items=[],
            suggestions=[],
        )
    assert 'id="demo-analytics-tab"' in html
    assert "Demo analytics" in html
    assert 'id="demo-analytics-pane"' in html


def test_privacy_mentions_demo_metrics(client):
    resp = client.get("/docs?section=privacy")
    assert resp.status_code == 200
    assert b"Demo walkthrough usage" in resp.data
