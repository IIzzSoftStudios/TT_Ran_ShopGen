from dataclasses import dataclass
from typing import Optional

@dataclass
class SimulationConfig:
    """Configuration settings for the simulation engine."""
    # Base tick interval in seconds (for future scheduling)
    tick_interval: int = 60  # 1 hour default
    
    # Price fluctuation settings
    min_price_change_percent: float = -20.0
    max_price_change_percent: float = 20.0
    
    # Logging settings
    enable_tick_logging: bool = True
    log_file_path: str = "logs/simulation.log"
    
    # Future expansion settings
    enable_demand_simulation: bool = False
    enable_supply_simulation: bool = False
    enable_event_simulation: bool = False

# Default configuration instance
default_config = SimulationConfig() 