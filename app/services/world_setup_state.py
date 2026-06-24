"""Campaign world-setup stage tracking (map-first wizard)."""

from __future__ import annotations

from typing import Any

from flask import redirect, url_for

from app.models import Campaign, CampaignWorldConfig
from app.services.world_generator import defaults as wg_defaults

SETUP_STAGE_MAP = "map_builder"
SETUP_STAGE_ECONOMY = "economy"
SETUP_STAGE_COMPLETE = "complete"

MAP_VISUAL_RANGE_KEYS = (
    "map_landmass_scale",
    "map_waterways",
    "map_terrain_roughness",
)

ECONOMY_RANGE_KEYS = (
    "num_regions",
    "num_cities",
    "population_scale",
    "global_item_pool_size",
    "city_size_variation",
    "items_per_shop",
    "tech_magic_balance",
)


def default_draft_ranges() -> dict[str, dict[str, int]]:
    return {
        key: {"min": d_min, "max": d_max}
        for key, (_floor, _ceiling, d_min, d_max) in wg_defaults.RANGE_SETTINGS.items()
    }


def build_draft_settings(campaign_name: str, system_type: str) -> dict[str, Any]:
    """Initial settings_json after step 1 (identity) creates the campaign shell."""
    return {
        "schema_version": wg_defaults.SCHEMA_VERSION,
        "campaign_name": campaign_name,
        "system_type": system_type,
        "setup_stage": SETUP_STAGE_MAP,
        "pending_generation": True,
        "ranges": default_draft_ranges(),
        "species_distribution": [
            {"name": name, "percent": percent, "source": "default"}
            for name, percent in wg_defaults.DEFAULT_SPECIES_DISTRIBUTION
        ],
        "inventory_mode": "axis",
        "supply_demand_enabled": True,
        "market_volatility": 5,
        "world_seed": None,
    }


def get_world_config(campaign_id: int) -> CampaignWorldConfig | None:
    return CampaignWorldConfig.query.filter_by(campaign_id=campaign_id).first()


def settings_for_campaign(campaign: Campaign) -> dict[str, Any]:
    config = get_world_config(campaign.id)
    if config is None or not config.settings_json:
        return {}
    return dict(config.settings_json)


def is_pending_setup(settings: dict[str, Any] | None) -> bool:
    if not settings:
        return False
    if settings.get("generation_skipped"):
        return False
    return bool(settings.get("pending_generation"))


def setup_stage(settings: dict[str, Any] | None) -> str | None:
    if not settings or not is_pending_setup(settings):
        return None
    stage = settings.get("setup_stage")
    if stage in (SETUP_STAGE_MAP, SETUP_STAGE_ECONOMY):
        return stage
    return SETUP_STAGE_MAP


def setup_resume_url(settings: dict[str, Any] | None) -> str | None:
    stage = setup_stage(settings)
    if stage == SETUP_STAGE_MAP:
        return url_for("gm.generate_world_map")
    if stage == SETUP_STAGE_ECONOMY:
        return url_for("gm.generate_world_economy_form")
    return None


def redirect_for_setup_stage(settings: dict[str, Any] | None):
    """Return a Flask redirect to the correct wizard step, or None if complete."""
    target = setup_resume_url(settings)
    if target is None:
        return None
    return redirect(target, code=303)


def mark_setup_complete(settings: dict[str, Any]) -> dict[str, Any]:
    updated = dict(settings)
    updated["setup_stage"] = SETUP_STAGE_COMPLETE
    updated["pending_generation"] = False
    return updated


def mark_setup_economy(settings: dict[str, Any]) -> dict[str, Any]:
    updated = dict(settings)
    updated["setup_stage"] = SETUP_STAGE_ECONOMY
    updated["pending_generation"] = True
    return updated


def mark_setup_map(settings: dict[str, Any]) -> dict[str, Any]:
    """Return to the map-builder step (wizard back navigation)."""
    updated = dict(settings)
    updated["setup_stage"] = SETUP_STAGE_MAP
    updated["pending_generation"] = True
    return updated


def merge_map_ranges_from_form(
    settings: dict[str, Any], form: dict[str, Any]
) -> dict[str, Any]:
    """Persist map-visual slider values from step 2 continue POST."""
    updated = dict(settings)
    ranges = dict(updated.get("ranges") or default_draft_ranges())
    for key in MAP_VISUAL_RANGE_KEYS:
        floor, ceiling, _d_min, _d_max = wg_defaults.RANGE_SETTINGS[key]
        lo_raw = form.get(f"{key}_min", ranges.get(key, {}).get("min", _d_min))
        hi_raw = form.get(f"{key}_max", ranges.get(key, {}).get("max", _d_max))
        try:
            lo = max(floor, min(ceiling, int(lo_raw)))
            hi = max(floor, min(ceiling, int(hi_raw)))
        except (TypeError, ValueError):
            lo, hi = _d_min, _d_max
        if lo > hi:
            lo, hi = hi, lo
        ranges[key] = {"min": lo, "max": hi}
    updated["ranges"] = ranges
    return updated
