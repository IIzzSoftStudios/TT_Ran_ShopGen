from flask import Blueprint, jsonify, request, make_response
from flask_login import login_required, current_user
from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError
from sqlalchemy.exc import SQLAlchemyError

from app.constants.simulation_flags import ALLOWED_SIMULATION_SPEEDS
from app.extensions import db
from app.models import SimulationLog, SimulationState
from app.services.distributed_lock import acquire_simulation_lock
from app.services.simulation import SimulationEngine
from app.services.simulation_state_helpers import get_simulation_state_for_gm

simulation_bp = Blueprint("simulation", __name__)


def _gm_profile_or_403():
    if not current_user.gm_profile:
        return None, (jsonify({"error": "User is not a GM"}), 403)
    return current_user.gm_profile, None


@simulation_bp.route("/api/simulation/speed", methods=["POST"])
@login_required
def set_simulation_speed():
    gm_profile, err = _gm_profile_or_403()
    if err:
        return err

    data = request.get_json()
    if not data or "speed" not in data:
        return jsonify({"error": "Speed parameter is required"}), 400

    speed = data["speed"]
    if speed not in ALLOWED_SIMULATION_SPEEDS:
        return jsonify({"error": "Invalid speed setting"}), 400

    try:
        state = get_simulation_state_for_gm(db.session, gm_profile.id)
        if not state:
            from datetime import datetime

            state = SimulationState(
                current_tick=0,
                speed=speed,
                last_tick_time=datetime.utcnow(),
                gm_profile_id=gm_profile.id,
            )
            db.session.add(state)
        else:
            state.speed = speed
        db.session.commit()
        return jsonify(
            {
                "current_tick": state.current_tick,
                "speed": state.speed,
                "last_tick_time": state.last_tick_time.isoformat() if state.last_tick_time else None,
                "current_game_day": gm_profile.current_game_day,
            }
        )
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "Database error occurred"}), 500
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@simulation_bp.route("/api/simulation/tick", methods=["POST"])
@login_required
def manual_tick():
    gm_profile, err = _gm_profile_or_403()
    if err:
        return err

    try:
        try:
            lock = acquire_simulation_lock(gm_profile.id, ttl_seconds=10, blocking=False)
        except (RedisConnectionError, RedisTimeoutError):
            return (
                jsonify(
                    {
                        "error": "Simulation service is currently offline. Please try again later.",
                        "status": "offline",
                    }
                ),
                503,
            )

        if lock is None:
            return jsonify({"error": "Simulation already running", "status": "busy"}), 409

        try:
            engine = SimulationEngine()
            stats = engine.run_tick(gm_profile.id, commit=True)
            state = get_simulation_state_for_gm(db.session, gm_profile.id)
            status_payload = {
                "active": bool(state and state.speed != "pause"),
                "tick": state.current_tick if state else 0,
                "speed": state.speed if state else "pause",
                "last_tick": state.last_tick_time.isoformat() if state and state.last_tick_time else None,
                "current_game_day": stats.get("current_game_day"),
            }
            return jsonify(
                {
                    "success": True,
                    "message": (
                        f"Simulation tick completed: Updated {stats['shops_updated']} shops "
                        f"and {stats['items_updated']} items."
                    ),
                    "stats": stats,
                    "status": status_payload,
                }
            )
        finally:
            lock.release()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "Database error occurred"}), 500
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e), "success": False}), 500


@simulation_bp.route("/api/simulation/status", methods=["GET"])
@login_required
def get_simulation_status():
    gm_profile, err = _gm_profile_or_403()
    if err:
        return err

    try:
        state = get_simulation_state_for_gm(db.session, gm_profile.id)
        tick_val = state.current_tick if state else 0
        last_iso = (
            state.last_tick_time.isoformat() if state and state.last_tick_time else None
        )
        active = bool(state and state.speed != "pause")
        status = {
            "active": active,
            "tick": tick_val,
            "current_tick": tick_val,
            "speed": state.speed if state else "pause",
            "last_tick": last_iso,
            "last_tick_time": last_iso,
            "current_game_day": gm_profile.current_game_day,
            "status": "running" if active else "paused",
        }
        response = make_response(jsonify(status))
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    except SQLAlchemyError:
        return jsonify({"error": "Database error occurred"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@simulation_bp.route("/api/simulation/logs", methods=["GET"])
@login_required
def get_simulation_logs():
    gm_profile, err = _gm_profile_or_403()
    if err:
        return err

    try:
        limit = request.args.get("limit", default=50, type=int)
        logs = (
            SimulationLog.query.filter_by(gm_profile_id=gm_profile.id)
            .order_by(SimulationLog.timestamp.desc())
            .limit(limit)
            .all()
        )
        result = [
            {
                "tick_id": log.tick_id,
                "event_type": log.event_type,
                "details": log.details,
                "timestamp": log.timestamp.isoformat(),
            }
            for log in logs
        ]
        return jsonify(result)
    except SQLAlchemyError:
        return jsonify({"error": "Database error occurred"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
