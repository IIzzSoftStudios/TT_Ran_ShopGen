"""
GM Simulation Handler
Handles all simulation-related business logic for GM routes
"""
from datetime import datetime
from functools import wraps

from flask import render_template, request, redirect, url_for, flash, jsonify, session
from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError
from app.services.logging_config import gm_logger
from app.services.simulation import SimulationEngine
from app.scripts.seeder import seed_gm_data
from app.extensions import db
from app.models import SimulationState
from app.services.simulation_state_helpers import get_simulation_state_for_gm
from app.routes.handlers.gm_helpers import get_current_gm_profile
from app.routes.handlers.gm_shops_handler import get_shop_city_panel_context
from app.services.distributed_lock import acquire_simulation_lock
from app.services.distributed_lock import get_redis_client
from app.tasks.simulation_tasks import run_period_task


REDIS_OFFLINE_ERROR = "Simulation service is currently offline. Please try again in a few minutes."

_SIM_DASHBOARD_CLICK_ATTR = {
    "day": "sim_clicks_day",
    "week": "sim_clicks_week",
    "month": "sim_clicks_month",
    "year": "sim_clicks_year",
    "pause": "sim_clicks_pause",
}


def _record_sim_dashboard_click(gm_profile_id: int, kind: str) -> None:
    """Count one successful GM dashboard simulation control action (no commit)."""
    attr = _SIM_DASHBOARD_CLICK_ATTR.get(kind)
    if not attr:
        return
    state = get_simulation_state_for_gm(db.session, gm_profile_id)
    if state is None:
        state = SimulationState(
            gm_profile_id=gm_profile_id,
            current_tick=0,
            speed="pause",
            last_tick_time=datetime.utcnow(),
        )
        setattr(state, attr, 1)
        db.session.add(state)
    else:
        setattr(state, attr, int(getattr(state, attr) or 0) + 1)


def handle_redis_outage(func):
    """Return a user-safe 503 when Redis broker/cache is unavailable."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (RedisConnectionError, RedisTimeoutError) as exc:
            # Expected when Redis/broker is down or too slow; avoid ERROR+traceback spam per request.
            gm_logger.warning("Redis unavailable in simulation endpoint: %s", exc)
            return jsonify({"error": REDIS_OFFLINE_ERROR, "status": "offline"}), 503

    return wrapper


def _debug_request(request_type: str, route: str):
    """Debug helper for request logging."""
    gm_logger.debug(
        f"{request_type} request to {route}:\n"
        f"  Method: {request.method}\n"
        f"  Form data: {request.form}\n"
        f"  Args: {request.args}\n"
    )


def home():
    """Render the GM dashboard with simulation controls and status."""
    gm_profile, redirect_response = get_current_gm_profile()
    if redirect_response:
        return redirect_response
    _debug_request("GET", "/gm/")

    shops_panel = get_shop_city_panel_context(gm_profile)
    return render_template(
        "GM_Home.html",
        gm_profile=gm_profile,
        # Statless: we no longer auto-advance simulation on page load.
        # Client-side runs will drive button active state later during the polling migration.
        current_speed="pause",
        **shops_panel,
    )


def seed_world():
    """Route to trigger the seeding of the GM's world data."""
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

    return redirect(url_for("gm.home"))


@handle_redis_outage
def run_simulation_tick():
    """Execute one simulation tick manually from the GM dashboard."""
    _debug_request("POST", "/gm/simulation/tick")

    gm_profile, redirect_response = get_current_gm_profile()
    if redirect_response:
        return redirect_response

    lock = acquire_simulation_lock(gm_profile.id, ttl_seconds=10, blocking=False)
    if lock is None:
        return jsonify({"error": "Simulation already running", "status": "busy"}), 409

    simulation_engine = SimulationEngine()
    try:
        stats = simulation_engine.run_tick(
            gm_profile.id,
            campaign_id=session.get("campaign_id"),
        )

        gm_logger.debug(
            f"Manual tick execution:\n"
            f"  Campaign ID: {gm_profile.id}\n"
            f"  Shops updated: {stats['shops_updated']}\n"
            f"  Items updated: {stats['items_updated']}\n"
            f"  Tick duration: {stats.get('tick_duration')}s\n"
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
    """Set simulation speed to pause (matches ``/api/simulation/status`` and ``SimulationState``)."""
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

        state = get_simulation_state_for_gm(db.session, gm_profile.id)
        if not state:
            state = SimulationState(
                current_tick=0,
                speed="pause",
                last_tick_time=datetime.utcnow(),
                gm_profile_id=gm_profile.id,
            )
            db.session.add(state)
        else:
            state.speed = "pause"
        db.session.flush()
        _record_sim_dashboard_click(gm_profile.id, "pause")
        db.session.commit()

        return jsonify(
            {
                "status": "ok",
                "message": "Simulation paused",
                "speed": state.speed,
                "current_game_day": gm_profile.current_game_day,
            }
        )
    except Exception as e:
        db.session.rollback()
        gm_logger.error(f"Error during simulation: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


@handle_redis_outage
def run_period_stream():
    """Enqueue day/week/month/year simulation as a background Celery job."""
    gm_profile, redirect_response = get_current_gm_profile()
    if redirect_response:
        return redirect_response

    payload = request.get_json(silent=True) or {}
    period = payload.get("period")
    ticks_map = {"day": 1, "week": 7, "month": 30, "year": 365}
    if period not in ticks_map:
        return jsonify({"error": "Invalid or missing period", "status": "invalid"}), 400

    # Fast check: if Redis lock exists, we expect the GM to be busy.
    redis_client = get_redis_client()
    lock_key = f"lock:sim:{int(gm_profile.id)}"
    if redis_client.exists(lock_key):
        return jsonify({"error": "Simulation already running", "status": "busy"}), 409

    # Enqueue background execution.
    task = run_period_task.delay(int(gm_profile.id), period)

    # Optional: prime queued state for immediate polling.
    redis_client.hset(
        f"sim_job:{task.id}",
        mapping={
            "status": "queued",
            "ticks_done": 0,
            "ticks_total": ticks_map[period],
            "current_game_day": gm_profile.current_game_day,
        },
    )

    try:
        _record_sim_dashboard_click(int(gm_profile.id), period)
        db.session.commit()
    except Exception:
        db.session.rollback()
        gm_logger.warning("Could not persist simulation button click count", exc_info=True)

    return jsonify({"job_id": task.id}), 202


@handle_redis_outage
def simulation_job_status(job_id: str):
    """Return per-tick job progress from Redis for polling UI."""
    redis_client = get_redis_client()
    job_key = f"sim_job:{job_id}"
    data = redis_client.hgetall(job_key) or {}
    if not data:
        return jsonify({"error": "Job not found", "status": "not_found"}), 404

    def _to_int(v):
        try:
            return int(v)
        except Exception:
            return None

    out = {
        "status": data.get("status"),
        "ticks_done": _to_int(data.get("ticks_done")),
        "ticks_total": _to_int(data.get("ticks_total")),
        "current_game_day": _to_int(data.get("current_game_day")),
        "error": data.get("error"),
    }
    return jsonify(out)


def debug_form():
    """Debug form submission"""
    print("FORM KEYS:", request.form.keys())
    print("FORM DICT:", request.form.to_dict(flat=False))
    return "Check logs"
