"""GM Home onboarding checklist context and template."""

from __future__ import annotations

import pytest

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import Campaign, City, GMProfile, Player, Shop, User
from app.routes.handlers.gm_simulation_handler import build_gm_onboarding_context
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


def _gm_with_campaign(*, cities=0, shops=0, players=0, game_day=1):
    user = User(username="gm-onboard", password="x", role="GM")
    user.set_password("Secret1!")
    db.session.add(user)
    db.session.commit()
    ensure_gm_profile(user)
    db.session.commit()
    db.session.refresh(user)
    campaign = Campaign(
        gm_profile_id=user.gm_profile.id,
        name="Onboard Camp",
        system_type="generic",
        is_active=True,
        current_game_day=game_day,
    )
    db.session.add(campaign)
    db.session.flush()
    for i in range(cities):
        db.session.add(City(name=f"City{i}", campaign_id=campaign.id))
    for i in range(shops):
        db.session.add(
            Shop(campaign_id=campaign.id, name=f"Shop{i}", type="General")
        )
    for i in range(players):
        db.session.add(
            Player(campaign_id=campaign.id, is_npc=False, join_code=f"PLY-TEST{i}")
        )
    db.session.commit()
    return user, campaign


def test_build_context_no_world():
    user, campaign = _gm_with_campaign()
    with flask_app.test_request_context("/"):
        ctx = build_gm_onboarding_context(user.gm_profile, campaign)
    assert ctx is not None
    assert ctx["show"] is True
    assert ctx["steps"]["world"] is False
    assert ctx["steps"]["players"] is False
    assert ctx["steps"]["simulation"] is False


def test_build_context_world_no_players():
    user, campaign = _gm_with_campaign(cities=1, shops=1)
    with flask_app.test_request_context("/"):
        ctx = build_gm_onboarding_context(user.gm_profile, campaign)
    assert ctx["steps"]["world"] is True
    assert ctx["steps"]["players"] is False
    assert ctx["show"] is True


def test_build_context_ready_for_first_sim():
    user, campaign = _gm_with_campaign(cities=1, shops=1, players=2, game_day=1)
    with flask_app.test_request_context("/"):
        ctx = build_gm_onboarding_context(user.gm_profile, campaign)
    assert ctx["steps"]["world"] is True
    assert ctx["steps"]["players"] is True
    assert ctx["steps"]["simulation"] is False
    assert ctx["show"] is True
    assert ctx["show_first_sim_prompt"] is True
    assert ctx["join_code_ready"] is True
    assert ctx["campaign_players_url"].endswith("/campaigns?onboarding=players") or ctx[
        "campaign_players_url"
    ].endswith("/campaigns/?onboarding=players")


def test_build_context_join_code_not_ready_when_cleared():
    user, campaign = _gm_with_campaign(cities=1, shops=1, players=1, game_day=1)
    campaign.join_code = None
    db.session.commit()
    with flask_app.test_request_context("/"):
        ctx = build_gm_onboarding_context(user.gm_profile, campaign)
    assert ctx["join_code_ready"] is False
    assert ctx["show_first_sim_prompt"] is True


def test_build_context_join_code_ready_before_first_sim():
    user, campaign = _gm_with_campaign(cities=1, shops=1, players=1, game_day=1)
    with flask_app.test_request_context("/"):
        ctx = build_gm_onboarding_context(user.gm_profile, campaign)
    assert ctx["join_code_ready"] is True
    assert ctx["show_first_sim_prompt"] is True
    assert ctx["first_sim_completed"] is False


def test_build_context_all_complete():
    user, campaign = _gm_with_campaign(cities=1, shops=1, players=1, game_day=2)
    with flask_app.test_request_context("/"):
        ctx = build_gm_onboarding_context(user.gm_profile, campaign)
    assert ctx["all_complete"] is True
    assert ctx["show"] is False
    assert ctx["first_sim_completed"] is True
    assert ctx["show_first_sim_prompt"] is False


def test_gm_home_renders_checklist_for_incomplete_setup():
    user, campaign = _gm_with_campaign(cities=1, shops=1, players=0)
    client = flask_app.test_client()
    seed_client_session(client, user, campaign_id=campaign.id, session_mode="gm")
    resp = client.get("/gm/")
    assert resp.status_code == 200
    assert b"Getting started" in resp.data
    assert b"Generate your world" in resp.data
    assert b"Run your first market day" in resp.data


def test_gm_home_first_run_prompt_before_advanced_controls():
    user, campaign = _gm_with_campaign(cities=1, shops=1, players=1, game_day=1)
    client = flask_app.test_client()
    seed_client_session(client, user, campaign_id=campaign.id, session_mode="gm")
    resp = client.get("/gm/")
    assert resp.status_code == 200
    assert b"gm-dashboard--first-run" in resp.data
    assert b"gm-run-first-day-btn" in resp.data
    assert b"Start the market clock" in resp.data
    assert b"gm-advanced-sim-controls" not in resp.data
    assert b"gm-run-first-day-btn" in resp.data
    assert b">Week<" in resp.data or b"Run week" in resp.data
    assert b">Month<" in resp.data or b"Run month" in resp.data
    assert b">Year<" in resp.data or b"Run year" in resp.data


def test_gm_home_renders_setup_complete_summary():
    user, campaign = _gm_with_campaign(cities=1, shops=1, players=1, game_day=2)
    client = flask_app.test_client()
    seed_client_session(client, user, campaign_id=campaign.id, session_mode="gm")
    resp = client.get("/gm/")
    assert resp.status_code == 200
    assert b"Setup complete" in resp.data
