from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from app.services.economy.simulation_tick import EconomicSimulationTick
from app.models import SimulationState
from app.extensions import db
from app.services.simulation import SPEED_MAPPING
import logging
import time

logger = logging.getLogger(__name__)

simulation_bp = Blueprint('simulation', __name__)

@simulation_bp.route('/tick', methods=['POST'])
@login_required
def run_simulation_tick():
    """Run a single tick of the economic simulation."""
    if not current_user.gm_profile:
        return jsonify({
            'success': False,
            'message': 'Only GMs can run simulation ticks'
        }), 403

    # Check if simulation is paused
    state = SimulationState.query.filter_by(gm_profile_id=current_user.gm_profile.id).first()
    if state and state.speed == 'pause':
        return jsonify({
            'success': False,
            'message': 'Simulation is paused'
        }), 400

    start_time = time.time()
    
    # Run the simulation tick
    simulator = EconomicSimulationTick(current_user.gm_profile.id)
    success, message = simulator.run_tick()

    duration_ms = (time.time() - start_time) * 1000
    
    if success:
        # Update performance metrics
        if state:
            state.update_performance_metrics(duration_ms)
            db.session.commit()
            
        return jsonify({
            'success': True,
            'message': message,
            'tick': state.current_tick if state else 1,
            'performance': {
                'duration_ms': duration_ms,
                'avg_duration_ms': state.performance_metrics.get('avg_duration_ms', 0) if state else 0
            }
        })
    else:
        # Record error
        if state:
            state.record_error(message)
            db.session.commit()
            
        return jsonify({
            'success': False,
            'message': message,
            'performance': {
                'duration_ms': duration_ms,
                'error_count': state.performance_metrics.get('error_count', 0) if state else 0
            }
        }), 500

@simulation_bp.route('/state', methods=['GET'])
@login_required
def get_simulation_state():
    """Get the current simulation state."""
    if not current_user.gm_profile:
        return jsonify({
            'success': False,
            'message': 'Only GMs can access simulation state'
        }), 403

    state = SimulationState.query.filter_by(gm_profile_id=current_user.gm_profile.id).first()
    
    if not state:
        return jsonify({
            'success': True,
            'state': {
                'tick': 0,
                'speed': 'pause',
                'last_tick': None,
                'performance': {
                    'last_tick_duration_ms': None,
                    'avg_duration_ms': 0,
                    'max_duration_ms': 0,
                    'min_duration_ms': 0,
                    'error_count': 0
                },
                'last_error': None,
                'last_error_time': None
            }
        })

    # Get performance metrics
    performance = state.performance_metrics or {
        'avg_duration_ms': 0,
        'max_duration_ms': 0,
        'min_duration_ms': 0,
        'error_count': 0
    }

    return jsonify({
        'success': True,
        'state': {
            'tick': state.current_tick,
            'speed': state.speed,
            'last_tick': state.last_tick_time.isoformat() if state.last_tick_time else None,
            'performance': {
                'last_tick_duration_ms': state.last_tick_duration_ms,
                'avg_duration_ms': performance.get('avg_duration_ms', 0),
                'max_duration_ms': performance.get('max_duration_ms', 0),
                'min_duration_ms': performance.get('min_duration_ms', 0),
                'error_count': performance.get('error_count', 0)
            },
            'last_error': state.last_error,
            'last_error_time': state.last_error_time.isoformat() if state.last_error_time else None
        }
    })

@simulation_bp.route('/speed', methods=['POST'])
@login_required
def set_simulation_speed():
    """Set the simulation speed (pause, 1x, 5x, etc.)."""
    logger.debug("Received request to set simulation speed")
    logger.debug(f"Current user: {current_user.id}, GM profile: {current_user.gm_profile.id if current_user.gm_profile else None}")
    
    if not current_user.gm_profile:
        logger.warning(f"User {current_user.id} attempted to set speed without GM profile")
        return jsonify({
            'success': False,
            'message': 'Only GMs can set simulation speed'
        }), 403

    speed = request.json.get('speed')
    logger.debug(f"Requested speed: {speed}")
    logger.debug(f"Available speeds: {list(SPEED_MAPPING.keys())}")
    
    if speed not in SPEED_MAPPING.keys():
        logger.error(f"Invalid speed requested: {speed}")
        return jsonify({
            'success': False,
            'message': 'Invalid simulation speed'
        }), 400

    try:
        logger.debug(f"Querying simulation state for GM {current_user.gm_profile.id}")
        state = SimulationState.query.filter_by(gm_profile_id=current_user.gm_profile.id).first()
        if not state:
            logger.debug(f"No existing state found for GM {current_user.gm_profile.id}, creating new state")
            state = SimulationState(gm_profile_id=current_user.gm_profile.id)
            db.session.add(state)
        else:
            logger.debug(f"Found existing state: tick={state.current_tick}, current_speed={state.speed}")

        state.speed = speed
        logger.debug("Attempting to commit speed change")
        db.session.commit()
        logger.debug("Successfully committed speed change")

        return jsonify({
            'success': True,
            'message': f'Simulation speed set to {speed}',
            'speed': speed
        })
    except Exception as e:
        logger.error(f"Error setting simulation speed: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error setting simulation speed: {str(e)}'
        }), 500 