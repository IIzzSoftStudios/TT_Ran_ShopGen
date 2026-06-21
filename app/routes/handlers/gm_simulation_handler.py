"""
GM Simulation Handler
Handles all simulation-related business logic for GM routes
"""
<<<<<<< HEAD
import json

from flask import render_template, request, redirect, url_for, flash, jsonify, Response, stream_with_context
from app.services.logging_config import gm_logger
from app.services.simulation import SimulationEngine
from app.scripts.seeder import seed_gm_data
from app.extensions import db
from app.routes.handlers.gm_helpers import get_current_gm_profile
from app.routes.handlers.gm_shops_handler import get_shop_city_panel_context
from datetime import datetime
=======
import os
from datetime import datetime
from functools import wraps

from flask import render_template, request, redirect, url_for, flash, jsonify, session
from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError
from app.services.logging_config import gm_logger
from app.scripts.seeder import seed_gm_data
from app.extensions import db
from app.models import Campaign, City, Player, Shop, SimulationState
from app.services.simulation_state_helpers import get_simulation_state_for_campaign
from app.routes.handlers.gm_helpers import get_current_gm_profile, require_active_campaign
from app.routes.handlers.gm_players_handler import build_player_entries
from app.routes.handlers.gm_shops_handler import get_shop_city_panel_context
from app.services.distributed_lock import get_redis_client
from app.services.market_overview import capture_start_metrics_for_job
from app.tasks.simulation_tasks import SimJobStatus, run_period_task, simulation_pause_key
from app.utils.safe_errors import public_error_message, redact_sim_job_error_for_client


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
>>>>>>> GCP


def _debug_request(request_type: str, route: str):
    """Debug helper for request logging."""
<<<<<<< HEAD
    simulation_engine = SimulationEngine()
=======
>>>>>>> GCP
    gm_logger.debug(
        f"{request_type} request to {route}:\n"
        f"  Method: {request.method}\n"
        f"  Form data: {request.form}\n"
        f"  Args: {request.args}\n"
<<<<<<< HEAD
        f"  Current speed: {simulation_engine.current_speed}\n"
        f"  Last tick: {simulation_engine.last_tick_time}"
    )


=======
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


def build_gm_onboarding_context(gm_profile, campaign):
    """Read-only checklist state for GM Home (no writes)."""
    if campaign is None or gm_profile is None:
        return None
    if campaign.gm_profile_id != gm_profile.id:
        return None

    cid = int(campaign.id)
    city_count = City.query.filter_by(campaign_id=cid).count()
    shop_count = Shop.query.filter_by(campaign_id=cid).count()
    has_world = city_count > 0 and shop_count > 0
    player_count = Player.query.filter_by(
        campaign_id=cid, is_npc=False
    ).count()
    current_day = int(campaign.current_game_day or 1)
    first_sim_done = current_day > 1

    steps = {
        "world": has_world,
        "players": player_count > 0,
        "simulation": first_sim_done,
    }
    all_complete = all(steps.values())

    return {
        "show": not all_complete,
        "all_complete": all_complete,
        "has_generated_world": has_world,
        "player_count": player_count,
        "join_code_ready": bool(campaign.join_code),
        "first_sim_completed": first_sim_done,
        "show_first_sim_prompt": not first_sim_done,
        "current_game_day": current_day,
        "steps": steps,
        "generate_world_url": url_for("gm.generate_world_form"),
        "players_view_url": url_for("gm.gm_view_players"),
        "campaign_players_url": url_for("gm.view_campaigns", onboarding="players"),
    }


>>>>>>> GCP
def home():
    """Render the GM dashboard with simulation controls and status."""
    gm_profile, redirect_response = get_current_gm_profile()
    if redirect_response:
        return redirect_response
<<<<<<< HEAD

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

    shops_panel = get_shop_city_panel_context(gm_profile)
    return render_template(
        "GM_Home.html",
        gm_profile=gm_profile,
        current_speed=simulation_engine.current_speed,
        last_tick_time=simulation_engine.last_tick_time,
        simulation_status="active" if simulation_engine.current_speed != "pause" else "paused",
=======
    _debug_request("GET", "/gm/")

    campaign, redirect_response = require_active_campaign(gm_profile)
    if redirect_response is not None:
        return redirect_response

    shops_panel = get_shop_city_panel_context(gm_profile, include_nav_toggles=True)
    player_entries = build_player_entries(campaign)
    onboarding_checklist = build_gm_onboarding_context(gm_profile, campaign)
    # Battle tab is D&D-5e-only: hidden entirely for other rulesets.
    from app.services.rulesets import get_ruleset

    combat_enabled = (
        campaign is not None
        and get_ruleset(campaign.system_type).system_type == "dnd5e"
    )
    character_creation_settings = None
    species_compendium_preview = []
    if combat_enabled and campaign is not None:
        from app.services.character_creation.campaign_settings import (
            get_creation_settings,
        )
        from app.services.species_compendium_service import ensure_species_compendium

        character_creation_settings = get_creation_settings(campaign.id)
        species_compendium_preview = ensure_species_compendium(campaign.id)
    return render_template(
        "GM_Home.html",
        gm_profile=gm_profile,
        current_speed="pause",
        onboarding_checklist=onboarding_checklist,
        combat_enabled=combat_enabled,
        player_entries=player_entries,
        character_creation_settings=character_creation_settings,
        species_compendium_preview=species_compendium_preview,
>>>>>>> GCP
        **shops_panel,
    )


def seed_world():
    """Route to trigger the seeding of the GM's world data."""
<<<<<<< HEAD
    simulation_engine = SimulationEngine()
=======
>>>>>>> GCP
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
<<<<<<< HEAD
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
=======
        flash(public_error_message(e), "error")

    return redirect(url_for("gm.home"))


def update_simulation_speed():
    """Set simulation speed to pause (matches ``/api/simulation/status`` and ``SimulationState``)."""
>>>>>>> GCP
    _debug_request("POST", "/gm/simulation/speed")

    gm_profile, redirect_response = get_current_gm_profile()
    if redirect_response:
        return redirect_response
<<<<<<< HEAD
=======
    campaign_id, campaign_error = _active_campaign_id_for_simulation(gm_profile)
    if campaign_error:
        return campaign_error
>>>>>>> GCP

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

<<<<<<< HEAD
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
=======
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
        redis_client = get_redis_client()
        redis_client.set(
            simulation_pause_key(campaign_id),
            "1",
            ex=int(os.getenv("SIM_JOB_TTL_SECONDS", "86400")),
        )
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
    except (RedisConnectionError, RedisTimeoutError) as exc:
        db.session.rollback()
        gm_logger.warning("Redis unavailable while pausing simulation: %s", exc)
        return jsonify({"error": REDIS_OFFLINE_ERROR, "status": "offline"}), 503
    except Exception as e:
        db.session.rollback()
        gm_logger.error(f"Error during simulation: {str(e)}", exc_info=True)
        return jsonify({"error": public_error_message(e), "status": "error"}), 500


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
>>>>>>> GCP

    payload = request.get_json(silent=True) or {}
    period = payload.get("period")
    ticks_map = {"day": 1, "week": 7, "month": 30, "year": 365}
    if period not in ticks_map:
        return jsonify({"error": "Invalid or missing period", "status": "invalid"}), 400

<<<<<<< HEAD
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
=======
    redis_client = get_redis_client()
    lock_key = f"lock:sim:{int(campaign_id)}"
    if redis_client.exists(lock_key):
        return (
            jsonify({"error": "Simulation already running", "status": SimJobStatus.BUSY}),
            409,
        )
    redis_client.delete(simulation_pause_key(campaign_id))

    campaign = Campaign.query.get(campaign_id)
    start_metrics_json = capture_start_metrics_for_job(int(campaign_id))
    task = run_period_task.delay(int(campaign_id), period)
    # Seed the job key (with pre-tick metrics) before the worker can read an
    # empty hash. The task overwrites status/ticks with its own frames.
    redis_client.hset(
        f"sim_job:{task.id}",
        mapping={
            "status": SimJobStatus.QUEUED,
            "ticks_done": 0,
            "ticks_total": ticks_map[period],
            "current_game_day": campaign.current_game_day if campaign else 0,
            "campaign_id": campaign_id or "",
            "period": period,
            "start_metrics_json": start_metrics_json,
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
    SimJobStatus.PAUSED,
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
    world_changed_flag = data.get("world_changed")
    if world_changed_flag is not None:
        world_changed = str(world_changed_flag).lower() in ("true", "1", "yes")
    else:
        # Default: only a clean SUCCESS means the world advanced and snapshot
        # was saved. ERROR without an explicit flag still means unchanged
        # (failed batch rolled back).
        world_changed = status == SimJobStatus.SUCCESS

    out = {
        "status": status,
        "ticks_done": _to_int(data.get("ticks_done")),
        "ticks_total": _to_int(data.get("ticks_total")),
        "current_game_day": _to_int(data.get("current_game_day")),
        "units_sold_total": _to_int(data.get("units_sold_total")),
        "shops_restocked_total": _to_int(data.get("shops_restocked_total")),
        "error": redact_sim_job_error_for_client(data.get("error")),
        "world_changed": world_changed,
        "terminal": status in _REENTRANT_TERMINAL_STATUSES,
    }
    return jsonify(out)
>>>>>>> GCP


def debug_form():
    """Debug form submission"""
    print("FORM KEYS:", request.form.keys())
    print("FORM DICT:", request.form.to_dict(flat=False))
    return "Check logs"
