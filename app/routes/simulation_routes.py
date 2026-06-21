from flask import Blueprint, jsonify, request, make_response, session
from flask_login import login_required, current_user
from sqlalchemy.exc import SQLAlchemyError

from app.constants.simulation_flags import ALLOWED_SIMULATION_SPEEDS
from app.extensions import db
from app.models import Campaign, SimulationLog, SimulationState
from app.services.simulation_state_helpers import get_simulation_state_for_campaign
from app.utils.safe_errors import public_error_message

simulation_bp = Blueprint("simulation", __name__)


def _gm_profile_or_403():
    if not current_user.gm_profile:
        return None, (jsonify({"error": "User is not a GM"}), 403)
    return current_user.gm_profile, None


def _active_campaign_or_400(gm_profile):
    raw_campaign_id = session.get("campaign_id")
    if not raw_campaign_id:
        return None, (
            jsonify({"error": "Please select a campaign before running simulation."}),
            400,
        )
    try:
        campaign_id = int(raw_campaign_id)
    except (TypeError, ValueError):
        session.pop("campaign_id", None)
        session.modified = True
        return None, (
            jsonify(
                {"error": "Invalid campaign session. Please select a campaign again."}
            ),
            400,
        )
    campaign = Campaign.query.filter_by(
        id=campaign_id,
        gm_profile_id=gm_profile.id,
        is_active=True,
    ).first()
    if campaign is None:
        session.pop("campaign_id", None)
        session.modified = True
        return None, (
            jsonify(
                {"error": "Invalid campaign session. Please select a campaign again."}
            ),
            400,
        )
    return campaign, None


@simulation_bp.route("/api/simulation/speed", methods=["POST"])
@login_required
def set_simulation_speed():
    gm_profile, err = _gm_profile_or_403()
    if err:
        return err
    campaign, camp_err = _active_campaign_or_400(gm_profile)
    if camp_err:
        return camp_err

    data = request.get_json()
    if not data or "speed" not in data:
        return jsonify({"error": "Speed parameter is required"}), 400

    speed = data["speed"]
    if speed not in ALLOWED_SIMULATION_SPEEDS:
        return jsonify({"error": "Invalid speed setting"}), 400

    try:
        state = get_simulation_state_for_campaign(db.session, campaign.id)
        if not state:
            from datetime import datetime

            state = SimulationState(
                current_tick=0,
                speed=speed,
                last_tick_time=datetime.utcnow(),
                campaign_id=campaign.id,
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
                "current_game_day": campaign.current_game_day,
            }
        )
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "Database error occurred"}), 500
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": public_error_message(e)}), 500


@simulation_bp.route("/api/simulation/status", methods=["GET"])
@login_required
def get_simulation_status():
    gm_profile, err = _gm_profile_or_403()
    if err:
        return err
    campaign, camp_err = _active_campaign_or_400(gm_profile)
    if camp_err:
        return camp_err

    try:
        state = get_simulation_state_for_campaign(db.session, campaign.id)
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
            "current_game_day": campaign.current_game_day,
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
        return jsonify({"error": public_error_message(e)}), 500


@simulation_bp.route("/api/simulation/logs", methods=["GET"])
@login_required
def get_simulation_logs():
    gm_profile, err = _gm_profile_or_403()
    if err:
        return err
    campaign, camp_err = _active_campaign_or_400(gm_profile)
    if camp_err:
        return camp_err

    try:
        limit = request.args.get("limit", default=50, type=int)
        logs = (
            SimulationLog.query.filter_by(campaign_id=campaign.id)
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
        return jsonify({"error": public_error_message(e)}), 500
