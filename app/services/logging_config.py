import logging
import os
import sys
from datetime import datetime

# Create logs directory if it doesn't exist
os.makedirs('app/services/logs', exist_ok=True)

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('simulation.log'),
        logging.FileHandler('simulation_debug.log'),
        logging.FileHandler('simulation_error.log')
    ]
)

# Set levels for specific handlers
for handler in logging.getLogger().handlers:
    if isinstance(handler, logging.FileHandler):
        if handler.baseFilename.endswith('simulation_debug.log'):
            handler.setLevel(logging.DEBUG)
        elif handler.baseFilename.endswith('simulation_error.log'):
            handler.setLevel(logging.ERROR)
        else:
            handler.setLevel(logging.INFO)

# Reduce SQLAlchemy logging noise
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy.pool').setLevel(logging.WARNING)

# Create a structured logger for simulation events
class SimulationEventLogger:
    def __init__(self):
        self.logger = logging.getLogger('simulation.events')
        self.logger.setLevel(logging.DEBUG)
        
    def log_tick_start(self, gm_profile_id: int, tick_number: int):
        self.logger.info({
            'event': 'tick_start',
            'gm_profile_id': gm_profile_id,
            'tick_number': tick_number,
            'timestamp': datetime.utcnow().isoformat()
        })
        
    def log_tick_end(self, gm_profile_id: int, tick_number: int, duration_ms: float):
        self.logger.info({
            'event': 'tick_end',
            'gm_profile_id': gm_profile_id,
            'tick_number': tick_number,
            'duration_ms': duration_ms,
            'timestamp': datetime.utcnow().isoformat()
        })
        
    def log_error(self, gm_profile_id: int, error_type: str, message: str, details: dict = None):
        self.logger.error({
            'event': 'error',
            'gm_profile_id': gm_profile_id,
            'error_type': error_type,
            'message': message,
            'details': details or {},
            'timestamp': datetime.utcnow().isoformat()
        })
        
    def log_state_change(self, gm_profile_id: int, old_state: dict, new_state: dict):
        self.logger.info({
            'event': 'state_change',
            'gm_profile_id': gm_profile_id,
            'old_state': old_state,
            'new_state': new_state,
            'timestamp': datetime.utcnow().isoformat()
        })

# Initialize the event logger
event_logger = SimulationEventLogger()

# Configure logging
def setup_logging():
    # Create formatters
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Create handlers
    simulation_handler = logging.FileHandler('app/services/logs/simulation.log')
    simulation_handler.setFormatter(formatter)
    
    rollback_handler = logging.FileHandler('app/services/logs/rollback.log')
    rollback_handler.setFormatter(formatter)
    
    auth_handler = logging.FileHandler('app/services/logs/auth.log')
    auth_handler.setFormatter(formatter)
    
    # Create loggers
    simulation_logger = logging.getLogger('simulation')
    simulation_logger.setLevel(logging.INFO)
    simulation_logger.addHandler(simulation_handler)
    
    rollback_logger = logging.getLogger('rollback')
    rollback_logger.setLevel(logging.INFO)
    rollback_logger.addHandler(rollback_handler)
    
    auth_logger = logging.getLogger('auth')
    auth_logger.setLevel(logging.DEBUG)  # Set to DEBUG for more detailed logging
    auth_logger.addHandler(auth_handler)
    
    return simulation_logger, rollback_logger, auth_logger

# Create loggers
simulation_logger, rollback_logger, auth_logger = setup_logging() 