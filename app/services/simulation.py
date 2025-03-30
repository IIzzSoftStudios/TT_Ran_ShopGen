from datetime import datetime, timedelta
from typing import Dict, Optional, List
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session
from flask import current_app
from app.models import SimulationState, SimulationLog, SimRule, ShopInventory, Item, City, GMProfile, User
from app.extensions import db
from app.services.logging_config import simulation_logger, rollback_logger, event_logger
from threading import Thread, Event
import time
from app.services.economy.simulation_tick import EconomicSimulationTick
import logging
import sys
import threading

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
logger = logging.getLogger(__name__)

# Global instance
simulation_service = None

def init_simulation_service(app):
    """Initialize the simulation service with the Flask app."""
    global simulation_service
    logger.info("Initializing simulation service")
    logger.debug(f"Flask app config: {app.config}")
    
    if simulation_service is None:
        logger.debug("Creating new simulation service instance")
        simulation_service = SimulationService(app)
        # Start the service once during initialization
        simulation_service.start()
    
    service = simulation_service
    
    @app.teardown_appcontext
    def stop_simulation(exception=None):
        # Only stop the service if there's an error
        if exception:
            logger.info("Stopping simulation service due to error")
            logger.error(f"Error during shutdown: {str(exception)}")
            service.stop()
    
    # Add error handlers
    @app.errorhandler(Exception)
    def handle_error(error):
        logger.error(f"Unhandled error in simulation service: {str(error)}", exc_info=True)
        return {"error": str(error)}, 500
    
    logger.info("Simulation service initialization complete")
    return service

# Speed settings mapping (in seconds)
SPEED_MAPPING = {
    "pause": None,
    "1x": 60,      # 1 tick/min
    "5x": 20,      # 20 ticks/min
    "100x": 1,     # 60 ticks/min
    "1000x": 0.01  # Stress test
}

class SimulationService:
    def __init__(self, app):
        self.running = False
        self.thread = None
        self.db = db
        self.logger = simulation_logger
        self.app = app  # Store the Flask app instance
        
        # Speed settings in seconds per tick
        self.speed_settings = {
            'pause': float('inf'),  # Never process ticks
            'slow': 60.0,           # 1 tick per minute
            'normal': 30.0,         # 2 ticks per minute
            'fast': 10.0,           # 6 ticks per minute
            'very_fast': 5.0        # 12 ticks per minute
        }
        
    def start(self):
        """Start the simulation service"""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._run_simulation)
            self.thread.daemon = True
            self.thread.start()
            self.logger.info("Simulation service started")
        else:
            self.logger.debug("Simulation service already running")
            
    def stop(self):
        """Stop the simulation service"""
        if self.running:
            self.running = False
            if self.thread:
                self.thread.join()
            self.logger.info("Simulation service stopped")
        else:
            self.logger.debug("Simulation service already stopped")

    def _run_simulation(self):
        """Main simulation loop"""
        self.logger.info("Starting simulation loop")
        
        while self.running:
            try:
                # Create application context for this iteration
                with self.app.app_context():
                    # Check for active GM sessions
                    if not self._has_active_gm_sessions():
                        self.logger.info("No active GM sessions found, pausing all simulations")
                        running_sims = SimulationState.query.filter_by(status='running').all()
                        for sim in running_sims:
                            sim.status = 'paused'
                            sim.speed = 'pause'
                            self.logger.info(f"Paused simulation for GM {sim.gm_profile_id}")
                        db.session.commit()
                        time.sleep(5)
                        continue
                    
                    # Process active simulations
                    active_sims = SimulationState.query.filter_by(status='running').all()
                    
                    for sim in active_sims:
                        try:
                            # Calculate time since last tick
                            time_since_last = (datetime.utcnow() - sim.last_tick).total_seconds()
                            
                            # Check if we should process a new tick based on speed
                            if sim.speed == 'normal' and time_since_last >= 60:
                                self._process_tick(sim)
                            elif sim.speed == 'fast' and time_since_last >= 30:
                                self._process_tick(sim)
                            elif sim.speed == 'very_fast' and time_since_last >= 15:
                                self._process_tick(sim)
                                
                        except Exception as e:
                            self.logger.error(f"Error processing simulation {sim.id}: {str(e)}")
                            self.record_simulation_error(sim, str(e))
                            continue
                            
                    db.session.commit()
                    
            except Exception as e:
                self.logger.error(f"Error in simulation loop: {str(e)}")
                
            # Sleep briefly to prevent CPU overuse
            time.sleep(1)

    def _has_active_gm_sessions(self):
        """Check if there are any active GM sessions"""
        try:
            with self.app.app_context():
                # Get count of active GM profiles (active in last 5 minutes)
                active_count = GMProfile.query.join(User).filter(
                    User.last_active >= datetime.utcnow() - timedelta(minutes=5)
                ).count()
                return active_count > 0
        except Exception as e:
            self.logger.error(f"Error checking active GM sessions: {str(e)}")
            return False

    def _log_error(self, message: str, gm_profile_id: Optional[int] = None, error_type: str = "error"):
        """Log an error message to both the logger and database"""
        try:
            # Log to file
            if error_type == "error":
                self.logger.error(message)
            elif error_type == "warning":
                self.logger.warning(message)
            else:
                self.logger.info(message)
            
            # Log to database
            with self.app.app_context():
                log = SimulationLog(
                    message=message,
                    level=error_type,
                    gm_profile_id=gm_profile_id,
                    timestamp=datetime.utcnow()
                )
                db.session.add(log)
                db.session.commit()
                
        except Exception as e:
            self.logger.error(f"Failed to log error: {str(e)}")
            # If database logging fails, at least we have the file log
            
    def record_simulation_error(self, sim: SimulationState, error: str):
        """Record an error for a specific simulation"""
        try:
            with self.app.app_context():
                # Update simulation state
                sim.last_error = error
                sim.last_error_time = datetime.utcnow()
                sim.error_count += 1
                
                # Log the error
                self._log_error(
                    message=f"Simulation error for GM {sim.gm_profile_id}: {error}",
                    gm_profile_id=sim.gm_profile_id,
                    error_type="error"
                )
                
                db.session.commit()
                
        except Exception as e:
            self.logger.error(f"Failed to record simulation error: {str(e)}")
            # If we can't record the error, at least log it
            self._log_error(
                message=f"Failed to record error for GM {sim.gm_profile_id}: {error}",
                gm_profile_id=sim.gm_profile_id,
                error_type="error"
            )

    def initialize_simulation(self, gm_profile_id: int) -> SimulationState:
        """Initialize or get existing simulation state for a GM profile"""
        self.logger.info(f"Initializing simulation for GM {gm_profile_id}")
        
        try:
            with self.app.app_context():
                # Check for existing simulation
                sim = SimulationState.query.filter_by(gm_profile_id=gm_profile_id).first()
                
                if sim is None:
                    # Create new simulation state
                    sim = SimulationState(
                        gm_profile_id=gm_profile_id,
                        current_tick=0,
                        last_tick=datetime.utcnow(),
                        speed='pause',
                        status='paused',
                        error_count=0,
                        last_error=None,
                        last_error_time=None
                    )
                    db.session.add(sim)
                    self.logger.info(f"Created new simulation state for GM {gm_profile_id}")
                else:
                    self.logger.info(f"Found existing simulation state for GM {gm_profile_id}")
                    
                db.session.commit()
                return sim
                
        except Exception as e:
            error_msg = f"Error initializing simulation: {str(e)}"
            self.logger.error(error_msg)
            raise SimulationError(error_msg)

    def set_simulation_speed(self, gm_profile_id: int, speed: str) -> SimulationState:
        """Set the simulation speed for a GM profile"""
        self.logger.info(f"Setting simulation speed to {speed} for GM {gm_profile_id}")
        
        # Validate speed setting
        valid_speeds = ['pause', 'normal', 'fast', 'very_fast']
        if speed not in valid_speeds:
            error_msg = f"Invalid speed setting: {speed}. Must be one of: {', '.join(valid_speeds)}"
            self.logger.error(error_msg)
            raise ValueError(error_msg)
            
        try:
            with self.app.app_context():
                # Get or create simulation state
                sim = SimulationState.query.filter_by(gm_profile_id=gm_profile_id).first()
                if sim is None:
                    sim = SimulationState(
                        gm_profile_id=gm_profile_id,
                        current_tick=0,
                        last_tick=datetime.utcnow(),
                        speed=speed,
                        status='paused' if speed == 'pause' else 'running',
                        error_count=0
                    )
                    db.session.add(sim)
                else:
                    # Update existing simulation
                    sim.speed = speed
                    sim.status = 'paused' if speed == 'pause' else 'running'
                    sim.last_tick = datetime.utcnow()
                    
                self.logger.info(f"Updated simulation state for GM {gm_profile_id}: speed={speed}, status={sim.status}")
                db.session.commit()
                return sim
                
        except Exception as e:
            error_msg = f"Error setting simulation speed: {str(e)}"
            self.logger.error(error_msg)
            raise SimulationError(error_msg)

    def get_simulation_status(self, gm_profile_id: int) -> Dict:
        """Get the current status of a simulation for a GM profile"""
        self.logger.info(f"Getting simulation status for GM {gm_profile_id}")
        
        try:
            with self.app.app_context():
                sim = SimulationState.query.filter_by(gm_profile_id=gm_profile_id).first()
                
                if sim is None:
                    # Return default status for non-existent simulation
                    self.logger.info(f"No simulation state found for GM {gm_profile_id}")
                    return {
                        "active": False,
                        "speed": "pause",
                        "status": "paused",
                        "current_tick": 0,
                        "last_tick": datetime.utcnow().isoformat(),
                        "error_count": 0,
                        "last_error": None,
                        "last_error_time": None
                    }
                
                # Return current simulation state
                self.logger.info(f"Found simulation state for GM {gm_profile_id}: tick={sim.current_tick}, speed={sim.speed}, status={sim.status}")
                return {
                    "active": sim.status == "running",
                    "speed": sim.speed,
                    "status": sim.status,
                    "current_tick": sim.current_tick,
                    "last_tick": sim.last_tick.isoformat(),
                    "error_count": sim.error_count,
                    "last_error": sim.last_error,
                    "last_error_time": sim.last_error_time.isoformat() if sim.last_error_time else None
                }
                
        except Exception as e:
            error_msg = f"Error getting simulation status: {str(e)}"
            self.logger.error(error_msg)
            raise SimulationError(error_msg)

    def get_recent_logs(self, gm_profile_id: int, limit: int = 50) -> List[Dict]:
        """Get recent simulation logs for a GM profile"""
        self.logger.debug(f"Getting recent logs for GM {gm_profile_id}")
        try:
            with self.app.app_context():
                logs = SimulationLog.query.filter_by(gm_profile_id=gm_profile_id)\
                    .order_by(SimulationLog.timestamp.desc())\
                    .limit(limit)\
                    .all()
                
                result = [{
                    "timestamp": log.timestamp.isoformat(),
                    "level": log.level,
                    "message": log.message
                } for log in logs]
                
                self.logger.debug(f"Retrieved {len(result)} logs for GM {gm_profile_id}")
                return result
                
        except Exception as e:
            self.logger.error(f"Error getting recent logs: {str(e)}")
            raise

    def manual_tick(self, gm_profile_id: int) -> Dict:
        """Manually trigger a simulation tick."""
        self.logger.info(f"Manual tick requested for GM {gm_profile_id}")
        try:
            with self.app.app_context():
                # Create and run simulation tick
                tick = EconomicSimulationTick(gm_profile_id)
                success, message = tick.run_tick()
                
                if not success:
                    raise Exception(message)
                    
                status = self.get_simulation_status(gm_profile_id)
                self.logger.info(f"Manual tick completed successfully for GM {gm_profile_id}")
                return {
                    "success": True,
                    "message": "Manual tick completed successfully",
                    "status": status
                }
        except Exception as e:
            self.logger.error(f"Error during manual tick for GM {gm_profile_id}: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"Error during manual tick: {str(e)}",
                "status": self.get_simulation_status(gm_profile_id)
            }

    def _process_tick(self, simulation: SimulationState) -> None:
        """Process a single simulation tick"""
        try:
            self.logger.info(f"Processing tick {simulation.current_tick} for GM {simulation.gm_profile_id}")
            
            # Update simulation state
            simulation.last_tick = datetime.utcnow()
            simulation.current_tick += 1
            
            # Process economic updates
            self.economic_service.process_tick(simulation.gm_profile_id, simulation.current_tick)
            
            # Process other simulation updates here
            # ...
            
            self.logger.info(f"Completed tick {simulation.current_tick} for GM {simulation.gm_profile_id}")
            
        except Exception as e:
            error_msg = f"Error processing tick: {str(e)}"
            self.logger.error(error_msg)
            self.record_simulation_error(simulation, error_msg)
            raise 