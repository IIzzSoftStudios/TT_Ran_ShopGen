from datetime import datetime
from typing import Dict, Optional, List
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session
from flask import current_app
from app.models import SimulationState, SimulationLog, SimRule, ShopInventory, Item, City
from app.extensions import db
from app.services.logging_config import simulation_logger, rollback_logger

# Global instance
simulation_service = None

def init_simulation_service(app):
    """Initialize the simulation service with the Flask app."""
    global simulation_service
    if simulation_service is None:
        simulation_service = SimulationService(app)
    return simulation_service

# Speed settings mapping (in seconds)
SPEED_MAPPING = {
    "pause": None,
    "1x": 60,      # 1 tick/min
    "5x": 20,      # 20 ticks/min
    "100x": 1,     # 60 ticks/min
    "1000x": 0.01  # Stress test
}

class SimulationService:
    def __init__(self, app=None):
        self.app = app  # Store the Flask app instance
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        self._active_jobs: Dict[int, str] = {}  # gm_profile_id -> job_id
        simulation_logger.info("SimulationService initialized")
        simulation_logger.info(f"Active scheduler jobs: {self._active_jobs}")
        
        if app:
            with app.app_context():
                self._restore_active_simulations()

    def _restore_active_simulations(self):
        """Restore active simulation jobs on service startup."""
        simulation_logger.info("Restoring active simulations...")
        try:
            active_states = db.session.query(SimulationState).filter(SimulationState.speed != "pause").all()
            
            for state in active_states:
                simulation_logger.info(f"Found active simulation for GM {state.gm_profile_id} with speed {state.speed}")
                self._update_scheduler(state.gm_profile_id)
        except Exception as e:
            simulation_logger.error(f"Error restoring active simulations: {str(e)}")

    def initialize_simulation(self, gm_profile_id: int) -> SimulationState:
        """Initialize simulation state for a GM profile if it doesn't exist."""
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
            simulation_logger.info(f"Initialized new simulation state for GM {gm_profile_id}")
        else:
            simulation_logger.info(f"Found existing simulation state for GM {gm_profile_id}: tick={state.current_tick}, speed={state.speed}")
        return state

    def set_simulation_speed(self, gm_profile_id: int, speed: str) -> SimulationState:
        """Set the simulation speed for a GM profile."""
        if speed not in SPEED_MAPPING:
            raise ValueError(f"Invalid speed setting: {speed}")

        state = self.initialize_simulation(gm_profile_id)
        old_speed = state.speed
        state.speed = speed
        db.session.commit()
        simulation_logger.info(f"Changed simulation speed for GM {gm_profile_id} from {old_speed} to {speed}")

        # Update scheduler
        if old_speed != speed:
            self._update_scheduler(gm_profile_id)

        return state

    def _update_scheduler(self, gm_profile_id: int):
        """Update the scheduler for a GM profile."""
        simulation_logger.info(f"Updating scheduler for GM {gm_profile_id}")
        simulation_logger.info(f"Current active jobs: {self._active_jobs}")
        
        # Remove existing job if any
        if gm_profile_id in self._active_jobs:
            job_id = self._active_jobs[gm_profile_id]
            try:
                self.scheduler.remove_job(job_id)
                del self._active_jobs[gm_profile_id]
                simulation_logger.info(f"Removed existing scheduler job {job_id} for GM {gm_profile_id}")
            except Exception as e:
                simulation_logger.error(f"Error removing job {job_id}: {str(e)}")

        # Add new job if not paused
        state = db.session.query(SimulationState).filter_by(gm_profile_id=gm_profile_id).first()
        if state and state.speed != "pause":
            interval = SPEED_MAPPING[state.speed]
            try:
                job = self.scheduler.add_job(
                    self._run_tick,
                    IntervalTrigger(seconds=interval),
                    args=[gm_profile_id],
                    id=f"sim_tick_{gm_profile_id}"
                )
                self._active_jobs[gm_profile_id] = job.id
                simulation_logger.info(f"Added new scheduler job {job.id} for GM {gm_profile_id} with interval {interval}s")
                simulation_logger.info(f"Updated active jobs: {self._active_jobs}")
            except Exception as e:
                simulation_logger.error(f"Error adding job for GM {gm_profile_id}: {str(e)}")
                # If job creation fails, pause the simulation
                state.speed = "pause"
                db.session.commit()

    def _run_tick(self, gm_profile_id: int):
        """Run a single simulation tick."""
        simulation_logger.info(f"[TICK START] Scheduler triggered tick for GM {gm_profile_id}")

        # Use the stored app instance for the context
        with self.app.app_context():
            try:
                state = db.session.query(SimulationState).filter_by(gm_profile_id=gm_profile_id).first()
                if not state:
                    simulation_logger.warning(f"[TICK SKIPPED] No simulation state found for GM {gm_profile_id}")
                    return

                simulation_logger.debug(f"[STATE CHECK] GM {gm_profile_id} current state: tick={state.current_tick}, speed={state.speed}")

                if state.speed == "pause":
                    simulation_logger.info(f"[TICK SKIPPED] Simulation paused for GM {gm_profile_id}")
                    return

                # Update tick counter and timestamp
                old_tick = state.current_tick
                state.current_tick += 1
                state.last_tick_time = datetime.utcnow()
                simulation_logger.debug(f"[TICK UPDATE] GM {gm_profile_id} incremented tick from {old_tick} to {state.current_tick}")

                # Apply simulation rules
                simulation_logger.info(f"[APPLY RULES] Executing rules for GM {gm_profile_id}, tick={state.current_tick}")
                self._apply_rules(gm_profile_id)

                # Log the tick
                simulation_logger.debug(f"[LOG TICK] Logging tick for GM {gm_profile_id}, tick={state.current_tick}")
                self._log_tick(gm_profile_id, state.current_tick)

                # Commit the changes
                db.session.commit()
                simulation_logger.info(f"[TICK COMMIT] Successfully ran tick {state.current_tick} for GM {gm_profile_id} (previous: {old_tick})")

            except Exception as e:
                db.session.rollback()
                rollback_logger.error(f"[TICK ERROR] Rollback during tick {state.current_tick if 'state' in locals() and state else 'UNKNOWN'} for GM {gm_profile_id}: {str(e)}")
                self._log_error(gm_profile_id, state.current_tick if 'state' in locals() and state else 0, str(e))
                self.set_simulation_speed(gm_profile_id, "pause")
                raise

    def _apply_rules(self, gm_profile_id: int):
        """Apply all active simulation rules."""
        rules = db.session.query(SimRule).filter_by(gm_profile_id=gm_profile_id).all()
        simulation_logger.info(f"Applying {len(rules)} rules for GM {gm_profile_id}")
        for rule in rules:
            self._apply_rule(rule)

    def _apply_rule(self, rule: SimRule):
        """Apply a single simulation rule."""
        # TODO: Implement rule application logic based on rule_type and function_type
        pass

    def _log_tick(self, gm_profile_id: int, tick_id: int):
        """Log a simulation tick."""
        log = SimulationLog(
            tick_id=tick_id,
            event_type="tick",
            details={"status": "success"},
            gm_profile_id=gm_profile_id
        )
        db.session.add(log)
        db.session.commit()

    def _log_error(self, gm_profile_id: int, tick_id: int, error_message: str):
        """Log a simulation error."""
        log = SimulationLog(
            tick_id=tick_id,
            event_type="error",
            details={"error": error_message},
            gm_profile_id=gm_profile_id
        )
        db.session.add(log)
        db.session.commit()
        simulation_logger.error(f"Error during tick {tick_id} for GM {gm_profile_id}: {error_message}")

    def get_simulation_status(self, gm_profile_id: int) -> Dict:
        """Get the current simulation status for a GM profile."""
        simulation_logger.info(f"Fetching simulation status for GM {gm_profile_id}")
        state = db.session.query(SimulationState).filter_by(gm_profile_id=gm_profile_id).first()
        if not state:
            simulation_logger.info(f"No simulation state found for GM {gm_profile_id}")
            return {"status": "not_initialized"}

        status = {
            "current_tick": state.current_tick,
            "speed": state.speed,
            "last_tick_time": state.last_tick_time.isoformat(),
            "status": "running" if state.speed != "pause" else "paused"
        }
        simulation_logger.info(f"Returning status for GM {gm_profile_id}: {status}")
        return status

    def get_recent_logs(self, gm_profile_id: int, limit: int = 50) -> List[Dict]:
        """Get recent simulation logs for a GM profile."""
        logs = db.session.query(SimulationLog)\
            .filter_by(gm_profile_id=gm_profile_id)\
            .order_by(SimulationLog.timestamp.desc())\
            .limit(limit)\
            .all()

        return [{
            "tick_id": log.tick_id,
            "timestamp": log.timestamp.isoformat(),
            "event_type": log.event_type,
            "details": log.details
        } for log in logs]

    def manual_tick(self, gm_profile_id: int) -> Dict:
        """Manually advance the simulation by one tick."""
        simulation_logger.info(f"Manual tick requested for GM {gm_profile_id}")
        state = db.session.query(SimulationState).filter_by(gm_profile_id=gm_profile_id).first()
        if not state:
            raise ValueError("Simulation not initialized")

        # Store current speed
        current_speed = state.speed
        
        try:
            # Temporarily pause simulation
            if current_speed != "pause":
                simulation_logger.info(f"Temporarily pausing simulation for GM {gm_profile_id} (current speed: {current_speed})")
                self.set_simulation_speed(gm_profile_id, "pause")

            # Update tick counter and timestamp
            old_tick = state.current_tick
            state.current_tick += 1
            state.last_tick_time = datetime.utcnow()
            
            # Apply simulation rules
            self._apply_rules(gm_profile_id)
            
            # Log the tick
            self._log_tick(gm_profile_id, state.current_tick)
            
            # Commit the changes
            db.session.commit()
            simulation_logger.info(f"Successfully ran manual tick {state.current_tick} for GM {gm_profile_id} (previous: {old_tick})")

            # Restore previous speed
            if current_speed != "pause":
                simulation_logger.info(f"Restoring previous speed {current_speed} for GM {gm_profile_id}")
                self.set_simulation_speed(gm_profile_id, current_speed)

            return self.get_simulation_status(gm_profile_id)
        except Exception as e:
            db.session.rollback()
            rollback_logger.error(f"Rollback during manual tick {state.current_tick} for GM {gm_profile_id}: {str(e)}")
            self._log_error(gm_profile_id, state.current_tick, str(e))
            raise 