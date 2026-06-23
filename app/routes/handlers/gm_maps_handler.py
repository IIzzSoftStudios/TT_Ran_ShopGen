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
from app.routes.handlers.gm_helpers import city_for_campaign_optional, shop_for_campaign_optional
from app.services import gm_maps
from app.services.gm_maps import MapValidationError

log = logging.getLogger(__name__)


def _campaign_for_json():
    """Resolve the active GM campaign for JSON endpoints.

    Returns ``(campaign, None)`` or ``(None, (json_response, status))``.
    Unlike the HTML helpers, failures are JSON errors, not redirects.
    """
    profile = getattr(current_user, "gm_profile", None)
    if profile is None:
        return None, (jsonify({"error": "A Game Master profile is required."}), 403)

    cid = session.get("campaign_id")
    if session.get("session_mode") == "player":
        # World-setup HTML routes are allowlisted for player mode, but the map
        # builder still calls JSON map endpoints. Promote to GM mode when the
        # active campaign is an in-progress setup owned by this GM.
        if cid:
            campaign = Campaign.query.filter_by(id=cid, gm_profile_id=profile.id).first()
            if campaign is not None:
                from app.services.world_setup_state import (
                    is_pending_setup,
                    settings_for_campaign,
                )

                if is_pending_setup(settings_for_campaign(campaign)):
                    session["session_mode"] = "gm"
                    session.modified = True
                    return campaign, None
        return None, (jsonify({"error": "GM session required."}), 403)

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
def get_shop_map(shop_id):
    campaign, err = _campaign_for_json()
    if err:
        return err
    shop = shop_for_campaign_optional(shop_id, campaign.id)
    if shop is None:
        return jsonify({"error": "Shop not found in this campaign."}), 404
    city = None
    city_id = request.args.get("city_id", type=int)
    if city_id is not None:
        city = city_for_campaign_optional(city_id, campaign.id)
        if city is None:
            return jsonify({"error": "City not found in this campaign."}), 404
        if city not in shop.cities:
            return jsonify({"error": "Shop is not linked to this city."}), 400
    payload = gm_maps.build_shop_map_payload(campaign.id, shop, city=city)
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


def _canvas_response(canvas):
    return {
        "id": canvas.id,
        "scope": canvas.scope,
        "city_id": canvas.city_id,
        "source_type": canvas.source_type,
        "has_image": bool(canvas.image_path),
        "has_underlay": bool(getattr(canvas, "underlay_path", None)),
        "generation": canvas.generation_json or {},
        "width": canvas.width,
        "height": canvas.height,
    }


def _background_json_payload():
    if request.files.get("map_image") is not None:
        return None
    if request.is_json:
        return request.get_json(silent=True) or {}
    content_type = (request.content_type or "").lower()
    if "application/json" in content_type:
        return request.get_json(silent=True) or {}
    return None


def _regen_blocked_response(canvas, json_payload):
    """Return 409 when studio edits would be discarded without confirmation."""
    if json_payload is None:
        json_payload = {}
    if json_payload.get("confirm_discard_edits"):
        return None
    generation = canvas.generation_json or {}
    if gm_maps.canvas_has_studio_edits(generation):
        return (
            jsonify(
                {
                    "error": (
                        "Map studio edits would be discarded. "
                        "Save your map or send confirm_discard_edits: true."
                    )
                }
            ),
            409,
        )
    return None


def _apply_background_action(campaign, canvas):
    """Shared upload-or-regenerate behavior for world and city canvases."""
    file_storage = request.files.get("map_image")
    if file_storage is not None and file_storage.filename:
        json_payload = _background_json_payload()
        blocked = _regen_blocked_response(canvas, json_payload or {})
        if blocked:
            return blocked
        try:
            gm_maps.save_map_upload(canvas, file_storage)
        except MapValidationError as exc:
            db.session.rollback()
            return jsonify({"error": str(exc)}), 400
    else:
        json_payload = _background_json_payload()
        blocked = _regen_blocked_response(canvas, json_payload)
        if blocked:
            return blocked
        try:
            if json_payload is not None:
                opts = gm_maps.parse_background_request(json_payload, canvas)
                gm_maps.regenerate_canvas_background(
                    canvas,
                    mode=opts["mode"],
                    layout_seed=opts["layout_seed"],
                    detail_seed=opts["detail_seed"],
                    profile_overrides=opts["profile_overrides"],
                    style_preset=opts["style_preset"],
                )
            else:
                gm_maps.regenerate_canvas_background(canvas, mode="full")
        except MapValidationError as exc:
            db.session.rollback()
            return jsonify({"error": str(exc)}), 400

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        log.exception("map_background_save_failed campaign_id=%s", campaign.id)
        return jsonify({"error": "Could not save map background."}), 500

    return jsonify(
        {
            "success": True,
            "canvas": _canvas_response(canvas),
        }
    )


def _preview_background_action(campaign, canvas):
    """Preview-only generation — no DB writes."""
    try:
        json_payload = _background_json_payload() or {}
        generation = gm_maps.build_background_preview(canvas, campaign.id, json_payload)
    except MapValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"success": True, "generation": generation})


def _canvas_for_preview(campaign_id, scope, city_id=None, shop_id=None):
    query = MapCanvas.query.filter_by(campaign_id=campaign_id, scope=scope)
    if city_id is not None:
        query = query.filter_by(city_id=city_id)
    if shop_id is not None:
        query = query.filter_by(shop_id=shop_id)
    canvas = query.first()
    if canvas is not None:
        return canvas
    return MapCanvas(
        campaign_id=campaign_id,
        scope=scope,
        city_id=city_id,
        shop_id=shop_id,
        generation_json={},
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
def post_shop_background(shop_id):
    campaign, err = _campaign_for_json()
    if err:
        return err
    shop = shop_for_campaign_optional(shop_id, campaign.id)
    if shop is None:
        return jsonify({"error": "Shop not found in this campaign."}), 404
    canvas = gm_maps.get_or_create_shop_canvas(campaign.id, shop)
    return _apply_background_action(campaign, canvas)


@login_required
def post_world_background_preview():
    campaign, err = _campaign_for_json()
    if err:
        return err
    canvas = _canvas_for_preview(campaign.id, gm_maps.WORLD_SCOPE)
    return _preview_background_action(campaign, canvas)


@login_required
def post_city_background_preview(city_id):
    campaign, err = _campaign_for_json()
    if err:
        return err
    city = city_for_campaign_optional(city_id, campaign.id)
    if city is None:
        return jsonify({"error": "City not found in this campaign."}), 404
    canvas = _canvas_for_preview(campaign.id, gm_maps.CITY_SCOPE, city_id=city.city_id)
    return _preview_background_action(campaign, canvas)


@login_required
def post_shop_background_preview(shop_id):
    campaign, err = _campaign_for_json()
    if err:
        return err
    shop = shop_for_campaign_optional(shop_id, campaign.id)
    if shop is None:
        return jsonify({"error": "Shop not found in this campaign."}), 404
    canvas = _canvas_for_preview(
        campaign.id, gm_maps.SHOP_SCOPE, shop_id=shop.shop_id
    )
    return _preview_background_action(campaign, canvas)


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


@login_required
def post_world_generation():
    campaign, err = _campaign_for_json()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    generation = data.get("generation")
    if not isinstance(generation, dict):
        return jsonify({"error": "generation must be an object."}), 400
    canvas = gm_maps.get_or_create_world_canvas(campaign.id)
    if canvas.source_type == "uploaded" and not data.get("convert_from_upload"):
        return jsonify(
            {
                "error": (
                    "Canvas uses an uploaded background. "
                    "Send convert_from_upload: true to switch to an editable map."
                )
            }
        ), 400
    try:
        gm_maps.save_canvas_generation(
            canvas,
            generation,
            convert_from_upload=bool(data.get("convert_from_upload")),
        )
        db.session.commit()
    except MapValidationError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception:
        db.session.rollback()
        log.exception("map_generation_save_failed campaign_id=%s", campaign.id)
        return jsonify({"error": "Could not save map generation."}), 500
    return jsonify({"success": True, "canvas": _canvas_response(canvas)})


@login_required
def post_city_generation(city_id):
    campaign, err = _campaign_for_json()
    if err:
        return err
    city = city_for_campaign_optional(city_id, campaign.id)
    if city is None:
        return jsonify({"error": "City not found in this campaign."}), 404
    data = request.get_json(silent=True) or {}
    generation = data.get("generation")
    if not isinstance(generation, dict):
        return jsonify({"error": "generation must be an object."}), 400
    canvas = gm_maps.get_or_create_city_canvas(campaign.id, city)
    if canvas.source_type == "uploaded" and not data.get("convert_from_upload"):
        return jsonify(
            {
                "error": (
                    "Canvas uses an uploaded background. "
                    "Send convert_from_upload: true to switch to an editable map."
                )
            }
        ), 400
    try:
        gm_maps.save_canvas_generation(
            canvas,
            generation,
            convert_from_upload=bool(data.get("convert_from_upload")),
        )
        db.session.commit()
    except MapValidationError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception:
        db.session.rollback()
        log.exception("map_generation_save_failed campaign_id=%s", campaign.id)
        return jsonify({"error": "Could not save map generation."}), 500
    return jsonify({"success": True, "canvas": _canvas_response(canvas)})


@login_required
def post_world_convert_editable():
    campaign, err = _campaign_for_json()
    if err:
        return err
    canvas = gm_maps.get_or_create_world_canvas(campaign.id)
    try:
        gm_maps.convert_canvas_to_editable(canvas)
        db.session.commit()
    except MapValidationError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception:
        db.session.rollback()
        log.exception("map_convert_editable_failed campaign_id=%s", campaign.id)
        return jsonify({"error": "Could not convert map to editable."}), 500
    return jsonify({"success": True, "canvas": _canvas_response(canvas)})


@login_required
def post_city_convert_editable(city_id):
    campaign, err = _campaign_for_json()
    if err:
        return err
    city = city_for_campaign_optional(city_id, campaign.id)
    if city is None:
        return jsonify({"error": "City not found in this campaign."}), 404
    canvas = gm_maps.get_or_create_city_canvas(campaign.id, city)
    try:
        gm_maps.convert_canvas_to_editable(canvas)
        db.session.commit()
    except MapValidationError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception:
        db.session.rollback()
        log.exception("map_convert_editable_failed campaign_id=%s", campaign.id)
        return jsonify({"error": "Could not convert map to editable."}), 500
    return jsonify({"success": True, "canvas": _canvas_response(canvas)})


def _apply_underlay_upload(campaign, canvas):
    file_storage = request.files.get("map_image")
    if file_storage is None or not file_storage.filename:
        return jsonify({"error": "map_image file is required."}), 400
    try:
        gm_maps.save_map_underlay(canvas, file_storage)
        db.session.commit()
    except MapValidationError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception:
        db.session.rollback()
        log.exception("map_underlay_save_failed campaign_id=%s", campaign.id)
        return jsonify({"error": "Could not save trace underlay."}), 500
    return jsonify({"success": True, "canvas": _canvas_response(canvas)})


@login_required
def post_world_underlay():
    campaign, err = _campaign_for_json()
    if err:
        return err
    canvas = gm_maps.get_or_create_world_canvas(campaign.id)
    return _apply_underlay_upload(campaign, canvas)


@login_required
def post_city_underlay(city_id):
    campaign, err = _campaign_for_json()
    if err:
        return err
    city = city_for_campaign_optional(city_id, campaign.id)
    if city is None:
        return jsonify({"error": "City not found in this campaign."}), 404
    canvas = gm_maps.get_or_create_city_canvas(campaign.id, city)
    return _apply_underlay_upload(campaign, canvas)


def _apply_underlay_delete(campaign, canvas):
    try:
        gm_maps.delete_map_underlay(canvas)
        db.session.commit()
    except Exception:
        db.session.rollback()
        log.exception("map_underlay_delete_failed campaign_id=%s", campaign.id)
        return jsonify({"error": "Could not remove trace underlay."}), 500
    return jsonify({"success": True, "canvas": _canvas_response(canvas)})


@login_required
def delete_world_underlay():
    campaign, err = _campaign_for_json()
    if err:
        return err
    canvas = gm_maps.get_or_create_world_canvas(campaign.id)
    return _apply_underlay_delete(campaign, canvas)


@login_required
def delete_city_underlay(city_id):
    campaign, err = _campaign_for_json()
    if err:
        return err
    city = city_for_campaign_optional(city_id, campaign.id)
    if city is None:
        return jsonify({"error": "City not found in this campaign."}), 404
    canvas = gm_maps.get_or_create_city_canvas(campaign.id, city)
    return _apply_underlay_delete(campaign, canvas)


@login_required
def get_map_underlay(canvas_id):
    """Serve a GM trace underlay image scoped to the owning campaign."""
    campaign, err = _campaign_for_json()
    if err:
        return err
    canvas = _canvas_for_campaign(canvas_id, campaign.id)
    if canvas is None or not getattr(canvas, "underlay_path", None):
        return jsonify({"error": "Map underlay not found."}), 404
    path = gm_maps.map_underlay_file(canvas.id)
    if not path.exists():
        return jsonify({"error": "Map underlay not found."}), 404
    return send_file(
        io.BytesIO(path.read_bytes()), mimetype="image/webp", max_age=0
    )


def _apply_generation_regen(canvas, campaign, data):
    mode = gm_maps.validate_partial_regen_mode(data.get("mode"))
    profile_overrides = data.get("profile")
    if profile_overrides is not None:
        if not isinstance(profile_overrides, dict):
            raise MapValidationError("profile must be an object.")
        profile_overrides = {
            k: gm_maps._clamp_profile_value(k, v)
            for k, v in profile_overrides.items()
            if k in gm_maps.PROFILE_CLAMP_KEYS
        }
    if data.get("cell_graph") and isinstance(data["cell_graph"], dict):
        generation = dict(canvas.generation_json or {})
        generation["cell_graph"] = data["cell_graph"]
        canvas.generation_json = generation
    gm_maps.apply_partial_regen(
        canvas,
        mode,
        settings=gm_maps._settings_for_campaign(campaign.id),
        profile_overrides=profile_overrides,
    )
    db.session.commit()
    return jsonify({"success": True, "canvas": _canvas_response(canvas)})


@login_required
def post_world_generation_regen():
    campaign, err = _campaign_for_json()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    canvas = gm_maps.get_or_create_world_canvas(campaign.id)
    try:
        return _apply_generation_regen(canvas, campaign, data)
    except MapValidationError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception:
        db.session.rollback()
        log.exception("map_generation_regen_failed campaign_id=%s", campaign.id)
        return jsonify({"error": "Could not regenerate map."}), 500


@login_required
def post_city_generation_regen(city_id):
    campaign, err = _campaign_for_json()
    if err:
        return err
    city = city_for_campaign_optional(city_id, campaign.id)
    if city is None:
        return jsonify({"error": "City not found in this campaign."}), 404
    data = request.get_json(silent=True) or {}
    canvas = gm_maps.get_or_create_city_canvas(campaign.id, city)
    try:
        return _apply_generation_regen(canvas, campaign, data)
    except MapValidationError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception:
        db.session.rollback()
        log.exception("map_generation_regen_failed campaign_id=%s", campaign.id)
        return jsonify({"error": "Could not regenerate map."}), 500
