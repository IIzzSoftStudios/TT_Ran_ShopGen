"""
Three-tier persistence: Hot (in-memory, SimState), Warm (PostgreSQL via callback), Cold (blob via subprocess).
Cold uses Producer-Consumer with multiprocessing.Queue and a separate Process to avoid GIL during compression.
"""
import os
import time
import queue
import threading
import multiprocessing as mp
from typing import Callable, Optional, Any

import numpy as np
from .dtypes import AGENT_DTYPE, DTYPE_VERSION


def _cold_worker_process(
    q: "mp.Queue",
    blob_dir: str,
    sim_id: str,
) -> None:
    """
    Runs in a separate process: consume buffers from the queue, compress, write to blob_dir.
    Compressing ~30 MB with zstd can take 50–100 ms; doing this in the main process would stutter.
    """
    try:
        import zstandard as zstd
        has_zstd = True
    except ImportError:
        has_zstd = False

    while True:
        try:
            msg = q.get(timeout=1.0)
            if msg is None:
                break
            tick_start, tick_end, buffer = msg
            # buffer: (batch_size, num_agents) dtype=AGENT_DTYPE
            os.makedirs(blob_dir, exist_ok=True)
            path = os.path.join(blob_dir, f"{sim_id}_t{tick_start}-{tick_end}.npz")
            np.savez_compressed(path, data=buffer, version=DTYPE_VERSION, tick_start=tick_start, tick_end=tick_end)
        except queue.Empty:
            continue
        except Exception as e:
            print(f"[Cold worker] error: {e}")


class PersistenceAdapter:
    """
    Hot: caller uses SimState (ring buffer) directly.
    Warm: push pulse dict to a queue; background thread calls warm_callback (e.g. raw SQL insert).
    Cold: fill 3D buffer (batch_size, num_agents); when full, put copy into multiprocessing.Queue;
          a separate Process compresses and writes to blob_dir.
    """

    __slots__ = (
        "batch_size", "num_agents", "cold_buffer", "cold_idx", "cold_queue",
        "cold_process", "blob_dir", "sim_id", "warm_queue", "warm_thread", "warm_callback", "running"
    )

    def __init__(
        self,
        num_agents: int,
        batch_size: int = 100,
        blob_dir: str = "data/sim_blobs",
        sim_id: str = "default",
        warm_callback: Optional[Callable[[dict], None]] = None,
    ):
        self.num_agents = num_agents
        self.batch_size = batch_size
        self.blob_dir = blob_dir
        self.sim_id = sim_id
        self.warm_callback = warm_callback

        # Cold: 3D buffer (batch_size, num_agents)
        self.cold_buffer = np.zeros((batch_size, num_agents), dtype=AGENT_DTYPE)
        self.cold_idx = 0
        self.cold_queue = mp.Queue(maxsize=4)
        self.cold_process = mp.Process(
            target=_cold_worker_process,
            args=(self.cold_queue, blob_dir, sim_id),
            daemon=True,
        )
        self.cold_process.start()

        # Warm: queue + background thread
        self.warm_queue = queue.Queue()
        self.running = True
        self.warm_thread = threading.Thread(target=self._warm_loop, daemon=True)
        self.warm_thread.start()

    def _warm_loop(self) -> None:
        while self.running:
            try:
                pulse = self.warm_queue.get(timeout=0.5)
                if pulse is None:
                    break
                if self.warm_callback:
                    try:
                        self.warm_callback(pulse)
                    except Exception as e:
                        print(f"[Warm] callback error: {e}")
            except queue.Empty:
                continue

    def stage_tick(self, agent_data: np.ndarray) -> None:
        """
        Copy current tick into cold buffer. When full, put a copy into the Queue and reset.
        Never block the sim loop; compression runs in the cold process.
        """
        self.cold_buffer[self.cold_idx] = agent_data
        self.cold_idx += 1
        if self.cold_idx >= self.batch_size:
            self.flush_cold()

    def flush_cold(self) -> None:
        """Push current cold buffer to the subprocess (non-blocking put with copy)."""
        if self.cold_idx == 0:
            return
        tick_end = self.cold_idx  # relative to current run
        data_to_send = self.cold_buffer[: self.cold_idx].copy()
        tick_start = 0
        try:
            self.cold_queue.put_nowait((tick_start, tick_end, data_to_send))
        except queue.Full:
            pass  # drop or could block; plan says non-blocking
        self.cold_idx = 0

    def push_warm(self, pulse: dict) -> None:
        """Fire-and-forget: enqueue pulse for background thread to write to PostgreSQL."""
        try:
            self.warm_queue.put_nowait(pulse)
        except queue.Full:
            pass

    def shutdown(self) -> None:
        self.running = False
        self.warm_queue.put(None)
        self.cold_queue.put(None)
        self.flush_cold()
        if self.cold_process.is_alive():
            self.cold_process.join(timeout=5.0)
