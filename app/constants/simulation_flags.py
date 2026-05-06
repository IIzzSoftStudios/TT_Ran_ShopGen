"""Feature flags and benchmark notes for simulation / world state (Phase 1+)."""

import os

# Must match DB CHECK on simulation_state.speed and every set_simulation_speed endpoint.
ALLOWED_SIMULATION_SPEEDS = frozenset(
    ("pause", "1x", "5x", "10x", "100x", "1000x")
)

# When False: ShopInventory + PriceHistory remain authoritative; GMWorldState is not written on tick.
# When True (default): tick persists GMWorldState (tick_seq / updated_at every tick; state_json when inventory runs).
# Opt out with WORLD_STATE_ENABLED=false. READ_PRICES_FROM_WORLD_STATE remains separate (off by default).
WORLD_STATE_ENABLED = os.getenv("WORLD_STATE_ENABLED", "true").lower() in ("true", "1", "yes")


def world_state_writes_enabled() -> bool:
    """Read env at call time (not import time) so workers always see values from load_dotenv."""
    return os.getenv("WORLD_STATE_ENABLED", "true").lower() in ("true", "1", "yes")

# Player/market routes: resolve prices from GMWorldState.state_json when True (requires WORLD_STATE_ENABLED writes to populate).
READ_PRICES_FROM_WORLD_STATE = os.getenv(
    "READ_PRICES_FROM_WORLD_STATE", "false"
).lower() in ("true", "1", "yes")

# P99 tick_duration target (seconds). Phase 1 instrumentation establishes N_max empirically; do not assume 33ms until measured.
TICK_BUDGET_SECONDS = 0.033

# Back-of-envelope: after DB + ORM collapse, Python pricing loop may dominate — benchmark N_items, not concurrent GMs alone.
BENCHMARK_NOTE = (
    "Measure P99 tick_duration vs inventory row count (N_items); 3500 GMs is concurrency, not per-tick row count."
)
