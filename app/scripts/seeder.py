"""World seeding for GM campaigns.

Phase 1 makes `seed_gm_data` a thin compatibility shim around
`world_generator.generator.generate`. It synthesizes a default
`CampaignWorldConfig.settings_json` (Medieval-leaning world, 4 cities,
etc.), uses a fixed `world_seed=1` for deterministic test output, and
delegates to the real generator.

Unlike the request-path handler, this shim auto-creates the
CampaignWorldConfig row (if a campaign_id is provided) and commits.
Callers that don't have a campaign available can still invoke it --
only the generator's gm_profile-scoped entities are created in that
case.

Campaign rows created through the ORM get ``join_code`` values from
SQLAlchemy ``before_insert`` listeners (see ``app.models``); this script
does not construct ``Player`` rows.
"""

from __future__ import annotations

from typing import Optional

from app.extensions import db
from app.models import Campaign, CampaignWorldConfig
from app.services.world_generator import generator as wg_generator
from app.services.world_generator.defaults import (
    RANGE_SETTINGS,
    SCHEMA_VERSION,
)


def _default_settings(
    num_cities: Optional[int] = None,
    num_shops_per_city: Optional[int] = None,
    num_global_items: Optional[int] = None,
    num_items_per_shop: Optional[int] = None,
) -> dict:
    """Return a normalized settings_json matching validator.validate's output.

    Legacy kwargs override the `defaults.RANGE_SETTINGS` midpoints so old
    call sites keep working (they get a world roughly the size they asked
    for, bounded by the new floors/ceilings).
    """
    ranges = {}
    overrides = {
        "num_cities": num_cities,
        "shops_per_city": num_shops_per_city,
        "items_per_shop": num_items_per_shop,
        "global_item_pool_size": num_global_items,
    }
    for key, (floor, ceiling, d_min, d_max) in RANGE_SETTINGS.items():
        ov = overrides.get(key)
        if ov is not None:
            clamped = max(floor, min(ceiling, int(ov)))
            ranges[key] = {"min": clamped, "max": clamped}
        else:
            ranges[key] = {"min": d_min, "max": d_max}
    # Medieval-leaning fused axis for test stability.
    ranges["tech_magic_balance"] = {"min": 4, "max": 6}

    return {
        "schema_version": SCHEMA_VERSION,
        "campaign_name": "(seeded)",
        "system_type": "dnd5e",
        "world_seed": 1,  # deterministic: test fixtures rely on this
        "ranges": ranges,
    }


def seed_gm_data(
    gm_profile_id: int,
    *,
    num_cities: int = 10,
    num_shops_per_city: int = 10,
    num_global_items: int = 75,
    num_items_per_shop: int = 10,
    campaign_id: Optional[int] = None,
) -> bool:
    """Populate demo content for a GM profile via the real generator.

    If ``campaign_id`` is provided, a ``CampaignWorldConfig`` row is
    created too so the generator can be driven end-to-end. Commits on
    success; rolls back and re-raises on failure.
    """
    settings = _default_settings(
        num_cities=num_cities,
        num_shops_per_city=num_shops_per_city,
        num_global_items=num_global_items,
        num_items_per_shop=num_items_per_shop,
    )

    # Without a campaign the generator still needs a stable campaign_id so
    # Region / CampaignWorldConfig FKs resolve. Fall back to the first
    # active campaign for this GM profile.
    resolved_campaign_id = campaign_id
    if resolved_campaign_id is None:
        campaign = (
            Campaign.query.filter_by(
                gm_profile_id=gm_profile_id, is_active=True
            )
            .order_by(Campaign.created_at.asc())
            .first()
        )
        if campaign is not None:
            resolved_campaign_id = campaign.id

    if resolved_campaign_id is None:
        # Nothing to attach the world to -- maintain the old no-op contract.
        return True

    try:
        existing_config = (
            db.session.query(CampaignWorldConfig)
            .filter_by(campaign_id=resolved_campaign_id)
            .first()
        )
        if existing_config is None:
            config = CampaignWorldConfig(
                campaign_id=resolved_campaign_id,
                settings_json=settings,
                schema_version=SCHEMA_VERSION,
                world_seed=settings["world_seed"],
            )
            db.session.add(config)
            db.session.flush()
        else:
            existing_config.settings_json = settings
            existing_config.world_seed = settings["world_seed"]

        result = wg_generator.generate(
            campaign_id=resolved_campaign_id,
            settings=settings,
        )

        # Persist resolved seed even though it was fixed -- keeps the
        # config row consistent with what the generator actually used.
        if existing_config is None:
            config.world_seed = result.effective_seed
        else:
            existing_config.world_seed = result.effective_seed

        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        raise
