from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from app.services.economy.simulation_tick import EconomicSimulationTick
from app.models import SimulationState
from app.extensions import db

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

    # Run the simulation tick
    simulator = EconomicSimulationTick(current_user.gm_profile.id)
    success, message = simulator.run_tick()

    if success:
        return jsonify({
            'success': True,
            'message': message,
            'tick': state.current_tick if state else 1
        })
    else:
        return jsonify({
            'success': False,
            'message': message
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
                'last_tick': None
            }
        })

    return jsonify({
        'success': True,
        'state': {
            'tick': state.current_tick,
            'speed': state.speed,
            'last_tick': state.last_tick_time.isoformat() if state.last_tick_time else None
        }
    })

@simulation_bp.route('/speed', methods=['POST'])
@login_required
def set_simulation_speed():
    """Set the simulation speed (pause, 1x, 5x, etc.)."""
    if not current_user.gm_profile:
        return jsonify({
            'success': False,
            'message': 'Only GMs can set simulation speed'
        }), 403

    speed = request.json.get('speed')
    if speed not in ['pause', '1x', '5x', '10x', '100x']:
        return jsonify({
            'success': False,
            'message': 'Invalid simulation speed'
        }), 400

    state = SimulationState.query.filter_by(gm_profile_id=current_user.gm_profile.id).first()
    if not state:
        state = SimulationState(gm_profile_id=current_user.gm_profile.id)
        db.session.add(state)

    state.speed = speed
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Simulation speed set to {speed}',
        'speed': speed
    }) 