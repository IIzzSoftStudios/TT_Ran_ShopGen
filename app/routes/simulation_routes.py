from flask import Blueprint, jsonify, request, make_response, current_app
from flask_login import login_required, current_user
from app.models import GMProfile
from app import db
from sqlalchemy.exc import SQLAlchemyError

simulation_bp = Blueprint('simulation', __name__)

def get_simulation_service():
    """Get the simulation service from the current app context."""
    from app.services.simulation import simulation_service
    return simulation_service

# Set Simulation Speed
@simulation_bp.route('/api/simulation/speed', methods=['POST'])
@login_required
def set_simulation_speed():
    if not current_user.gm_profile:
        return jsonify({"error": "User is not a GM"}), 403

    data = request.get_json()
    if not data or 'speed' not in data:
        return jsonify({"error": "Speed parameter is required"}), 400

    speed = data['speed']
    if speed not in ['pause', '1x', '5x', '100x', '1000x']:
        return jsonify({"error": "Invalid speed setting"}), 400

    try:
        db.session.begin_nested()
        state = get_simulation_service().set_simulation_speed(current_user.gm_profile.id, speed)
        db.session.commit()
        return jsonify({
            "current_tick": state.current_tick,
            "speed": state.speed,
            "last_tick_time": state.last_tick_time.isoformat() if state.last_tick_time else None
        })
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "Database error occurred"}), 500
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# Manual Tick
@simulation_bp.route('/api/simulation/tick', methods=['POST'])
@login_required
def manual_tick():
    if not current_user.gm_profile:
        return jsonify({"error": "User is not a GM"}), 403

    try:
        db.session.begin_nested()
        print(f"[DEBUG] Starting manual tick for GM {current_user.gm_profile.id}")
        
        status = get_simulation_service().manual_tick(current_user.gm_profile.id)

        print(f"[DEBUG] manual_tick returned: {status}")
        
        db.session.commit()
        print("[DEBUG] Commit successful")
        return jsonify(status)
    except SQLAlchemyError as e:
        db.session.rollback()
        print(f"[ERROR] SQLAlchemy Error: {e}")
        return jsonify({"error": "Database error occurred"}), 500
    except Exception as e:
        db.session.rollback()
        print(f"[ERROR] Exception: {e}")
        return jsonify({"error": str(e)}), 500

# Get Simulation Status
@simulation_bp.route('/api/simulation/status', methods=['GET'])
@login_required
def get_simulation_status():
    if not current_user.gm_profile:
        return jsonify({"error": "User is not a GM"}), 403

    try:
        status = get_simulation_service().get_simulation_status(current_user.gm_profile.id)
        response = make_response(jsonify(status))
        # Add cache control headers
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except SQLAlchemyError:
        return jsonify({"error": "Database error occurred"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Get Simulation Logs
@simulation_bp.route('/api/simulation/logs', methods=['GET'])
@login_required
def get_simulation_logs():
    if not current_user.gm_profile:
        return jsonify({"error": "User is not a GM"}), 403

    try:
        limit = request.args.get('limit', default=50, type=int)
        logs = get_simulation_service().get_recent_logs(current_user.gm_profile.id, limit)
        return jsonify(logs)
    except SQLAlchemyError:
        return jsonify({"error": "Database error occurred"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
