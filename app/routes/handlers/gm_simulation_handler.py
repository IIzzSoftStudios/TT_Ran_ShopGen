"""
GM Simulation Handler
Handles all simulation-related business logic for GM routes
"""
import json

from flask import render_template, request, redirect, url_for, flash, jsonify, Response, stream_with_context
from app.services.logging_config import gm_logger
from app.services.simulation import SimulationEngine
from app.scripts.seeder import seed_gm_data
from app.extensions import db
from app.routes.handlers.gm_helpers import get_current_gm_profile
from datetime import datetime


def _debug_request(request_type: str, route: str):
    """Debug helper for request logging."""
    simulation_engine = SimulationEngine()
    gm_logger.debug(
        f"{request_type} request to {route}:\n"
        f"  Method: {request.method}\n"
        f"  Form data: {request.form}\n"
        f"  Args: {request.args}\n"
        f"  Current speed: {simulation_engine.current_speed}\n"
        f"  Last tick: {simulation_engine.last_tick_time}"
    )


def home():
    """Render the GM dashboard with simulation controls and status."""
    gm_profile, redirect_response = get_current_gm_profile()
    if redirect_response:
        return redirect_response

    simulation_engine = SimulationEngine()
    _debug_request("GET", "/gm/")

    if simulation_engine.should_run_tick():
        try:
            stats = simulation_engine.run_tick(gm_profile.id)
            flash(
                f"Simulation tick completed: Updated {stats['shops_updated']} shops "
                f"and {stats['items_updated']} items.",
                "system",
            )
        except Exception as e:
            flash(f"Error during simulation tick: {str(e)}", "danger")

    gm_logger.debug(
        f"GM dashboard state:\n"
        f"  User ID: {gm_profile.id}\n"
        f"  Current speed: {simulation_engine.current_speed}\n"
        f"  Last tick: {simulation_engine.last_tick_time}\n"
        f"  Time since last tick: {datetime.now() - simulation_engine.last_tick_time}"
    )

    return render_template(
        "GM_Home.html",
        gm_profile=gm_profile,
        current_speed=simulation_engine.current_speed,
        last_tick_time=simulation_engine.last_tick_time,
        simulation_status="active" if simulation_engine.current_speed != "pause" else "paused",
    )


def seed_world():
    """Route to trigger the seeding of the GM's world data."""
    simulation_engine = SimulationEngine()
    _debug_request("POST", "/gm/seed_world")

    gm_profile, redirect_response = get_current_gm_profile()
    if redirect_response:
        return redirect_response

    try:
        success = seed_gm_data(
            gm_profile.id,
            num_cities=10,
            num_shops_per_city=10,
            num_global_items=75,
            num_items_per_shop=10,
        )
        if success:
            flash("Your world has been successfully seeded!", "success")
        else:
            flash("Failed to seed world. Check server logs for details.", "error")
    except Exception as e:
        db.session.rollback()
        gm_logger.error(f"Error during seeding world: {str(e)}", exc_info=True)
        flash(f"An error occurred during seeding: {str(e)}", "error")

    return redirect(url_for("gm.gm_home"))


def run_simulation_tick():
    """Execute one simulation tick manually from the GM dashboard."""
    simulation_engine = SimulationEngine()
    _debug_request("POST", "/gm/simulation/tick")

    gm_profile, redirect_response = get_current_gm_profile()
    if redirect_response:
        return redirect_response

    lock = SimulationEngine.get_lock()
    if not lock.acquire(blocking=False):
        return jsonify({"error": "Simulation already running", "status": "busy"}), 409
    try:
        stats = simulation_engine.run_tick(gm_profile.id)

        gm_logger.debug(
            f"Manual tick execution:\n"
            f"  Campaign ID: {gm_profile.id}\n"
            f"  Shops updated: {stats['shops_updated']}\n"
            f"  Items updated: {stats['items_updated']}\n"
            f"  Last tick time: {simulation_engine.last_tick_time}\n"
            f"  Time since last tick: {datetime.now() - simulation_engine.last_tick_time}"
        )

        return jsonify(
            {
                "status": "success",
                "message": (
                    f"Simulation tick completed: Updated {stats['shops_updated']} shops "
                    f"and {stats['items_updated']} items."
                ),
                "stats": stats,
                "current_game_day": stats.get("current_game_day"),
            }
        )
    except Exception as e:
        gm_logger.error(f"Error during simulation tick: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500
    finally:
        lock.release()


def update_simulation_speed():
    """Pause the simulation engine (period runs use the NDJSON stream endpoint)."""
    simulation_engine = SimulationEngine()
    _debug_request("POST", "/gm/simulation/speed")

    gm_profile, redirect_response = get_current_gm_profile()
    if redirect_response:
        return redirect_response

    try:
        payload = request.get_json(silent=True) or {}
        speed = request.form.get("speed") or payload.get("speed", "pause")
        if speed != "pause":
            return (
                jsonify(
                    {
                        "error": "Period simulations use POST /gm/simulation/run-period",
                        "status": "invalid",
                    }
                ),
                400,
            )

        simulation_engine.set_speed("pause")
        return jsonify({"status": "ok", "message": "Simulation paused"})
    except Exception as e:
        gm_logger.error(f"Error during simulation: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


def run_period_stream():
    """Run day/week/month/year as NDJSON stream (one line per tick, commit per tick)."""
    gm_profile, redirect_response = get_current_gm_profile()
    if redirect_response:
        return redirect_response

    payload = request.get_json(silent=True) or {}
    period = payload.get("period")
    ticks_map = {"day": 1, "week": 7, "month": 30, "year": 365}
    if period not in ticks_map:
        return jsonify({"error": "Invalid or missing period", "status": "invalid"}), 400

    lock = SimulationEngine.get_lock()
    if not lock.acquire(blocking=False):
        return jsonify({"error": "Simulation already running", "status": "busy"}), 409

    total_ticks = ticks_map[period]

    def generate():
        engine = None
        try:
            engine = SimulationEngine()
            engine.set_speed(period)
            for i in range(1, total_ticks + 1):
                stats = engine.run_tick(gm_profile.id, commit=True)
                line = {
                    "current_game_day": stats["current_game_day"],
                    "tick": i,
                    "total": total_ticks,
                }
                yield json.dumps(line) + "\n"
        except Exception as e:
            gm_logger.error(f"Streamed simulation failed: {str(e)}", exc_info=True)
            yield json.dumps({"error": str(e), "tick": None}) + "\n"
        finally:
            if engine is not None:
                try:
                    engine.set_speed("pause")
                except Exception:
                    pass
            lock.release()

    return Response(stream_with_context(generate()), mimetype="application/x-ndjson")


def debug_form():
    """Debug form submission"""
    print("FORM KEYS:", request.form.keys())
    print("FORM DICT:", request.form.to_dict(flat=False))
    return "Check logs"
