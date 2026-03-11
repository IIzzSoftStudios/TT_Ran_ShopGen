"""
REST API for NumPy sim: start/stop, subscribe_to_city, Market Pulse, Observer (city slice as binary).
Aggregation only - never stream 300k rows.
"""
import queue
import threading
from flask import Blueprint, request, jsonify, current_app, abort
from flask_login import login_required, current_user

from app.services.sim_runner import SimRunner


def _require_gm():
    """Abort with 403 if the current user is not a GM."""
    if getattr(current_user, "role", None) != "GM":
        abort(403)

sim_api_bp = Blueprint("sim_api", __name__, url_prefix="/api/sim")

# Lazy singleton runner (created per app when first needed)
_runner: SimRunner = None
_runner_lock = threading.Lock()


def get_runner() -> SimRunner:
    global _runner
    with _runner_lock:
        if _runner is None:
            _runner = SimRunner(
                app=current_app._get_current_object(),
                num_agents=300_000,
                ring_buffer_ticks=60,
                cold_batch_size=100,
                sim_id="default",
            )
            # Optional: push pulse + city slices to a queue for WebSocket/sse later
            _broadcast_q = queue.Queue(maxsize=64)

            def _broadcast(pulse: dict, city_slices: dict):
                try:
                    _broadcast_q.put_nowait({"pulse": pulse, "city_slices": city_slices})
                except queue.Full:
                    pass

            _runner.set_broadcast_callback(_broadcast)
        return _runner


@sim_api_bp.route("/start", methods=["POST"])
@login_required
def start():
    """Start the simulation loop in the background (1 tick/sec, fixed timestep + catch-up)."""
    _require_gm()
    get_runner().start_background()
    return jsonify({"status": "started"})


@sim_api_bp.route("/stop", methods=["POST"])
@login_required
def stop():
    """Stop the simulation and cold worker."""
    _require_gm()
    get_runner().stop()
    return jsonify({"status": "stopped"})


def _parse_city_id():
    """Extract and validate city_id from JSON body or query string. Returns (city_id, error_response)."""
    data = request.get_json() or {}
    raw = data.get("city_id")
    if raw is None:
        raw = request.args.get("city_id")
    if raw is None:
        return None, (jsonify({"error": "city_id required"}), 400)
    try:
        return int(raw), None
    except (TypeError, ValueError):
        return None, (jsonify({"error": "city_id must be an integer"}), 400)


@sim_api_bp.route("/subscribe_city", methods=["POST"])
@login_required
def subscribe_city():
    """Add city_id to the Watch List; each tick the server will include that city's slice in broadcast."""
    _require_gm()
    city_id, err = _parse_city_id()
    if err is not None:
        return err
    get_runner().subscribe_city(city_id)
    return jsonify({"subscribed": city_id})


@sim_api_bp.route("/unsubscribe_city", methods=["POST"])
@login_required
def unsubscribe_city():
    """Remove city_id from the Watch List."""
    _require_gm()
    city_id, err = _parse_city_id()
    if err is not None:
        return err
    get_runner().unsubscribe_city(city_id)
    return jsonify({"unsubscribed": city_id})


@sim_api_bp.route("/pulse", methods=["GET"])
@login_required
def get_pulse():
    """Return the latest Market Pulse (mean_price, median_gold, volume, std_price, tick) for charts."""
    runner = get_runner()
    pulse = runner.get_latest_pulse()
    if pulse is None:
        return jsonify({"pulse": None, "message": "no tick yet"})
    # Remove internal keys
    out = {k: v for k, v in pulse.items() if not k.startswith("_")}
    return jsonify({"pulse": out})


@sim_api_bp.route("/city/<int:city_id>", methods=["GET"])
@login_required
def get_city_slice(city_id):
    """
    Observer: return binary slice of agents in this city (fixed-width dtype).
    Client can decode with TypedArray/DataView using the same dtype layout.
    """
    runner = get_runner()
    data = runner.get_city_slice_bytes(city_id)
    from flask import Response
    return Response(data, mimetype="application/octet-stream", headers={
        "Content-Type": "application/octet-stream",
        "X-Agent-Dtype-Bytes": "21",  # AGENT_DTYPE.itemsize for client
    })
