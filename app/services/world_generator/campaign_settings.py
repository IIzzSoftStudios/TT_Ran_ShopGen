"""Read/update per-campaign world settings on ``CampaignWorldConfig``."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm.attributes import flag_modified

from app.extensions import db
from app.models import CampaignWorldConfig
from app.services.world_generator.defaults import RANGE_SETTINGS, SCHEMA_VERSION
from app.services.world_generator.settings_resolve import supply_demand_enabled


def _default_ranges() -> Dict[str, Dict[str, int]]:
    return {
        key: {"min": d_min, "max": d_max}
        for key, (_floor, _ceil, d_min, d_max) in RANGE_SETTINGS.items()
    }


def _minimal_settings_json() -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "inventory_mode": "axis",
        "supply_demand_enabled": True,
        "ranges": _default_ranges(),
    }


def get_world_config(campaign_id: int) -> Optional[CampaignWorldConfig]:
    return CampaignWorldConfig.query.filter_by(campaign_id=campaign_id).first()


def normalize_settings_json(raw: Any) -> Dict[str, Any]:
    """Coerce persisted JSON/JSONB into a dict (some drivers return a JSON string)."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def read_supply_demand_flag(campaign_id: int) -> bool:
    """Effective supply/demand flag (legacy campaigns without config default to on)."""
    cfg = get_world_config(campaign_id)
    if cfg is None:
        return True
    settings = normalize_settings_json(cfg.settings_json)
    if not settings:
        return True
    return supply_demand_enabled(settings)


def toggle_supply_demand(campaign_id: int) -> Tuple[bool, CampaignWorldConfig]:
    """Flip ``supply_demand_enabled``; create a minimal config row if missing."""
    cfg = get_world_config(campaign_id)
    if cfg is None:
        # Implicit default is on; first toggle turns supply off and persists that choice.
        settings = _minimal_settings_json()
        settings["supply_demand_enabled"] = False
        cfg = CampaignWorldConfig(
            campaign_id=campaign_id,
            settings_json=settings,
            schema_version=SCHEMA_VERSION,
        )
        db.session.add(cfg)
        return False, cfg

    settings = deepcopy(normalize_settings_json(cfg.settings_json))
    if not settings:
        settings = _minimal_settings_json()
    new_value = not supply_demand_enabled(settings)
    settings["supply_demand_enabled"] = new_value
    cfg.settings_json = settings
    flag_modified(cfg, "settings_json")
    return new_value, cfg
