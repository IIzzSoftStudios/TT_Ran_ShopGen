"""Regression tests for ``SimulationEngine.run_tick`` (canonical tick path).

Scheduling uses Celery + per-campaign Redis locks; there is no in-process
auto-tick loop. These tests assert engine behavior on a minimal in-memory
schema.
"""

from __future__ import annotations

import pytest
from flask import Flask

from app.extensions import db
import app.models  # noqa: F401
from app.models import Campaign, GMProfile, SimulationState, User
from app.services.simulation import SimulationEngine


@pytest.fixture()
def sim_app():
    flask_app = Flask(__name__)
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    flask_app.config["SECRET_KEY"] = "test"
    db.init_app(flask_app)
    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


def _make_gm(username: str) -> GMProfile:
    user = User(username=username, password="x", role="GM")
    db.session.add(user)
    db.session.flush()
    gm = GMProfile(user_id=user.id)
    db.session.add(gm)
    db.session.commit()
    return gm


def _make_campaign(gm: GMProfile, name: str = "Test Campaign") -> Campaign:
    campaign = Campaign(
        gm_profile_id=gm.id,
        name=name,
        system_type="generic",
        is_active=True,
        current_game_day=1,
    )
    db.session.add(campaign)
    db.session.commit()
    return campaign


def test_run_tick_unknown_campaign_raises(sim_app):
    with sim_app.app_context():
        engine = SimulationEngine()
        with pytest.raises(ValueError, match="No Campaign"):
            engine.run_tick(999, commit=True)


def test_run_tick_advances_calendar_and_sim_state(sim_app):
    with sim_app.app_context():
        gm = _make_gm("gm-one")
        campaign = _make_campaign(gm)
        engine = SimulationEngine()
        stats = engine.run_tick(campaign.id, commit=True)

        db.session.refresh(campaign)
        assert campaign.current_game_day == 2
        assert stats.get("current_game_day") == 2

        state = (
            db.session.query(SimulationState)
            .filter_by(campaign_id=campaign.id)
            .first()
        )
        assert state is not None
        assert state.current_tick == 2


def test_run_tick_isolates_campaigns_under_same_gm(sim_app):
    """Ticking one campaign must not advance another campaign owned by the same GM."""
    with sim_app.app_context():
        gm = _make_gm("gm-multi")
        campaign_a = _make_campaign(gm, name="Camp A")
        campaign_b = _make_campaign(gm, name="Camp B")

        engine = SimulationEngine()
        engine.run_tick(campaign_a.id, commit=True)

        db.session.refresh(campaign_a)
        db.session.refresh(campaign_b)
        assert campaign_a.current_game_day == 2
        assert campaign_b.current_game_day == 1

        state_a = (
            db.session.query(SimulationState)
            .filter_by(campaign_id=campaign_a.id)
            .first()
        )
        state_b = (
            db.session.query(SimulationState)
            .filter_by(campaign_id=campaign_b.id)
            .first()
        )
        assert state_a is not None and state_a.current_tick == 2
        assert state_b is None or state_b.current_tick == 0
