"""Resolve shop prices/stock from GMWorldState.state_json when READ_PRICES_FROM_WORLD_STATE is enabled.

State authority (Phase 3)
-------------------------
Row tables remain **authoritative for player-facing reads** while
``READ_PRICES_FROM_WORLD_STATE`` is false (the default):

- ``ShopInventory.dynamic_price`` and ``ShopInventory.stock``
- ``PriceHistory`` (append-only tick audit)
- ``Campaign.current_game_day`` and ``SimulationState.current_tick``

``GMWorldState`` is a **dual-write snapshot cache** when ``WORLD_STATE_ENABLED`` is
true (also the default). The canonical tick path in ``SimulationEngine.run_tick``
writes inventory prices/stock to rows first, then mirrors them into
``GMWorldState.state_json`` in the same transaction. The blob is not safe to read
for purchase or display decisions until row/blob reconciliation is proven and
``READ_PRICES_FROM_WORLD_STATE`` is deliberately enabled with a reconciliation
strategy for buy/sell paths.

Flag split (intentional, unchanged in Phase 3):

- ``WORLD_STATE_ENABLED`` — controls tick **writes** to ``GMWorldState``.
- ``READ_PRICES_FROM_WORLD_STATE`` — controls route **reads** from the blob; off by
  default so callers fall back to row values via the ``fallback`` arguments below.

When reads are disabled, missing blob rows, malformed ``state_json``, or invalid
entry shapes all resolve to the caller-supplied row fallback — never raise.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.constants.simulation_flags import READ_PRICES_FROM_WORLD_STATE
from app.models import GMWorldState


def _state_map(campaign_id: int) -> Optional[Dict[str, Any]]:
    if not READ_PRICES_FROM_WORLD_STATE:
        return None
    row = GMWorldState.query.filter_by(campaign_id=campaign_id).first()
    if not row or not row.state_json:
        return None
    return row.state_json if isinstance(row.state_json, dict) else None


def get_effective_price(
    campaign_id: int,
    inventory_id: int,
    fallback: float,
) -> float:
    """Return dynamic_price from world state JSON (key=str inventory_id) or row fallback."""
    m = _state_map(campaign_id)
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
    campaign_id: int,
    inventory_id: int,
    fallback: int,
) -> int:
    """Return stock from world state JSON (key=str inventory_id) or row fallback."""
    m = _state_map(campaign_id)
    if not m:
        return fallback
    entry = m.get(str(inventory_id))
    if isinstance(entry, dict) and "stock" in entry:
        try:
            return int(entry["stock"])
        except (TypeError, ValueError):
            return fallback
    return fallback
