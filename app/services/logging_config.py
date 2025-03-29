import logging
import os
from datetime import datetime

# Create logs directory if it doesn't exist
os.makedirs('app/services/logs', exist_ok=True)

# Configure logging
def setup_logging():
    # Create formatters
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Create handlers
    simulation_handler = logging.FileHandler('app/services/logs/simulation.log')
    simulation_handler.setFormatter(formatter)
    
    rollback_handler = logging.FileHandler('app/services/logs/rollback.log')
    rollback_handler.setFormatter(formatter)
    
    # Create loggers
    simulation_logger = logging.getLogger('simulation')
    simulation_logger.setLevel(logging.INFO)
    simulation_logger.addHandler(simulation_handler)
    
    rollback_logger = logging.getLogger('rollback')
    rollback_logger.setLevel(logging.INFO)
    rollback_logger.addHandler(rollback_handler)
    
    return simulation_logger, rollback_logger

# Create loggers
simulation_logger, rollback_logger = setup_logging() 