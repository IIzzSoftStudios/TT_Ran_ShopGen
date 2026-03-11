"""
Bridges sim_core to the Flask app: builds PersistenceAdapter with warm_callback that writes MarketPulse to PostgreSQL.
Provides a single runner that holds SimState, PersistenceAdapter, SimulationLoop, and Watch List for Observer.
"""
import os
import threading
from typing import Set, Callable, Optional, Any

from app.services.sim_core import SimState, PersistenceAdapter, SimulationLoop
from app.services.sim_core.loop import compute_market_pulse


def make_warm_callback(app, sim_id: str):
    """Build a fire-and-forget callback that inserts one MarketPulse row (raw insert or ORM in background)."""
    def _insert_pulse(pulse: dict) -> None:
        with app.app_context():
            from app.extensions import db
            from app.models.backend import MarketPulse
            from datetime import datetime
            try:
                db.session.add(MarketPulse(
                    sim_id=sim_id,
                    tick=pulse["tick"],
                    mean_price=pulse["mean_price"],
                    median_gold=pulse["median_gold"],
                    volume=pulse["volume"],
                    std_price=pulse["std_price"],
                    recorded_at=datetime.utcnow(),
                ))
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"[Warm] insert error: {e}")
    return _insert_pulse


class SimRunner:
    """
    Holds state, persistence, loop, watch list. Runs the sim in a background thread.
    Broadcast callback receives (pulse, agents) each tick; runner can push to a queue for WebSocket.
    """

    __slots__ = (
        "app", "sim_id", "num_agents", "state", "persistence", "loop",
        "watch_list", "broadcast_queue", "thread", "running", "_pulse_callback"
    )

    def __init__(
        self,
        app,
        num_agents: int = 300_000,
        ring_buffer_ticks: int = 60,
        cold_batch_size: int = 100,
        sim_id: str = "default",
    ):
        self.app = app
        self.sim_id = sim_id
        self.num_agents = num_agents
        self.watch_list = set()  # type: Set[int]  # city_ids being watched
        self.broadcast_queue = None  # Optional[queue.Queue] - set by API to receive (pulse, city_slices)
        self.thread = None
        self.running = False
        self._pulse_callback = None  # set to push pulse + slices to broadcast_queue

        blob_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "sim_blobs")
        warm_cb = make_warm_callback(app, sim_id)

        self.state = SimState(num_agents=num_agents, ring_buffer_ticks=ring_buffer_ticks)
        self.persistence = PersistenceAdapter(
            num_agents=num_agents,
            batch_size=cold_batch_size,
            blob_dir=blob_dir,
            sim_id=sim_id,
            warm_callback=warm_cb,
        )
        self.loop = SimulationLoop(
            state=self.state,
            persistence=self.persistence,
            tick_interval_sec=1.0,
            broadcast_callback=self._on_tick,
        )
        self._seed_agents()

    def _seed_agents(self) -> None:
        """Initialize agents with placeholder data (single source of truth in NumPy)."""
        import numpy as np
        n = self.num_agents
        rng = np.random.default_rng(42)
        self.state.agents["agent_id"] = np.arange(n, dtype=np.uint32)
        self.state.agents["city_id"] = np.uint16(np.arange(n) % 1000)  # up to 1000 cities
        self.state.agents["gold"] = np.float32(100.0 + rng.random(n) * 50)
        self.state.agents["inventory_count"] = np.uint16(rng.integers(0, 100, n))
        self.state.agents["base_price"] = np.float32(10.0 + rng.random(n) * 40)
        self.state.agents["strategy_flags"] = np.uint8(rng.integers(0, 4, n))
        self.state.agents["last_transaction_vol"] = np.float32(0.01)

    def _on_tick(self, pulse: dict, agents) -> None:
        """Called from sim loop each tick: push pulse and watched city slices to broadcast queue."""
        if self._pulse_callback:
            city_slices = {}
            for city_id in self.watch_list:
                view = self.state.slice_by_city(city_id)
                city_slices[city_id] = view.tobytes() if len(view) > 0 else b""
            self._pulse_callback(pulse, city_slices)

    def subscribe_city(self, city_id: int) -> None:
        self.watch_list.add(int(city_id))

    def unsubscribe_city(self, city_id: int) -> None:
        self.watch_list.discard(int(city_id))

    def set_broadcast_callback(self, cb: Callable[[dict, dict], None]) -> None:
        """cb(pulse, city_slices) where city_slices is {city_id: bytes}."""
        self._pulse_callback = cb

    def start_background(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.running = True
        self.thread = threading.Thread(
            target=self.loop.run_until_stopped,
            kwargs={"stop_check": lambda: not self.running},
            daemon=True,
        )
        self.thread.start()

    def stop(self) -> None:
        self.running = False
        self.loop.stop()
        if self.thread:
            self.thread.join(timeout=5.0)
        self.persistence.shutdown()

    def get_latest_pulse(self) -> Optional[dict]:
        """Return last computed pulse (from ring buffer or current state)."""
        if self.state.current_tick == 0:
            return None
        return compute_market_pulse(self.state.agents, self.state.current_tick - 1)

    def get_city_slice_bytes(self, city_id: int) -> bytes:
        """Observer: return binary slice for a city (for WebSocket or REST)."""
        view = self.state.slice_by_city(int(city_id))
        return view.tobytes() if len(view) > 0 else b""
