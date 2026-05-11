"""
GM Simulation Handler
Handles all simulation-related business logic for GM routes
"""
from datetime import datetime
from functools import wraps

from flask import render_template, request, redirect, url_for, flash, jsonify, session
from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError
from app.services.logging_config import gm_logger
from app.scripts.seeder import seed_gm_data
from app.extensions import db
from app.models import Campaign, SimulationState
from app.services.simulation_state_helpers import get_simulation_state_for_campaign
from app.routes.handlers.gm_helpers import get_current_gm_profile, require_active_campaign
from app.routes.handlers.gm_shops_handler import get_shop_city_panel_context
from app.services.distributed_lock import get_redis_client
from app.tasks.simulation_tasks import SimJobStatus, run_period_task


REDIS_OFFLINE_ERROR = "Simulation service is currently offline. Please try again in a few minutes."

_SIM_DASHBOARD_CLICK_ATTR = {
    "day": "sim_clicks_day",
    "week": "sim_clicks_week",
    "month": "sim_clicks_month",
    "year": "sim_clicks_year",
    "pause": "sim_clicks_pause",
}


def _record_sim_dashboard_click(campaign_id: int, kind: str) -> None:
    """Count one successful GM dashboard simulation control action (no commit)."""
    attr = _SIM_DASHBOARD_CLICK_ATTR.get(kind)
    if not attr:
        return
    state = get_simulation_state_for_campaign(db.session, campaign_id)
    if state is None:
        state = SimulationState(
            campaign_id=campaign_id,
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


def _active_campaign_id_for_simulation(gm_profile):
    """Return the loaded campaign id for this GM or a JSON error response."""
    raw_campaign_id = session.get("campaign_id")
    if not raw_campaign_id:
        return None, (
            jsonify(
                {
                    "error": "Please select a campaign before running simulation.",
                    "status": "invalid",
                }
            ),
            400,
        )
    try:
        campaign_id = int(raw_campaign_id)
    except (TypeError, ValueError):
        session.pop("campaign_id", None)
        session.modified = True
        return None, (
            jsonify(
                {
                    "error": "Invalid campaign session. Please select a campaign again.",
                    "status": "invalid",
                }
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
                {
                    "error": "Invalid campaign session. Please select a campaign again.",
                    "status": "invalid",
                }
            ),
            400,
        )
    return campaign_id, None


def home():
    """Render the GM dashboard with simulation controls and status."""
    gm_profile, redirect_response = get_current_gm_profile()
    if redirect_response:
        return redirect_response
    _debug_request("GET", "/gm/")

    campaign, redirect_response = require_active_campaign(gm_profile)
    if redirect_response is not None:
        return redirect_response

    shops_panel = get_shop_city_panel_context(gm_profile)
    return render_template(
        "GM_Home.html",
        gm_profile=gm_profile,
        campaign=campaign,
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


def update_simulation_speed():
    """Set simulation speed to pause (matches ``/api/simulation/status`` and ``SimulationState``)."""
    _debug_request("POST", "/gm/simulation/speed")

    gm_profile, redirect_response = get_current_gm_profile()
    if redirect_response:
        return redirect_response
    campaign_id, campaign_error = _active_campaign_id_for_simulation(gm_profile)
    if campaign_error:
        return campaign_error

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

        state = get_simulation_state_for_campaign(db.session, campaign_id)
        if not state:
            state = SimulationState(
                current_tick=0,
                speed="pause",
                last_tick_time=datetime.utcnow(),
                campaign_id=campaign_id,
            )
            db.session.add(state)
        else:
            state.speed = "pause"
        db.session.flush()
        _record_sim_dashboard_click(campaign_id, "pause")
        db.session.commit()

        campaign = Campaign.query.get(campaign_id)
        return jsonify(
            {
                "status": "ok",
                "message": "Simulation paused",
                "speed": state.speed,
                "current_game_day": campaign.current_game_day if campaign else None,
            }
        )
    except Exception as e:
        db.session.rollback()
        gm_logger.error(f"Error during simulation: {str(e)}")
        return jsonify({"error": str(e), "status": "error"}), 500


@handle_redis_outage
def run_period_stream():
    """Enqueue day/week/month/year simulation as a background Celery job.

    All four periods (Day/Week/Month/Year) flow through a single Celery
    task ``run_period_task`` — there is no separate synchronous tick path.
    The task runs as one ACID batch (commit at end, rollback on failure)
    so a failed run never leaves the campaign world half-advanced.
    """
    gm_profile, redirect_response = get_current_gm_profile()
    if redirect_response:
        return redirect_response
    campaign_id, campaign_error = _active_campaign_id_for_simulation(gm_profile)
    if campaign_error:
        return campaign_error

    payload = request.get_json(silent=True) or {}
    period = payload.get("period")
    ticks_map = {"day": 1, "week": 7, "month": 30, "year": 365}
    if period not in ticks_map:
        return jsonify({"error": "Invalid or missing period", "status": "invalid"}), 400

    redis_client = get_redis_client()
    lock_key = f"lock:sim:{int(campaign_id)}"
    if redis_client.exists(lock_key):
        return (
            jsonify({"error": "Simulation already running", "status": SimJobStatus.BUSY}),
            409,
        )

    task = run_period_task.delay(int(campaign_id), period)

    campaign = Campaign.query.get(campaign_id)
    # Seed the job key so the polling UI sees an entry before the worker
    # picks the task up. The task overwrites this with its own queued/running
    # frames and an authoritative current_game_day.
    redis_client.hset(
        f"sim_job:{task.id}",
        mapping={
            "status": SimJobStatus.QUEUED,
            "ticks_done": 0,
            "ticks_total": ticks_map[period],
            "current_game_day": campaign.current_game_day if campaign else 0,
            "campaign_id": campaign_id or "",
            "period": period,
        },
    )

    try:
        _record_sim_dashboard_click(int(campaign_id), period)
        db.session.commit()
    except Exception:
        db.session.rollback()
        gm_logger.warning("Could not persist simulation button click count", exc_info=True)

    return jsonify({"job_id": task.id}), 202


# Terminal job statuses that mean "world unchanged" — UI uses this set to
# decide whether to re-enable run buttons immediately or block on operator
# reconciliation. lock_lost is included because the ACID batch rolls back on
# refresh failure too.
_REENTRANT_TERMINAL_STATUSES = {
    SimJobStatus.SUCCESS,
    SimJobStatus.ERROR,
    SimJobStatus.LOCK_LOST,
    SimJobStatus.BUSY,
}


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

    status = data.get("status")
    out = {
        "status": status,
        "ticks_done": _to_int(data.get("ticks_done")),
        "ticks_total": _to_int(data.get("ticks_total")),
        "current_game_day": _to_int(data.get("current_game_day")),
        "error": data.get("error"),
        # `world_changed=False` means the campaign is byte-for-byte identical
        # to its pre-run state and the GM can re-click the period button. The
        # ACID batch guarantees this is true for every non-success terminal.
        "world_changed": status == SimJobStatus.SUCCESS,
        "terminal": status in _REENTRANT_TERMINAL_STATUSES,
    }
    return jsonify(out)


def debug_form():
    """Debug form submission"""
    print("FORM KEYS:", request.form.keys())
    print("FORM DICT:", request.form.to_dict(flat=False))
    return "Check logs"
