"""World state read path: row fallback when READ_PRICES_FROM_WORLD_STATE is off."""

from __future__ import annotations

import pytest
from flask import Flask

from app.extensions import db
import app.models  # noqa: F401
from app.models import Campaign, GMProfile, GMWorldState, User
from app.services import world_state_reads as wsr


@pytest.fixture()
def app_ctx():
    flask_app = Flask(__name__)
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    flask_app.config["SECRET_KEY"] = "test"
    db.init_app(flask_app)
    with flask_app.app_context():
        db.create_all()
        user = User(username="gm-ws", password="x", role="GM")
        db.session.add(user)
        db.session.flush()
        gm = GMProfile(user_id=user.id)
        db.session.add(gm)
        db.session.flush()
        campaign = Campaign(gm_profile_id=gm.id, name="WS", system_type="generic")
        db.session.add(campaign)
        db.session.flush()
        db.session.add(
            GMWorldState(
                campaign_id=campaign.id,
                state_json={"99": {"dynamic_price": 12.5, "stock": 7}},
            )
        )
        db.session.commit()
        yield campaign.id
        db.drop_all()


def test_reads_use_row_fallback_when_flag_disabled(app_ctx, monkeypatch):
    monkeypatch.setattr(
        "app.services.world_state_reads.READ_PRICES_FROM_WORLD_STATE",
        False,
    )
    cid = app_ctx
    assert wsr.get_effective_price(cid, 99, fallback=100.0) == 100.0
    assert wsr.get_effective_stock(cid, 99, fallback=3) == 3


def test_reads_use_blob_when_flag_enabled(app_ctx, monkeypatch):
    monkeypatch.setattr(
        "app.services.world_state_reads.READ_PRICES_FROM_WORLD_STATE",
        True,
    )
    cid = app_ctx
    assert wsr.get_effective_price(cid, 99, fallback=100.0) == 12.5
    assert wsr.get_effective_stock(cid, 99, fallback=3) == 7


def test_reads_fallback_when_blob_row_missing(app_ctx, monkeypatch):
    monkeypatch.setattr(
        "app.services.world_state_reads.READ_PRICES_FROM_WORLD_STATE",
        True,
    )
    cid = app_ctx
    assert wsr.get_effective_price(cid, 404, fallback=88.0) == 88.0
    assert wsr.get_effective_stock(cid, 404, fallback=5) == 5


def test_reads_fallback_for_malformed_entry(app_ctx, monkeypatch):
    monkeypatch.setattr(
        "app.services.world_state_reads.READ_PRICES_FROM_WORLD_STATE",
        True,
    )
    cid = app_ctx
    row = GMWorldState.query.filter_by(campaign_id=cid).first()
    row.state_json = {
        "99": "not-a-dict",
        "100": {"dynamic_price": "bad", "stock": "nope"},
        "101": {"dynamic_price": 9.0},
    }
    db.session.commit()

    assert wsr.get_effective_price(cid, 99, fallback=100.0) == 100.0
    assert wsr.get_effective_stock(cid, 99, fallback=3) == 3
    assert wsr.get_effective_price(cid, 100, fallback=100.0) == 100.0
    assert wsr.get_effective_stock(cid, 100, fallback=3) == 3
    assert wsr.get_effective_price(cid, 101, fallback=100.0) == 9.0
    assert wsr.get_effective_stock(cid, 101, fallback=3) == 3


def test_reads_fallback_when_state_json_not_dict(app_ctx, monkeypatch):
    monkeypatch.setattr(
        "app.services.world_state_reads.READ_PRICES_FROM_WORLD_STATE",
        True,
    )
    cid = app_ctx
    row = GMWorldState.query.filter_by(campaign_id=cid).first()
    row.state_json = ["invalid"]
    db.session.commit()

    assert wsr.get_effective_price(cid, 99, fallback=100.0) == 100.0
    assert wsr.get_effective_stock(cid, 99, fallback=3) == 3


def test_reads_fallback_when_world_state_row_missing(app_ctx, monkeypatch):
    monkeypatch.setattr(
        "app.services.world_state_reads.READ_PRICES_FROM_WORLD_STATE",
        True,
    )
    cid = app_ctx
    GMWorldState.query.filter_by(campaign_id=cid).delete()
    db.session.commit()

    assert wsr.get_effective_price(cid, 99, fallback=100.0) == 100.0
    assert wsr.get_effective_stock(cid, 99, fallback=3) == 3
