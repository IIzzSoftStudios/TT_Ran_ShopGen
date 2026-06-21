"""GM interactive map API handlers (JSON).

Campaign authority comes from the GM session only -- client payloads are
never trusted for `campaign_id`. Entity ids from the browser are treated
as references that must resolve inside the active campaign or the request
fails with 403/404 JSON errors.
"""

import io
import logging

from flask import jsonify, request, send_file, session
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Campaign, MapCanvas
from app.routes.handlers.gm_helpers import city_for_campaign_optional
from app.services import gm_maps
from app.services.gm_maps import MapValidationError

log = logging.getLogger(__name__)


def _campaign_for_json():
    """Resolve the active GM campaign for JSON endpoints.

    Returns ``(campaign, None)`` or ``(None, (json_response, status))``.
    Unlike the HTML helpers, failures are JSON errors, not redirects.
    """
    if session.get("session_mode") == "player":
        return None, (jsonify({"error": "GM session required."}), 403)
    profile = getattr(current_user, "gm_profile", None)
    if profile is None:
        return None, (jsonify({"error": "A Game Master profile is required."}), 403)
    cid = session.get("campaign_id")
    if not cid:
        return None, (jsonify({"error": "Select a campaign first."}), 400)
    campaign = Campaign.query.filter_by(id=cid, gm_profile_id=profile.id).first()
    if campaign is None:
        return None, (jsonify({"error": "Active campaign not found."}), 404)
    return campaign, None


def _canvas_for_campaign(canvas_id, campaign_id):
    if not isinstance(canvas_id, int):
        return None
    return MapCanvas.query.filter_by(id=canvas_id, campaign_id=campaign_id).first()


def _world_canvas_for_campaign(canvas_id, campaign_id):
    canvas = _canvas_for_campaign(canvas_id, campaign_id)
    if canvas is None or canvas.scope != gm_maps.WORLD_SCOPE:
        return None
    return canvas


@login_required
def get_world_map():
    campaign, err = _campaign_for_json()
    if err:
        return err
    payload = gm_maps.build_world_map_payload(campaign.id)
    db.session.commit()  # canvas may have been lazily created
    return jsonify(payload)


@login_required
def get_city_map(city_id):
    campaign, err = _campaign_for_json()
    if err:
        return err
    city = city_for_campaign_optional(city_id, campaign.id)
    if city is None:
        return jsonify({"error": "City not found in this campaign."}), 404
    payload = gm_maps.build_city_map_payload(campaign.id, city)
    db.session.commit()
    return jsonify(payload)


@login_required
def post_marker():
    campaign, err = _campaign_for_json()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    canvas_id = data.get("canvas_id")
    entity_type = data.get("entity_type")
    entity_id = data.get("entity_id")
    try:
        x = float(data.get("x"))
        y = float(data.get("y"))
    except (TypeError, ValueError):
        return jsonify({"error": "x and y must be numbers."}), 400
    if not isinstance(entity_id, int):
        return jsonify({"error": "entity_id must be an integer."}), 400

    canvas = _canvas_for_campaign(canvas_id, campaign.id)
    if canvas is None:
        return jsonify({"error": "Canvas not found in this campaign."}), 404

    try:
        marker = gm_maps.upsert_marker(
            campaign.id, canvas, entity_type, entity_id, x, y
        )
        db.session.commit()
    except MapValidationError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except LookupError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 404
    except Exception:
        db.session.rollback()
        log.exception("map_marker_upsert_failed campaign_id=%s", campaign.id)
        return jsonify({"error": "Could not save marker."}), 500

    return jsonify(
        {
            "success": True,
            "marker": {
                "id": marker.id,
                "entity_type": marker.entity_type,
                "city_id": marker.city_id,
                "shop_id": marker.shop_id,
                "x": marker.x,
                "y": marker.y,
            },
        }
    )


@login_required
def remove_marker():
    campaign, err = _campaign_for_json()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    canvas_id = data.get("canvas_id")
    entity_type = data.get("entity_type")
    entity_id = data.get("entity_id")
    if not isinstance(entity_id, int):
        return jsonify({"error": "entity_id must be an integer."}), 400

    canvas = _canvas_for_campaign(canvas_id, campaign.id)
    if canvas is None:
        return jsonify({"error": "Canvas not found in this campaign."}), 404

    try:
        removed = gm_maps.remove_marker(campaign.id, canvas, entity_type, entity_id)
        db.session.commit()
    except MapValidationError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except LookupError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 404
    except Exception:
        db.session.rollback()
        log.exception("map_marker_remove_failed campaign_id=%s", campaign.id)
        return jsonify({"error": "Could not remove marker."}), 500

    return jsonify({"success": True, "removed": removed})


@login_required
def post_poi():
    campaign, err = _campaign_for_json()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    canvas_id = data.get("canvas_id")
    poi_id = data.get("poi_id")
    try:
        x = float(data.get("x"))
        y = float(data.get("y"))
    except (TypeError, ValueError):
        return jsonify({"error": "x and y must be numbers."}), 400

    if poi_id is not None and not isinstance(poi_id, int):
        return jsonify({"error": "poi_id must be an integer."}), 400

    canvas = _world_canvas_for_campaign(canvas_id, campaign.id)
    if canvas is None:
        return jsonify({"error": "World canvas not found in this campaign."}), 404

    try:
        poi = gm_maps.upsert_poi(
            campaign.id,
            canvas,
            data.get("label") or "",
            data.get("note") or "",
            x,
            y,
            visible_to_players=bool(data.get("visible_to_players")),
            poi_id=poi_id,
        )
        db.session.commit()
    except MapValidationError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except LookupError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 404
    except Exception:
        db.session.rollback()
        log.exception("map_poi_upsert_failed campaign_id=%s", campaign.id)
        return jsonify({"error": "Could not save point of interest."}), 500

    return jsonify(
        {
            "success": True,
            "point_of_interest": {
                "id": poi.id,
                "label": poi.label,
                "note": poi.note or "",
                "x": poi.x,
                "y": poi.y,
                "visible_to_players": bool(poi.visible_to_players),
            },
        }
    )


@login_required
def remove_poi():
    campaign, err = _campaign_for_json()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    canvas_id = data.get("canvas_id")
    poi_id = data.get("poi_id")
    if not isinstance(poi_id, int):
        return jsonify({"error": "poi_id must be an integer."}), 400

    canvas = _world_canvas_for_campaign(canvas_id, campaign.id)
    if canvas is None:
        return jsonify({"error": "World canvas not found in this campaign."}), 404

    try:
        removed = gm_maps.remove_poi(campaign.id, canvas, poi_id)
        db.session.commit()
    except MapValidationError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except LookupError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 404
    except Exception:
        db.session.rollback()
        log.exception("map_poi_remove_failed campaign_id=%s", campaign.id)
        return jsonify({"error": "Could not remove point of interest."}), 500

    return jsonify({"success": True, "removed": removed})


def _apply_background_action(campaign, canvas):
    """Shared upload-or-regenerate behavior for world and city canvases."""
    file_storage = request.files.get("map_image")
    if file_storage is not None and file_storage.filename:
        try:
            gm_maps.save_map_upload(canvas, file_storage)
        except MapValidationError as exc:
            db.session.rollback()
            return jsonify({"error": str(exc)}), 400
    else:
        gm_maps.regenerate_canvas_background(canvas)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        log.exception("map_background_save_failed campaign_id=%s", campaign.id)
        return jsonify({"error": "Could not save map background."}), 500

    return jsonify(
        {
            "success": True,
            "canvas": {
                "id": canvas.id,
                "scope": canvas.scope,
                "city_id": canvas.city_id,
                "source_type": canvas.source_type,
                "has_image": bool(canvas.image_path),
                "generation": canvas.generation_json or {},
                "width": canvas.width,
                "height": canvas.height,
            },
        }
    )


@login_required
def post_world_background():
    campaign, err = _campaign_for_json()
    if err:
        return err
    canvas = gm_maps.get_or_create_world_canvas(campaign.id)
    return _apply_background_action(campaign, canvas)


@login_required
def post_city_background(city_id):
    campaign, err = _campaign_for_json()
    if err:
        return err
    city = city_for_campaign_optional(city_id, campaign.id)
    if city is None:
        return jsonify({"error": "City not found in this campaign."}), 404
    canvas = gm_maps.get_or_create_city_canvas(campaign.id, city)
    return _apply_background_action(campaign, canvas)


@login_required
def get_map_image(canvas_id):
    """Serve an uploaded map background, scoped to the owning GM's campaign."""
    campaign, err = _campaign_for_json()
    if err:
        return err
    canvas = _canvas_for_campaign(canvas_id, campaign.id)
    if canvas is None or not canvas.image_path:
        return jsonify({"error": "Map image not found."}), 404
    path = gm_maps.map_image_file(canvas.id)
    if not path.exists():
        return jsonify({"error": "Map image not found."}), 404
    # Serve from memory so no file handle stays open (Windows file locking,
    # and regenerate can delete the file while a response is in flight).
    return send_file(
        io.BytesIO(path.read_bytes()), mimetype="image/webp", max_age=0
    )
