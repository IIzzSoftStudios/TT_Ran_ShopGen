"""Bootstrap the shared public Demo campaign (no Items).

Creates (or reuses) the system Demo GM + a campaign named ``Demo World``,
runs normal world generation, strips all Item-scoped rows, ensures a world
map canvas exists, marks setup complete, and writes
``DEMO_TEMPLATE_CAMPAIGN_ID`` into ``config.env``.

Usage (from TT_Ran_ShopGen/):
    python scripts/bootstrap_demo_world.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app as flask_app
from app.extensions import db
from app.models import (
    Campaign,
    CampaignWorldConfig,
    GlobalMarket,
    Item,
    PriceHistory,
    RegionalMarket,
    ShopInventory,
)
from app.scripts.seeder import _default_settings
from app.services import gm_maps
from app.services.demo_session import DEMO_SYSTEM_USERNAME, ensure_demo_system_user
from app.services.world_generator import generator as wg_generator
from app.services.world_generator.defaults import SCHEMA_VERSION
from app.services.world_setup_state import SETUP_STAGE_COMPLETE


DEMO_CAMPAIGN_NAME = "Demo World"
CONFIG_ENV_PATH = ROOT / "config.env"


def _strip_items_for_campaign(campaign_id: int) -> dict[str, int]:
    """Remove item pool + dependent market/inventory rows for one campaign."""
    counts = {}
    counts["shop_inventory"] = (
        db.session.query(ShopInventory)
        .filter_by(campaign_id=campaign_id)
        .delete(synchronize_session=False)
    )
    counts["price_history"] = (
        db.session.query(PriceHistory)
        .filter_by(campaign_id=campaign_id)
        .delete(synchronize_session=False)
    )
    counts["regional_markets"] = (
        db.session.query(RegionalMarket)
        .filter_by(campaign_id=campaign_id)
        .delete(synchronize_session=False)
    )
    counts["global_markets"] = (
        db.session.query(GlobalMarket)
        .filter_by(campaign_id=campaign_id)
        .delete(synchronize_session=False)
    )
    counts["items"] = (
        db.session.query(Item)
        .filter_by(campaign_id=campaign_id)
        .delete(synchronize_session=False)
    )
    return counts


def _upsert_demo_campaign(gm_profile_id: int) -> Campaign:
    existing = (
        Campaign.query.filter_by(
            gm_profile_id=gm_profile_id,
            name=DEMO_CAMPAIGN_NAME,
            is_active=True,
        )
        .order_by(Campaign.id.asc())
        .first()
    )
    if existing is not None:
        return existing
    campaign = Campaign(
        gm_profile_id=gm_profile_id,
        name=DEMO_CAMPAIGN_NAME,
        system_type="dnd5e",
        is_active=True,
        current_game_day=1,
    )
    db.session.add(campaign)
    db.session.flush()
    return campaign


def _write_config_env_campaign_id(campaign_id: int) -> None:
    key = "DEMO_TEMPLATE_CAMPAIGN_ID"
    line = f"{key}={campaign_id}\n"
    if not CONFIG_ENV_PATH.exists():
        CONFIG_ENV_PATH.write_text(line, encoding="utf-8")
        return
    text = CONFIG_ENV_PATH.read_text(encoding="utf-8")
    pattern = re.compile(rf"(?m)^\s*#?\s*{key}\s*=.*$")
    if pattern.search(text):
        text = pattern.sub(f"{key}={campaign_id}", text, count=1)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += f"\n# Public Demo template campaign (landing Try Demo)\n{line}"
    CONFIG_ENV_PATH.write_text(text, encoding="utf-8")


def main() -> int:
    with flask_app.app_context():
        demo_user = ensure_demo_system_user()
        profile = demo_user.gm_profile
        assert profile is not None

        campaign = _upsert_demo_campaign(profile.id)
        settings = _default_settings(
            num_cities=6,
            num_shops_per_city=4,
            num_global_items=50,
            num_items_per_shop=5,
        )
        settings["campaign_name"] = DEMO_CAMPAIGN_NAME
        settings["setup_stage"] = SETUP_STAGE_COMPLETE
        settings["pending_generation"] = False

        config = CampaignWorldConfig.query.filter_by(campaign_id=campaign.id).first()
        if config is None:
            config = CampaignWorldConfig(
                campaign_id=campaign.id,
                settings_json=settings,
                schema_version=SCHEMA_VERSION,
                world_seed=settings["world_seed"],
            )
            db.session.add(config)
        else:
            config.settings_json = settings
            config.schema_version = SCHEMA_VERSION
            config.world_seed = settings["world_seed"]
        db.session.flush()

        # Wipe prior generated economy if re-running, then regenerate.
        from app.models import City, Region, Shop, SimulationState

        db.session.query(ShopInventory).filter_by(campaign_id=campaign.id).delete(
            synchronize_session=False
        )
        db.session.query(PriceHistory).filter_by(campaign_id=campaign.id).delete(
            synchronize_session=False
        )
        db.session.query(RegionalMarket).filter_by(campaign_id=campaign.id).delete(
            synchronize_session=False
        )
        db.session.query(GlobalMarket).filter_by(campaign_id=campaign.id).delete(
            synchronize_session=False
        )
        db.session.query(Item).filter_by(campaign_id=campaign.id).delete(
            synchronize_session=False
        )
        # Shops may be linked via association table; delete shops/cities/regions.
        shops = Shop.query.filter_by(campaign_id=campaign.id).all()
        for shop in shops:
            shop.cities.clear()
        db.session.flush()
        db.session.query(Shop).filter_by(campaign_id=campaign.id).delete(
            synchronize_session=False
        )
        db.session.query(City).filter_by(campaign_id=campaign.id).delete(
            synchronize_session=False
        )
        db.session.query(Region).filter_by(campaign_id=campaign.id).delete(
            synchronize_session=False
        )
        db.session.query(SimulationState).filter_by(campaign_id=campaign.id).delete(
            synchronize_session=False
        )
        db.session.flush()

        result = wg_generator.generate(campaign_id=campaign.id, settings=settings)
        stripped = _strip_items_for_campaign(campaign.id)

        config.world_seed = result.effective_seed
        updated = dict(config.settings_json or {})
        updated["world_seed"] = result.effective_seed
        updated["setup_stage"] = SETUP_STAGE_COMPLETE
        updated["pending_generation"] = False
        updated["campaign_name"] = DEMO_CAMPAIGN_NAME
        config.settings_json = updated

        canvas = gm_maps.get_or_create_world_canvas(
            campaign.id,
            seed=result.effective_seed,
            settings=updated,
        )
        db.session.flush()

        flask_app.config["DEMO_TEMPLATE_CAMPAIGN_ID"] = str(campaign.id)
        db.session.commit()

        _write_config_env_campaign_id(campaign.id)

        print(
            f"Demo world ready: campaign_id={campaign.id} "
            f"user={DEMO_SYSTEM_USERNAME} "
            f"regions={result.n_regions} cities={result.n_cities} "
            f"shops={result.n_shops} items_stripped={stripped['items']} "
            f"canvas_id={canvas.id} seed={result.effective_seed}"
        )
        print(f"Wrote {CONFIG_ENV_PATH} DEMO_TEMPLATE_CAMPAIGN_ID={campaign.id}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
