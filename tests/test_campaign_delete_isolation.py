"""Campaign deletion: per-campaign child rows must cascade cleanly.

The legacy test in this file is fully mock-based and never exercises a real
cascade. It is kept for the IDOR / scoping assertion (only the GM's own
character sheets are deleted), but the new ``CampaignDeleteCascadeTests``
class drives an in-memory SQLite database with foreign-key enforcement on
to catch the SQLAlchemy unit-of-work bug where deleting a Campaign tried
to NULL out the primary-key column of a child row (``gm_world_state``).
"""

import unittest
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from sqlalchemy import event

from app import app
from app.extensions import db
from app.models import (
    Campaign,
    DeletedCampaignSimSnapshot,
    GMProfile,
    GMWorldState,
    SimulationLog,
    SimulationState,
    User,
)
from app.routes.handlers import gm_campaigns_handler


class CampaignDeleteIsolationTests(unittest.TestCase):
    @patch("app.routes.handlers.gm_campaigns_handler.flash")
    @patch("app.routes.handlers.gm_campaigns_handler.redirect")
    @patch("app.routes.handlers.gm_campaigns_handler.url_for", return_value="/gm/campaigns/")
    @patch("app.routes.handlers.gm_campaigns_handler.SimulationState")
    @patch("app.routes.handlers.gm_campaigns_handler.PlayerCharacterSheet")
    @patch("app.routes.handlers.gm_campaigns_handler.Campaign")
    @patch("app.routes.handlers.gm_campaigns_handler.GMProfile")
    @patch("app.routes.handlers.gm_campaigns_handler.current_user")
    @patch("app.routes.handlers.gm_campaigns_handler.db")
    def test_delete_campaign_removes_campaign_character_sheets(
        self,
        db_mock,
        current_user_mock,
        gm_profile_model_mock,
        campaign_model_mock,
        sheet_model_mock,
        _sim_state_model_mock,
        _url_for_mock,
        _redirect_mock,
        _flash_mock,
    ):
        current_user_mock.id = 42
        gm_profile = MagicMock(id=7)
        campaign = MagicMock(id=11)

        gm_profile_model_mock.query.filter_by.return_value.first.return_value = gm_profile
        campaign_model_mock.query.filter_by.return_value.first.return_value = campaign
        _sim_state_model_mock.query.filter_by.return_value.first.return_value = None

        with app.test_request_context("/gm/campaigns/delete/11", method="POST"):
            gm_campaigns_handler.delete_campaign.__wrapped__(campaign.id)

        sheet_model_mock.query.filter_by.assert_called_once_with(campaign_id=campaign.id)
        db_mock.session.delete.assert_called_once_with(campaign)
        db_mock.session.commit.assert_called_once()

    @patch("app.routes.handlers.gm_campaigns_handler.flash")
    @patch("app.routes.handlers.gm_campaigns_handler.redirect")
    @patch("app.routes.handlers.gm_campaigns_handler.url_for")
    @patch("app.routes.handlers.gm_campaigns_handler.SimulationState")
    @patch("app.routes.handlers.gm_campaigns_handler.PlayerCharacterSheet")
    @patch("app.routes.handlers.gm_campaigns_handler.Campaign")
    @patch("app.routes.handlers.gm_campaigns_handler.GMProfile")
    @patch("app.routes.handlers.gm_campaigns_handler.current_user")
    @patch("app.routes.handlers.gm_campaigns_handler.db")
    def test_delete_active_campaign_clears_session_and_redirects_to_picker(
        self,
        db_mock,
        current_user_mock,
        gm_profile_model_mock,
        campaign_model_mock,
        _sheet_model_mock,
        _sim_state_model_mock,
        url_for_mock,
        redirect_mock,
        _flash_mock,
    ):
        current_user_mock.id = 42
        gm_profile = MagicMock(id=7)
        campaign = MagicMock(id=11)

        gm_profile_model_mock.query.filter_by.return_value.first.return_value = gm_profile
        campaign_model_mock.query.filter_by.return_value.first.return_value = campaign
        _sim_state_model_mock.query.filter_by.return_value.first.return_value = None
        url_for_mock.side_effect = lambda endpoint, **_kwargs: {
            "main.campaigns": "/campaigns",
            "gm.view_campaigns": "/gm/campaigns/",
        }[endpoint]
        redirect_mock.side_effect = lambda url: url

        with app.test_request_context("/gm/campaigns/delete/11", method="POST"):
            from flask import session

            session["campaign_id"] = 11
            session["system_type"] = "dnd5e"

            response = gm_campaigns_handler.delete_campaign.__wrapped__(campaign.id)

            assert response == "/campaigns"
            assert "campaign_id" not in session
            assert "system_type" not in session

        db_mock.session.delete.assert_called_once_with(campaign)
        db_mock.session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Real cascade tests using in-memory SQLite with FK enforcement enabled.
# Regression coverage for the bug where deleting a Campaign tried to NULL
# the primary-key column of GMWorldState (campaign_id is its PK).
# ---------------------------------------------------------------------------


@pytest.fixture()
def cascade_app():
    flask_app = Flask(__name__)
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    flask_app.config["SECRET_KEY"] = "test"
    db.init_app(flask_app)
    with flask_app.app_context():
        # SQLite ignores FK constraints by default. Enable enforcement so
        # ON DELETE CASCADE actually fires; without this, passive_deletes=True
        # would silently leave orphans and the test would fail to detect
        # missing CASCADE on the FK.
        @event.listens_for(db.engine, "connect")
        def _fk_pragma_on_connect(dbapi_con, _record):
            cur = dbapi_con.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

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
    db.session.flush()
    return gm


def _make_campaign(gm: GMProfile, name: str) -> Campaign:
    c = Campaign(
        gm_profile_id=gm.id,
        name=name,
        system_type="generic",
        is_active=True,
        current_game_day=1,
    )
    db.session.add(c)
    db.session.flush()
    return c


def test_delete_campaign_cascades_through_gm_world_state(cascade_app):
    """The original crash: Campaign delete with a GMWorldState row.

    Before the fix, SQLAlchemy tried to ``UPDATE gm_world_state SET
    campaign_id = NULL WHERE ...`` to detach the child before the parent
    delete, but ``campaign_id`` is the table's primary key. The fix uses
    ``passive_deletes=True`` so the DB-level ON DELETE CASCADE handles
    the orphan removal.
    """
    gm = _make_gm("gm_world_state_user")
    campaign = _make_campaign(gm, "Doomed")
    campaign_id = campaign.id

    db.session.add(
        GMWorldState(
            campaign_id=campaign.id,
            state_json={"shops": []},
            schema_version=1,
            tick_seq=0,
        )
    )
    db.session.commit()
    assert GMWorldState.query.filter_by(campaign_id=campaign_id).count() == 1

    db.session.delete(campaign)
    db.session.commit()

    assert Campaign.query.filter_by(id=campaign_id).count() == 0
    assert GMWorldState.query.filter_by(campaign_id=campaign_id).count() == 0


def test_delete_campaign_cascades_through_simulation_state(cascade_app):
    """SimulationState.campaign_id is unique NOT NULL; nulling would crash.

    Same idiom as gm_world_state: deferring to the DB cascade prevents
    SQLAlchemy from attempting a doomed UPDATE before the parent delete.
    """
    gm = _make_gm("gm_sim_state_user")
    campaign = _make_campaign(gm, "AlsoDoomed")
    campaign_id = campaign.id

    db.session.add(
        SimulationState(
            campaign_id=campaign.id,
            current_tick=0,
            speed="pause",
        )
    )
    db.session.commit()
    assert SimulationState.query.filter_by(campaign_id=campaign_id).count() == 1

    db.session.delete(campaign)
    db.session.commit()

    assert Campaign.query.filter_by(id=campaign_id).count() == 0
    assert SimulationState.query.filter_by(campaign_id=campaign_id).count() == 0


def test_delete_campaign_cascades_through_simulation_logs(cascade_app):
    """Regression cover for the previously-fixed simulation_logs cascade."""
    gm = _make_gm("gm_sim_log_user")
    campaign = _make_campaign(gm, "LoggingDoomed")
    campaign_id = campaign.id

    db.session.add(
        SimulationLog(
            tick_id=1,
            event_type="price_change",
            details={"foo": "bar"},
            campaign_id=campaign.id,
        )
    )
    db.session.commit()
    assert SimulationLog.query.filter_by(campaign_id=campaign_id).count() == 1

    db.session.delete(campaign)
    db.session.commit()

    assert Campaign.query.filter_by(id=campaign_id).count() == 0
    assert SimulationLog.query.filter_by(campaign_id=campaign_id).count() == 0


def test_snapshot_helper_archives_campaign_metrics(cascade_app):
    """The private snapshot helper writes a tombstone with all current metrics.

    Pulls values from the live ``Campaign`` and its ``simulation_state`` —
    never from request input — so the snapshot is trustworthy regardless
    of caller context.
    """
    from datetime import datetime as _dt

    gm = _make_gm("snap_helper_user")
    campaign = _make_campaign(gm, "ArchiveMe")
    campaign.current_game_day = 14
    campaign.system_type = "dnd5e"
    last_tick = _dt(2026, 5, 7, 9, 30, 0)
    db.session.add(
        SimulationState(
            campaign_id=campaign.id,
            current_tick=13,
            speed="pause",
            last_tick_time=last_tick,
            sim_clicks_day=4,
            sim_clicks_week=2,
            sim_clicks_month=1,
            sim_clicks_year=0,
            sim_clicks_pause=3,
        )
    )
    db.session.commit()
    db.session.refresh(campaign)

    snap = gm_campaigns_handler._snapshot_campaign_for_analytics(campaign)
    db.session.commit()

    assert snap.snapshot_id is not None
    assert snap.gm_profile_id == gm.id
    assert snap.campaign_id == campaign.id
    assert snap.campaign_name == "ArchiveMe"
    assert snap.system_type == "dnd5e"
    assert snap.current_game_day == 14
    assert snap.days_simulated == 13
    assert snap.sim_clicks_day == 4
    assert snap.sim_clicks_week == 2
    assert snap.sim_clicks_month == 1
    assert snap.sim_clicks_year == 0
    assert snap.sim_clicks_pause == 3
    assert snap.last_tick_time == last_tick
    assert snap.deleted_at is not None


def test_snapshot_survives_campaign_delete_cascade(cascade_app):
    """Snapshot rows must NOT cascade away with the parent Campaign.

    The snapshot's only FK is to ``gm_profile``; there is no FK back to
    ``campaign``, so deleting the Campaign leaves the tombstone intact
    for analytics.
    """
    gm = _make_gm("survive_user")
    campaign = _make_campaign(gm, "ToBeForgotten")
    campaign.current_game_day = 5
    db.session.commit()

    gm_campaigns_handler._snapshot_campaign_for_analytics(campaign)
    db.session.delete(campaign)
    db.session.commit()

    snaps = DeletedCampaignSimSnapshot.query.filter_by(gm_profile_id=gm.id).all()
    assert len(snaps) == 1
    assert snaps[0].campaign_name == "ToBeForgotten"
    assert snaps[0].days_simulated == 4


def test_snapshot_loaded_simulation_state_still_deletes_cleanly(cascade_app):
    """Snapshotting loads ``campaign.simulation_state`` before delete.

    That loaded one-to-one child used to make SQLAlchemy emit
    ``UPDATE simulation_state SET campaign_id = NULL`` before the database
    cascade could run, which fails because ``campaign_id`` is NOT NULL.
    """
    gm = _make_gm("loaded_sim_user")
    campaign = _make_campaign(gm, "LoadedSimState")
    campaign_id = campaign.id
    db.session.add(
        SimulationState(
            campaign_id=campaign.id,
            current_tick=3,
            speed="pause",
            sim_clicks_day=1,
        )
    )
    db.session.commit()

    gm_campaigns_handler._snapshot_campaign_for_analytics(campaign)
    assert campaign.simulation_state is not None
    db.session.delete(campaign)
    db.session.commit()

    assert Campaign.query.filter_by(id=campaign_id).count() == 0
    assert SimulationState.query.filter_by(campaign_id=campaign_id).count() == 0
    snaps = DeletedCampaignSimSnapshot.query.filter_by(gm_profile_id=gm.id).all()
    assert len(snaps) == 1
    assert snaps[0].campaign_name == "LoadedSimState"
    assert snaps[0].sim_clicks_day == 1


def test_snapshot_cascades_when_gm_profile_deleted(cascade_app):
    """Snapshots are GM-scoped: deleting the GM clears the tombstones too.

    Per-GM analytics has no meaning once the GM is gone, so the FK is
    ``ON DELETE CASCADE``. This test pins that contract.
    """
    gm = _make_gm("doomed_gm")
    campaign = _make_campaign(gm, "Ephemeral")
    db.session.commit()
    gm_campaigns_handler._snapshot_campaign_for_analytics(campaign)
    db.session.delete(campaign)
    db.session.commit()
    assert DeletedCampaignSimSnapshot.query.count() == 1

    db.session.delete(gm)
    db.session.commit()
    assert DeletedCampaignSimSnapshot.query.count() == 0


def test_delete_campaign_handler_post_with_simulation_stack(client):
    """Regression: POST delete must not 500 when simulation_state is loaded for snapshot."""
    from app import app as flask_app
    from app.models import User
    from app.services.user_capabilities import ensure_gm_profile
    from tests.session_helpers import seed_client_session

    flask_app.config["WTF_CSRF_ENABLED"] = False
    with flask_app.app_context():
        db.create_all()
        user = User(username="gm_del_post", password="x", role="GM")
        user.set_password("Secret1!")
        db.session.add(user)
        db.session.commit()
        ensure_gm_profile(user)
        db.session.commit()
        db.session.refresh(user)
        gm = user.gm_profile
        campaign = _make_campaign(gm, "DeleteViaPost")
        db.session.add_all(
            [
                SimulationState(
                    campaign_id=campaign.id,
                    current_tick=2,
                    speed="pause",
                    sim_clicks_day=1,
                ),
                GMWorldState(
                    campaign_id=campaign.id,
                    state_json={"shops": []},
                    schema_version=1,
                    tick_seq=2,
                ),
            ]
        )
        db.session.commit()
        campaign_id = campaign.id
        seed_client_session(client, user)

    resp = client.post(f"/gm/campaigns/delete/{campaign_id}")
    assert resp.status_code in (302, 303)
    with flask_app.app_context():
        assert Campaign.query.filter_by(id=campaign_id).count() == 0
        assert SimulationState.query.filter_by(campaign_id=campaign_id).count() == 0
        assert GMWorldState.query.filter_by(campaign_id=campaign_id).count() == 0
        snaps = DeletedCampaignSimSnapshot.query.filter_by(campaign_id=campaign_id).all()
        assert len(snaps) == 1
        assert snaps[0].sim_clicks_day == 1
        db.drop_all()


def test_delete_campaign_with_full_simulation_stack_cascades(cascade_app):
    """The exact production shape: one Campaign with state + world_state + logs.

    Mirrors what the user reported: ``POST /gm/campaigns/delete/<id>`` on a
    campaign that has been ticked at least once (so it owns rows in every
    Campaign-scoped table).
    """
    gm = _make_gm("gm_full_stack_user")
    campaign = _make_campaign(gm, "ProductionShape")
    campaign_id = campaign.id

    db.session.add_all([
        SimulationState(campaign_id=campaign.id, current_tick=5, speed="pause"),
        GMWorldState(
            campaign_id=campaign.id,
            state_json={"shops": []},
            schema_version=1,
            tick_seq=5,
        ),
        SimulationLog(
            tick_id=1,
            event_type="price_change",
            details={"x": 1},
            campaign_id=campaign.id,
        ),
        SimulationLog(
            tick_id=2,
            event_type="restock",
            details={"y": 2},
            campaign_id=campaign.id,
        ),
    ])
    db.session.commit()

    db.session.delete(campaign)
    db.session.commit()

    assert Campaign.query.filter_by(id=campaign_id).count() == 0
    assert SimulationState.query.filter_by(campaign_id=campaign_id).count() == 0
    assert GMWorldState.query.filter_by(campaign_id=campaign_id).count() == 0
    assert SimulationLog.query.filter_by(campaign_id=campaign_id).count() == 0


if __name__ == "__main__":
    unittest.main()
