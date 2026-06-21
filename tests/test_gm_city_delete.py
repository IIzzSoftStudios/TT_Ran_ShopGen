"""GM city delete: regional_markets must not block parent row removal."""

import pytest
from flask import Flask

from app.extensions import db
from app.models import (
    Campaign,
    City,
    GMProfile,
    Item,
    RegionalMarket,
    Region,
    User,
    shop_cities,
)
from app.routes.handlers.gm_helpers import purge_city_dependencies


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


def test_purge_city_dependencies_allows_city_delete(app_ctx):
    user = User(username="gm_city_del", password="x", role="GM")
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
    region = Region(campaign_id=campaign.id, name="North")
    db.session.add(region)
    db.session.flush()
    city = City(
        campaign_id=campaign.id,
        name="Ironhold",
        region_id=region.id,
        region="North",
    )
    db.session.add(city)
    db.session.flush()
    item = Item(
        campaign_id=campaign.id,
        name="Iron",
        type="Material",
        rarity="common",
        base_price=1,
    )
    db.session.add(item)
    db.session.flush()
    db.session.add(
        RegionalMarket(
            city_id=city.city_id,
            item_id=item.item_id,
            campaign_id=campaign.id,
            average_price=1.0,
        )
    )
    db.session.commit()
    city_id = city.city_id

    purge_city_dependencies(city_id)
    db.session.delete(city)
    db.session.commit()

    assert City.query.filter_by(city_id=city_id).count() == 0
    assert RegionalMarket.query.filter_by(city_id=city_id).count() == 0
