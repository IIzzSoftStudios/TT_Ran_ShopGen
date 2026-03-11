"""
In-memory sim state: single NumPy agents array (single source of truth) and pre-allocated ring buffer.
Never convert agents to Python dicts/objects; keep everything in NumPy from start to shutdown.
"""
import numpy as np
from .dtypes import AGENT_DTYPE


class SimState:
    """
    Holds the current agent array and a ring buffer of the last N ticks.
    Pointer logic: write at index (current_tick % buffer_len) to overwrite oldest.
    """

    __slots__ = ("agents", "history", "buffer_len", "current_tick", "num_agents")

    def __init__(self, num_agents: int, ring_buffer_ticks: int = 60):
        self.num_agents = num_agents
        self.buffer_len = ring_buffer_ticks
        # Current tick state: one row per agent
        self.agents = np.zeros(num_agents, dtype=AGENT_DTYPE)
        # Pre-allocated ring buffer: (ticks, agents) — no per-tick allocations
        self.history = np.zeros((ring_buffer_ticks, num_agents), dtype=AGENT_DTYPE)
        self.current_tick = 0

    def write_to_ring(self) -> None:
        """Copy current agents into the ring buffer at the slot for current_tick. Call after each tick."""
        slot = int(self.current_tick % self.buffer_len)
        self.history[slot] = self.agents
        self.current_tick += 1

    def get_history_slot(self, ticks_ago: int):
        """Get state from N ticks ago (0 = last tick). Returns a view."""
        if ticks_ago < 0 or ticks_ago >= self.buffer_len:
            raise IndexError(f"ticks_ago must be in [0, {self.buffer_len})")
        slot = (self.current_tick - 1 - ticks_ago) % self.buffer_len
        return self.history[slot]

    def slice_by_city(self, city_id: int) -> np.ndarray:
        """Observer pattern: return view of agents in the given city. Contiguous slice for .tobytes()."""
        return self.agents[self.agents["city_id"] == city_id]
