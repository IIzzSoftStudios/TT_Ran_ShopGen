"""
300k-agent benchmark: validate RAM usage and tick performance.
Run from project root: python -m scripts.benchmark_sim
"""
import os
import sys
import time

# Add project root so app and sim_core are importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def get_mem_mb():
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # Linux: KB -> MB
    except ImportError:
        try:
            import psutil
            return psutil.Process().memory_info().rss / (1024 * 1024)
        except ImportError:
            return 0


def main():
    num_agents = 300_000
    ring_ticks = 60
    num_ticks = 20  # run 20 ticks to get stable timing

    from app.services.sim_core import SimState, PersistenceAdapter, SimulationLoop
    from app.services.sim_core.dtypes import agent_dtype_nbytes

    print("=== NumPy sim 300k-agent benchmark ===\n")
    print(f"Agents: {num_agents:,}, ring buffer: {ring_ticks} ticks")
    print(f"Bytes per agent: {agent_dtype_nbytes()}")
    print(f"Base state (agents only): {num_agents * agent_dtype_nbytes() / (1024*1024):.2f} MB")
    print(f"Ring buffer (60 x 300k): {ring_ticks * num_agents * agent_dtype_nbytes() / (1024*1024):.2f} MB\n")

    # State only (no persistence) to measure core memory
    state = SimState(num_agents=num_agents, ring_buffer_ticks=ring_ticks)
    # Seed
    import numpy as np
    rng = np.random.default_rng(42)
    state.agents["agent_id"] = np.arange(num_agents, dtype=np.uint32)
    state.agents["city_id"] = np.uint16(np.arange(num_agents) % 1000)
    state.agents["gold"] = np.float32(100.0 + rng.random(num_agents) * 50)
    state.agents["inventory_count"] = np.uint16(rng.integers(0, 100, num_agents))
    state.agents["base_price"] = np.float32(10.0 + rng.random(num_agents) * 40)
    state.agents["strategy_flags"] = np.uint8(rng.integers(0, 4, num_agents))
    state.agents["last_transaction_vol"] = np.float32(0.01)

    mem_after_state = get_mem_mb()
    print(f"RSS after SimState + seed (approx): {mem_after_state:.1f} MB\n")

    # No-op persistence so we don't start DB or cold process
    class NoOpPersistence:
        def push_warm(self, pulse): pass
        def stage_tick(self, agents): pass
        def shutdown(self): pass

    loop = SimulationLoop(state=state, persistence=NoOpPersistence(), tick_interval_sec=0)

    start = time.perf_counter()
    for i in range(num_ticks):
        loop.run_one_tick()
    elapsed = time.perf_counter() - start
    per_tick_ms = (elapsed / num_ticks) * 1000
    print(f"Ran {num_ticks} ticks in {elapsed:.2f} s")
    print(f"Per-tick: {per_tick_ms:.2f} ms")
    print(f"Headroom for 1000 ms budget: {1000 - per_tick_ms:.0f} ms\n")

    if per_tick_ms < 1000:
        print("PASS: Tick duration within 1s budget.")
    else:
        print("WARN: Tick exceeds 1s; consider Numba for logic or reducing work.")

    mem_final = get_mem_mb()
    print(f"RSS after {num_ticks} ticks: {mem_final:.1f} MB")
    print("\nDone.")


if __name__ == "__main__":
    main()
