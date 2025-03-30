from datetime import datetime
from typing import Dict, Optional, List
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session
from flask import current_app
from app.models import SimulationState, SimulationLog, SimRule, ShopInventory, Item, City
from app.extensions import db
from app.services.logging_config import simulation_logger, rollback_logger
from threading import Thread, Event
import time
from app.services.economy.simulation_tick import EconomicSimulationTick
import logging
import sys

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('simulation.log')
    ]
)
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
    service = simulation_service
    
    # Use with_appcontext instead of before_first_request
    @app.before_request
    def start_simulation():
        logger.debug("Checking if simulation needs to be started")
        if not service.running:
            logger.info("Starting simulation service")
            service.start()
    
    @app.teardown_appcontext
    def stop_simulation(exception=None):
        logger.info("Stopping simulation service")
        if exception:
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
        """Initialize the simulation service with the Flask app."""
        logger.info("Initializing SimulationService")
        logger.debug(f"App context: {app.app_context()}")
        self.app = app
        self.running = False
        self.thread = None
        self.tick_interval = 60  # seconds between ticks
        self.current_tick = 0
        self.last_tick_time = datetime.utcnow()
        self._initialization_errors = []
        
        try:
            # Load simulation state within app context
            with app.app_context():
                self._load_simulation_state()
            logger.info(f"SimulationService initialized with tick {self.current_tick}")
        except Exception as e:
            logger.error(f"Error during SimulationService initialization: {str(e)}", exc_info=True)
            self._initialization_errors.append(str(e))
            raise

    def _load_simulation_state(self):
        """Load simulation state from database."""
        logger.debug("Loading simulation state from database")
        try:
            state = SimulationState.query.first()
            if state:
                self.current_tick = state.current_tick
                self.last_tick_time = state.last_tick_time
                logger.info(f"Loaded existing simulation state: tick={self.current_tick}, last_tick={self.last_tick_time}")
                logger.debug(f"State details: speed={state.speed}, gm_profile_id={state.gm_profile_id}")
            else:
                logger.info("No existing simulation state found, using defaults")
                self.current_tick = 0
                self.last_tick_time = datetime.utcnow()
                logger.debug("Created default simulation state")
        except Exception as e:
            logger.error(f"Error loading simulation state: {str(e)}", exc_info=True)
            raise

    def start(self):
        """Start the simulation service."""
        logger.info("Starting simulation service")
        if not self.running:
            try:
                self.running = True
                self.thread = Thread(target=self._run_simulation)
                self.thread.daemon = True
                self.thread.start()
                logger.info("Simulation thread started")
                logger.debug(f"Thread ID: {self.thread.ident}, Name: {self.thread.name}")
            except Exception as e:
                logger.error(f"Error starting simulation thread: {str(e)}", exc_info=True)
                self.running = False
                raise
        else:
            logger.warning("Simulation service already running")

    def stop(self):
        """Stop the simulation service."""
        logger.info("Stopping simulation service")
        if self.running:
            self.running = False
            if self.thread:
                try:
                    self.thread.join(timeout=5)  # Wait up to 5 seconds for thread to finish
                    logger.info("Simulation thread stopped")
                except Exception as e:
                    logger.error(f"Error stopping simulation thread: {str(e)}", exc_info=True)
            else:
                logger.warning("No simulation thread to stop")
        else:
            logger.debug("Simulation service already stopped")

    def _run_simulation(self):
        """Main simulation loop."""
        logger.info("Starting simulation loop")
        while self.running:
            try:
                self.run_tick()
                logger.debug(f"Completed tick {self.current_tick}, sleeping for {self.tick_interval} seconds")
                time.sleep(self.tick_interval)
            except Exception as e:
                logger.error(f"Error in simulation loop: {str(e)}", exc_info=True)
                time.sleep(1)  # Wait before retrying

    def run_tick(self):
        """Run a single simulation tick."""
        logger.info(f"Starting tick {self.current_tick}")
        with self.app.app_context():
            try:
                # Get all GM profiles
                gm_profiles = db.session.query(SimulationState.gm_profile_id).distinct().all()
                logger.debug(f"Found {len(gm_profiles)} GM profiles to process")
                
                for gm_profile_row in gm_profiles:
                    gm_profile_id = gm_profile_row[0]  # Extract the ID from the Row object
                    logger.debug(f"Processing GM profile {gm_profile_id}")
                    try:
                        # Create and run simulation tick for each GM profile
                        tick = EconomicSimulationTick(gm_profile_id)
                        success, message = tick.run_tick()
                        
                        if not success:
                            logger.error(f"Error in tick {self.current_tick} for GM {gm_profile_id}: {message}")
                            self._log_error(f"Error in tick {self.current_tick}: {message}", gm_profile_id)
                        else:
                            logger.debug(f"Successfully processed tick for GM {gm_profile_id}")
                    except Exception as e:
                        logger.error(f"Error processing GM {gm_profile_id}: {str(e)}", exc_info=True)
                        self._log_error(f"Error processing GM {gm_profile_id}: {str(e)}", gm_profile_id)
                        continue  # Continue with next GM profile even if one fails
                
                self.current_tick += 1
                self.last_tick_time = datetime.utcnow()
                logger.info(f"Completed tick {self.current_tick}")
                
                # Update simulation state
                try:
                    state = SimulationState.query.first()
                    if state:
                        state.current_tick = self.current_tick
                        state.last_tick_time = self.last_tick_time
                        logger.debug(f"Updated existing simulation state: tick={self.current_tick}")
                    else:
                        state = SimulationState(
                            current_tick=self.current_tick,
                            last_tick_time=self.last_tick_time
                        )
                        db.session.add(state)
                        logger.debug("Created new simulation state")
                    
                    db.session.commit()
                    logger.debug("Committed simulation state changes")
                except Exception as e:
                    logger.error(f"Error updating simulation state: {str(e)}", exc_info=True)
                    db.session.rollback()
                    self._log_error(f"Error updating simulation state: {str(e)}", gm_profile_id)
                    raise
                
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error in simulation tick: {str(e)}", exc_info=True)
                self._log_error(f"Error in simulation tick: {str(e)}", gm_profile_id)
                raise

    def _log_error(self, message, gm_profile_id=None):
        """Log an error message."""
        logger.error(f"Logging error: {message}")
        try:
            # Rollback any existing transaction
            db.session.rollback()
            
            log = SimulationLog(
                tick_id=self.current_tick,
                event_type="error",
                details={"message": message},
                gm_profile_id=gm_profile_id
            )
            db.session.add(log)
            db.session.commit()
            logger.debug("Successfully logged error")
        except Exception as e:
            logger.error(f"Error logging error message: {str(e)}", exc_info=True)
            db.session.rollback()

    def initialize_simulation(self, gm_profile_id: int) -> SimulationState:
        """Initialize simulation state for a GM profile if it doesn't exist."""
        logger.info(f"Initializing simulation for GM {gm_profile_id}")
        try:
            state = db.session.query(SimulationState).filter_by(gm_profile_id=gm_profile_id).first()
            if not state:
                state = SimulationState(
                    current_tick=0,
                    speed="pause",
                    last_tick_time=datetime.utcnow(),
                    gm_profile_id=gm_profile_id
                )
                db.session.add(state)
                db.session.commit()
                logger.info(f"Initialized new simulation state for GM {gm_profile_id}")
            else:
                logger.info(f"Found existing simulation state for GM {gm_profile_id}: tick={state.current_tick}, speed={state.speed}")
            return state
        except Exception as e:
            logger.error(f"Error initializing simulation for GM {gm_profile_id}: {str(e)}", exc_info=True)
            raise

    def set_simulation_speed(self, gm_profile_id: int, speed: str) -> SimulationState:
        """Set the simulation speed for a GM profile."""
        logger.info(f"Setting simulation speed for GM {gm_profile_id} to {speed}")
        if speed not in SPEED_MAPPING:
            logger.error(f"Invalid speed setting: {speed}")
            raise ValueError(f"Invalid speed setting: {speed}")

        try:
            state = self.initialize_simulation(gm_profile_id)
            old_speed = state.speed
            state.speed = speed
            db.session.commit()
            logger.info(f"Changed simulation speed for GM {gm_profile_id} from {old_speed} to {speed}")
            return state
        except Exception as e:
            logger.error(f"Error setting simulation speed: {str(e)}", exc_info=True)
            raise

    def get_simulation_status(self, gm_profile_id: int) -> Dict:
        """Get the current simulation status for a GM profile."""
        logger.debug(f"Getting simulation status for GM {gm_profile_id}")
        try:
            state = db.session.query(SimulationState).filter_by(gm_profile_id=gm_profile_id).first()
            if not state:
                logger.warning(f"No simulation state found for GM {gm_profile_id}")
                return {
                    "active": False,
                    "tick": 0,
                    "speed": "pause",
                    "last_tick": None
                }
            
            status = {
                "active": state.speed != "pause",
                "tick": state.current_tick,
                "speed": state.speed,
                "last_tick": state.last_tick_time.isoformat() if state.last_tick_time else None
            }
            logger.debug(f"Simulation status for GM {gm_profile_id}: {status}")
            return status
        except Exception as e:
            logger.error(f"Error getting simulation status: {str(e)}", exc_info=True)
            raise

    def get_recent_logs(self, gm_profile_id: int, limit: int = 50) -> List[Dict]:
        """Get recent simulation logs for a GM profile."""
        logger.debug(f"Getting recent logs for GM {gm_profile_id}")
        try:
            logs = db.session.query(SimulationLog).filter_by(gm_profile_id=gm_profile_id)\
                .order_by(SimulationLog.timestamp.desc())\
                .limit(limit)\
                .all()
            
            result = [{
                "tick_id": log.tick_id,
                "event_type": log.event_type,
                "details": log.details,
                "timestamp": log.timestamp.isoformat()
            } for log in logs]
            
            logger.debug(f"Retrieved {len(result)} logs for GM {gm_profile_id}")
            return result
        except Exception as e:
            logger.error(f"Error getting recent logs: {str(e)}", exc_info=True)
            raise

    def manual_tick(self, gm_profile_id: int) -> Dict:
        """Manually trigger a simulation tick."""
        logger.info(f"Manual tick requested for GM {gm_profile_id}")
        try:
            self.run_tick()
            status = self.get_simulation_status(gm_profile_id)
            logger.info(f"Manual tick completed successfully for GM {gm_profile_id}")
            return {
                "success": True,
                "message": "Manual tick completed successfully",
                "status": status
            }
        except Exception as e:
            logger.error(f"Error during manual tick for GM {gm_profile_id}: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"Error during manual tick: {str(e)}",
                "status": self.get_simulation_status(gm_profile_id)
            } 