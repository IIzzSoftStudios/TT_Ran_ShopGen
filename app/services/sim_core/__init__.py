# NumPy-based simulation core: fixed-width dtypes, ring buffer, persistence, loop.
from .dtypes import AGENT_DTYPE, PULSE_DTYPE, agent_dtype_nbytes
from .state import SimState
from .persistence import PersistenceAdapter
from .loop import SimulationLoop

__all__ = [
    "AGENT_DTYPE",
    "PULSE_DTYPE",
    "agent_dtype_nbytes",
    "SimState",
    "PersistenceAdapter",
    "SimulationLoop",
]
