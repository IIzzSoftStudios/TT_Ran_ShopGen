"""Tests for GET /gm/market-overview."""

from __future__ import annotations

import pytest

from app import app as flask_app
from tests.session_helpers import seed_client_session
from app.extensions import db
import app.models  # noqa: F401
from app.models import (
    Campaign,
    CampaignWorldConfig,
    GlobalMarket,
    GMProfile,
    Item,
    Shop,
    ShopInventory,
    User,
)
from app.services.user_capabilities import ensure_gm_profile


@pytest.fixture(autouse=True)
def _db_tables():
    flask_app.config["WTF_CSRF_ENABLED"] = False
    with flask_app.app_context():
        db.create_all()
        yield
        db.session.rollback()
        db.drop_all()


def test_market_overview_requires_login():
  client = flask_app.test_client()
  resp = client.get("/gm/market-overview")
  assert resp.status_code in (302, 401)


def test_market_overview_returns_json_for_gm_with_campaign():
    user = User(username="gm-api-mkt", password="x", role="GM")
    user.set_password("Secret1!")
    db.session.add(user)
    db.session.commit()
    ensure_gm_profile(user)
    db.session.commit()
    db.session.refresh(user)

    campaign = Campaign(
        gm_profile_id=user.gm_profile.id,
        name="API Camp",
        system_type="generic",
        is_active=True,
        current_game_day=1,
    )
    db.session.add(campaign)
    db.session.flush()
    item = Item(
        campaign_id=campaign.id,
        name="Rope",
        type="Utility",
        rarity="common",
        base_price=5,
    )
    db.session.add(item)
    db.session.flush()
    shop = Shop(campaign_id=campaign.id, name="Dock", type="General")
    db.session.add(shop)
    db.session.flush()
    db.session.add(
        ShopInventory(
            campaign_id=campaign.id,
            shop_id=shop.shop_id,
            item_id=item.item_id,
            stock=3,
            dynamic_price=6.0,
        )
    )
    db.session.add(
        GlobalMarket(
            campaign_id=campaign.id,
            item_id=item.item_id,
            average_price=5.0,
            baseline_avg_stock=3.0,
        )
    )
    db.session.add(
        CampaignWorldConfig(
            campaign_id=campaign.id,
            settings_json={
                "schema_version": 2,
                "inventory_mode": "axis",
                "supply_demand_enabled": True,
                "market_volatility": 10,
                "ranges": {},
            },
            schema_version=2,
        )
    )
    db.session.commit()

    client = flask_app.test_client()
    seed_client_session(client, user, campaign_id=campaign.id)

    resp = client.get("/gm/market-overview")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data is not None
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "Rope"
    assert data["market_volatility"] == 10
