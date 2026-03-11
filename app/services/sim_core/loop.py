"""
Core simulation loop: fixed timestep, catch-up, and tick budget.
Phases: Logic (agent decisions), Agg (Market Pulse), Record (ring buffer), Warm (async), Broadcast (callback), Cold (stage).
"""
import time
import math
from typing import Callable, Optional

import numpy as np
from .dtypes import AGENT_DTYPE, PULSE_DTYPE
from .state import SimState
from .persistence import PersistenceAdapter


def _default_logic(agents: np.ndarray, tick: int) -> None:
    """
    Placeholder: advance agent state in-place (e.g. perturb gold and base_price).
    Replace with Numba @njit hot path for production.
    """
    n = len(agents)
    if n == 0:
        return
    # Small deterministic-ish perturbations so we have non-trivial pulse
    np.add(agents["gold"], np.float32(0.1 * (tick % 10 - 5)), out=agents["gold"])
    agents["gold"] = np.maximum(agents["gold"], 0.0)
    np.add(agents["base_price"], np.float32(0.01 * ((tick * 7) % 11 - 5)), out=agents["base_price"])
    agents["base_price"] = np.maximum(agents["base_price"], 0.01)
    agents["last_transaction_vol"] = np.float32(0.01)  # placeholder volume


def compute_market_pulse(agents: np.ndarray, current_tick: int) -> dict:
    """
    NumPy vectorized aggregation in one shot. Returns dict for warm storage and broadcast.
    """
    if len(agents) == 0:
        return {
            "tick": current_tick,
            "mean_price": 0.0,
            "median_gold": 0.0,
            "volume": 0.0,
            "std_price": 0.0,
        }
    mean_price = float(np.mean(agents["base_price"]))
    median_gold = float(np.median(agents["gold"]))
    volume = float(np.sum(agents["last_transaction_vol"]))
    std_price = float(np.std(agents["base_price"]))
    if math.isnan(std_price):
        std_price = 0.0
    return {
        "tick": current_tick,
        "mean_price": mean_price,
        "median_gold": median_gold,
        "volume": volume,
        "std_price": std_price,
    }


class SimulationLoop:
    """
    Runs the sim loop with a 1000 ms tick budget. Uses fixed timestep and catch-up.
    """

    def __init__(
        self,
        state: SimState,
        persistence: PersistenceAdapter,
        tick_interval_sec: float = 1.0,
        logic_callback: Optional[Callable[[np.ndarray, int], None]] = None,
        broadcast_callback: Optional[Callable[[dict, np.ndarray], None]] = None,
    ):
        self.state = state
        self.persistence = persistence
        self.tick_interval_sec = tick_interval_sec
        self.logic_callback = logic_callback or _default_logic
        self.broadcast_callback = broadcast_callback
        self.next_tick_time = time.time()
        self._running = False

    def run_one_tick(self) -> dict:
        """
        Execute one tick: logic -> agg -> record -> warm -> broadcast -> cold.
        Returns pulse dict and updates ring buffer / persistence.
        """
        t0 = time.perf_counter()
        agents = self.state.agents
        current_tick = self.state.current_tick

        # Logic: agent decisions (Numba in production)
        self.logic_callback(agents, current_tick)

        # Agg: Market Pulse
        pulse = compute_market_pulse(agents, current_tick)

        # Record: update ring buffer (pointer arithmetic)
        self.state.write_to_ring()

        # Warm: fire-and-forget to PostgreSQL
        self.persistence.push_warm(pulse)

        # Broadcast: caller can push to WebSocket queue (Observer slices + pulse)
        if self.broadcast_callback:
            self.broadcast_callback(pulse, agents)

        # Cold: stage for blob (when buffer full, adapter flushes async)
        self.persistence.stage_tick(agents)

        elapsed = time.perf_counter() - t0
        pulse["_tick_duration_ms"] = elapsed * 1000
        return pulse

    def run_until_stopped(self, stop_check: Optional[Callable[[], bool]] = None) -> None:
        """
        Fixed timestep loop: sleep_time = max(0, next_tick_time - time.time()).
        Catch-up: if a tick takes > interval, next tick starts immediately.
        """
        self._running = True
        while self._running:
            if stop_check and stop_check():
                break
            self.run_one_tick()
            self.next_tick_time += self.tick_interval_sec
            sleep_time = max(0.0, self.next_tick_time - time.time())
            if sleep_time > 0:
                time.sleep(sleep_time)
            # If we're behind, next_tick_time is in the past and sleep_time is 0 -> catch-up

    def stop(self) -> None:
        self._running = False
