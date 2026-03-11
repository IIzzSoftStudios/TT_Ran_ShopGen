"""
Fixed-width NumPy dtypes for the simulation. Single source of truth for binary slicing.
Avoid np.object_ at all costs — it breaks contiguous memory layout.
"""
import numpy as np

# 17 bytes per agent (plan). Optional last_transaction_vol for volume aggregation.
AGENT_DTYPE = np.dtype([
    ("agent_id", np.uint32),       # 4-byte unsigned (u4)
    ("city_id", np.uint16),        # 2-byte unsigned (u2), up to 65k cities
    ("gold", np.float32),          # 4-byte float (f4)
    ("inventory_count", np.uint16),
    ("base_price", np.float32),
    ("strategy_flags", np.uint8),  # 1-byte bitmask for AI behavior
    ("last_transaction_vol", np.float32),  # for volume aggregation in pulse
])
# 4+2+4+2+4+1+4 = 21 bytes per agent

PULSE_DTYPE = np.dtype([
    ("tick", np.uint32),
    ("mean_price", np.float32),
    ("median_gold", np.float32),
    ("volume", np.float32),
    ("std_price", np.float32),
])
# For warm storage and Market Pulse broadcast

# Schema version for blob replay
DTYPE_VERSION = 1


def agent_dtype_nbytes() -> int:
    """Bytes per agent row."""
    return int(AGENT_DTYPE.itemsize)
