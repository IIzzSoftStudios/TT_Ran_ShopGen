"""GM shop delete: price_history must not block parent row removal."""

import pytest
from flask import Flask

from app.extensions import db
from app.models import (
    Campaign,
    City,
    GMProfile,
    Item,
    PriceHistory,
    Shop,
    ShopInventory,
    User,
    shop_cities,
)
from app.routes.handlers.gm_helpers import purge_shop_dependencies


@pytest.fixture()
def app_ctx():
    flask_app = Flask(__name__)
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(flask_app)
    with flask_app.app_context():
        db.create_all()
        yield
        db.session.remove()
        db.drop_all()


def test_purge_shop_dependencies_allows_shop_delete(app_ctx):
    user = User(username="gm_shop_del", password="x", role="GM")
    db.session.add(user)
    db.session.flush()
    gm = GMProfile(user_id=user.id)
    db.session.add(gm)
    db.session.flush()
    campaign = Campaign(
        gm_profile_id=gm.id,
        name="Test",
        system_type="generic",
        is_active=True,
    )
    db.session.add(campaign)
    db.session.flush()
    city = City(campaign_id=campaign.id, name="Ironhold", region="North")
    shop = Shop(campaign_id=campaign.id, name="Forge", type="blacksmith")
    db.session.add_all([city, shop])
    db.session.flush()
    db.session.execute(
        shop_cities.insert().values(shop_id=shop.shop_id, city_id=city.city_id)
    )
    item = Item(
        campaign_id=campaign.id,
        name="Iron",
        type="Material",
        rarity="common",
        base_price=1,
    )
    db.session.add(item)
    db.session.flush()
    db.session.add_all(
        [
            ShopInventory(
                shop_id=shop.shop_id,
                item_id=item.item_id,
                campaign_id=campaign.id,
                stock=1,
                dynamic_price=1.0,
            ),
            PriceHistory(
                shop_id=shop.shop_id,
                item_id=item.item_id,
                campaign_id=campaign.id,
                price=1.0,
            ),
        ]
    )
    db.session.commit()
    shop_id = shop.shop_id

    purge_shop_dependencies(shop_id)
    db.session.delete(shop)
    db.session.commit()

    assert Shop.query.filter_by(shop_id=shop_id).count() == 0
    assert PriceHistory.query.filter_by(shop_id=shop_id).count() == 0
    assert ShopInventory.query.filter_by(shop_id=shop_id).count() == 0
