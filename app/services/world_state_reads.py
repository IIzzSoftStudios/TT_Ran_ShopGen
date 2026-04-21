"""Resolve shop prices/stock from GMWorldState.state_json when READ_PRICES_FROM_WORLD_STATE is enabled."""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.constants.simulation_flags import READ_PRICES_FROM_WORLD_STATE
from app.models import GMWorldState


def _state_map(gm_profile_id: int) -> Optional[Dict[str, Any]]:
    if not READ_PRICES_FROM_WORLD_STATE:
        return None
    row = GMWorldState.query.filter_by(gm_profile_id=gm_profile_id).first()
    if not row or not row.state_json:
        return None
    return row.state_json if isinstance(row.state_json, dict) else None


def get_effective_price(
    gm_profile_id: int,
    inventory_id: int,
    fallback: float,
) -> float:
    """Return dynamic_price from world state JSON (key=str inventory_id) or fallback."""
    m = _state_map(gm_profile_id)
    if not m:
        return fallback
    entry = m.get(str(inventory_id))
    if isinstance(entry, dict) and "dynamic_price" in entry:
        try:
            return float(entry["dynamic_price"])
        except (TypeError, ValueError):
            return fallback
    return fallback


def get_effective_stock(
    gm_profile_id: int,
    inventory_id: int,
    fallback: int,
) -> int:
    m = _state_map(gm_profile_id)
    if not m:
        return fallback
    entry = m.get(str(inventory_id))
    if isinstance(entry, dict) and "stock" in entry:
        try:
            return int(entry["stock"])
        except (TypeError, ValueError):
            return fallback
    return fallback
