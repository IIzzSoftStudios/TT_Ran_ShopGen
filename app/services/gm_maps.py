"""GM interactive map service: canvases, markers, uploads, generation.

GM presentation/editor state only. This module is never imported by the
simulation tick path (`SimulationEngine.run_tick`) and must stay that way.

Transaction discipline: functions here add/flush but never commit. The
route layer owns ``db.session.commit()`` / ``rollback()``, matching the
world-generator convention.

Authorization discipline: callers (routes) derive the active campaign from
the GM session. Functions re-validate that every entity (canvas, city,
shop) belongs to that campaign before any write.
"""

from __future__ import annotations

import io
import json
import logging
import math
import os
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from flask import current_app
from PIL import Image

from app.extensions import db
from app.models import (
    BattleEncounter,
    CampaignWorldConfig,
    City,
    Item,
    MapCanvas,
    MapMarker,
    MapPointOfInterest,
    Player,
    Region,
    Shop,
    ShopInventory,
)
from app.services import species_compendium_service
from app.services.map_generation.pipeline import (
    build_generation_from_cell_graph,
    generate_map,
    migrate_v5_to_v6,
    partial_regen,
)
from app.services.map_generation.hex_bake import bake_terrain_grid, bake_dimensions, hex_grid_from_terrain_grid
from app.services.map_generation.hex_generate import (
    CITY_DEFAULT_HEX_HEIGHT,
    CITY_DEFAULT_HEX_SIZE,
    CITY_DEFAULT_HEX_WIDTH,
    generate_city_hex_grid,
    generate_shop_hex_grid,
    generate_world_hex_grid,
)
from app.services.map_generation.hex_pipeline import build_generation_from_hex_grid
from app.services.map_generation import hex_grid as hex_grid_mod
from app.services.map_generation import raster_import

log = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 4 * 1024 * 1024  # 4 MB raw upload ceiling
MAX_MAP_EDGE = 2048  # uploaded backgrounds are bounded to this edge
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}

WORLD_SCOPE = "world"
CITY_SCOPE = "city"
SHOP_SCOPE = "shop"

GENERATION_SCHEMA_VERSION = 7
LEGACY_SCHEMA_REGEN_BELOW = 4  # v4 canvases are not auto-regenerated on GET
V6_SCHEMA_VERSION = 6
V7_SCHEMA_VERSION = 7
MAX_CELL_GRAPH_SITES = 250
MAX_HEX_GRID_WIDTH = 500
MAX_HEX_GRID_HEIGHT = 500
MAX_HEX_GRID_CELLS = MAX_HEX_GRID_WIDTH * MAX_HEX_GRID_HEIGHT
LAND_FORM_OPTIONS = frozenset({"large_continents", "archipelago", "scattered"})

TERRAIN_GRID_WIDTH = 256
TERRAIN_GRID_HEIGHT = 192
MAX_TERRAIN_GRID_WIDTH = 2048
MAX_TERRAIN_GRID_HEIGHT = 1536
MAX_TERRAIN_GRID_CELLS = MAX_TERRAIN_GRID_WIDTH * MAX_TERRAIN_GRID_HEIGHT
MAX_GENERATION_JSON_BYTES = 3 * 1024 * 1024
MAX_MAP_FEATURES = 500
TERRAIN_CELL_MAX = 6

WORLD_FEATURE_TYPES = frozenset(
    {
        "landmass",
        "island",
        "mountain_range",
        "river",
        "trade_route",
        "road",
        "railroad",
        "forest",
        "grassland",
        "hill",
        "region_tint",
        "lake",
    }
)
CITY_FEATURE_TYPES = frozenset(
    {
        "city_wall",
        "district",
        "road",
        "railroad",
        "canal",
        "plaza",
        "park",
    }
)
GM_DRAWN_LINE_TYPES = frozenset({"river", "trade_route", "road", "railroad", "canal"})

MAP_STYLE_PRESETS = frozenset(
    {"parchment_atlas", "satellite", "dark_fantasy", "ink_sketch"}
)
MAP_REGEN_MODES = frozenset({"layout", "details", "full"})
LEGACY_PALETTE_TO_STYLE = {
    "parchment": "parchment_atlas",
    "verdant": "parchment_atlas",
    "ashen": "dark_fantasy",
    "slate": "satellite",
    "sandstone": "parchment_atlas",
    "timber": "ink_sketch",
}
PROFILE_CLAMP_KEYS = (
    "landmass_scale",
    "waterways",
    "terrain_roughness",
    "coast_detail",
    "island_count",
    "biome_warmth",
    "region_density",
    "city_density",
    "economy_density",
    "city_complexity",
    "tech_magic_balance",
    "wind_direction",
    "moisture_strength",
    "land_frequency",
    "vegetation_frequency",
    "grassland_frequency",
    "hills_frequency",
    "desert_frequency",
    "mountain_frequency",
    "swamp_frequency",
    "cluster_percent",
    "hex_width",
    "hex_height",
    "hex_size",
)

MAP_PARTIAL_REGEN_MODES = frozenset(
    {"tectonics", "climate", "hydrology", "layout", "details", "full"}
)


class MapValidationError(ValueError):
    """Raised when map input fails validation (bad coords, scope, file)."""


# ---------------------------------------------------------------------------
# Upload storage
# ---------------------------------------------------------------------------
def map_upload_dir() -> Path:
    root = Path(current_app.root_path).parent
    path = root / "uploads" / "maps"
    path.mkdir(parents=True, exist_ok=True)
    return path


def map_image_file(canvas_id: int) -> Path:
    return map_upload_dir() / f"{canvas_id}.webp"


def map_underlay_file(canvas_id: int) -> Path:
    return map_upload_dir() / f"{canvas_id}_underlay.webp"


def save_map_upload(canvas: MapCanvas, file_storage) -> None:
    """Validate, bound, and persist an uploaded background as WebP.

    Mirrors the avatar pipeline (`app/services/user_avatar.py`) but with a
    larger size budget appropriate for map art. Mutates the canvas row;
    caller commits.
    """
    img = _validate_image_upload(file_storage)
    img.thumbnail((MAX_MAP_EDGE, MAX_MAP_EDGE), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="WEBP", quality=85)

    target = map_image_file(canvas.id)
    target.write_bytes(out.getvalue())

    canvas.source_type = "uploaded"
    canvas.image_path = target.name
    canvas.width = img.width
    canvas.height = img.height


def delete_map_image(canvas) -> None:
    """Best-effort removal of a canvas's uploaded image file.

    A stale file is harmless once `image_path` is cleared (Windows can hold
    handles open briefly), so never fail the request over it.
    """
    canvas_id = canvas if isinstance(canvas, int) else canvas.id
    path = map_image_file(canvas_id)
    try:
        if path.exists():
            path.unlink()
    except OSError:
        log.warning("map_image_delete_deferred path=%s", path)


def _validate_image_upload(file_storage) -> Image.Image:
    """Shared decode/validate path for map and underlay uploads."""
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    if size > MAX_UPLOAD_BYTES:
        raise MapValidationError("File exceeds max 4 MB allowed size.")
    file_storage.stream.seek(0)

    Image.MAX_IMAGE_PIXELS = 32_000_000
    try:
        img = Image.open(file_storage.stream)
        img_format = img.format
    except Exception as exc:
        raise MapValidationError("File is not a readable image.") from exc
    if img_format not in ALLOWED_FORMATS:
        raise MapValidationError("Unsupported image format. Use PNG, JPEG, WebP, or GIF.")
    return img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB")


def save_map_underlay(canvas: MapCanvas, file_storage) -> None:
    """Persist a trace underlay without changing background source_type."""
    img = _validate_image_upload(file_storage)
    img.thumbnail((MAX_MAP_EDGE, MAX_MAP_EDGE), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="WEBP", quality=85)
    target = map_underlay_file(canvas.id)
    target.write_bytes(out.getvalue())
    canvas.underlay_path = target.name


def delete_map_underlay(canvas: MapCanvas) -> None:
    """Remove trace underlay file and clear canvas.underlay_path."""
    if canvas.underlay_path:
        path = map_underlay_file(canvas.id)
        try:
            if path.exists():
                path.unlink()
        except OSError:
            log.warning("map_underlay_delete_deferred path=%s", path)
    canvas.underlay_path = None


# ---------------------------------------------------------------------------
# Map studio: terrain grid + generation_json v5
# ---------------------------------------------------------------------------
def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def empty_terrain_grid(width: int = TERRAIN_GRID_WIDTH, height: int = TERRAIN_GRID_HEIGHT) -> dict:
    return {
        "width": width,
        "height": height,
        "encoding": "rle",
        "cells": encode_terrain_rle([0] * (width * height)),
    }


def encode_terrain_rle(cells: list[int]) -> str:
    if not cells:
        return "0:0"
    parts: list[str] = []
    current = int(cells[0])
    count = 1
    for value in cells[1:]:
        value = int(value)
        if value == current and count < 1_000_000:
            count += 1
        else:
            parts.append(f"{current}:{count}")
            current = value
            count = 1
    parts.append(f"{current}:{count}")
    return ",".join(parts)


def decode_terrain_rle(cells_spec: str, expected_len: int) -> list[int]:
    if not isinstance(cells_spec, str) or not cells_spec.strip():
        raise MapValidationError("terrain_grid.cells must be a non-empty RLE string.")
    out: list[int] = []
    for segment in cells_spec.split(","):
        segment = segment.strip()
        if not segment:
            continue
        if ":" not in segment:
            raise MapValidationError("Invalid terrain_grid RLE segment.")
        code_s, count_s = segment.split(":", 1)
        try:
            code = int(code_s)
            count = int(count_s)
        except ValueError as exc:
            raise MapValidationError("Invalid terrain_grid RLE segment.") from exc
        if code < 0 or code > TERRAIN_CELL_MAX or count < 0:
            raise MapValidationError("terrain_grid RLE values out of range.")
        out.extend([code] * count)
    if len(out) != expected_len:
        raise MapValidationError(
            f"terrain_grid RLE length {len(out)} does not match width*height ({expected_len})."
        )
    return out


def _point_in_polygon(x: float, y: float, polygon: list[list[float]]) -> bool:
    if len(polygon) < 3:
        return False
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        xi, yi = float(polygon[i][0]), float(polygon[i][1])
        xj, yj = float(polygon[j][0]), float(polygon[j][1])
        intersect = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi
        )
        if intersect:
            inside = not inside
        j = i
    return inside


def _feature_to_grid_code(feature_type: str, scope: str) -> int | None:
    if scope == WORLD_SCOPE:
        if feature_type in ("landmass", "island"):
            return 1
        if feature_type == "hill":
            return 6
        if feature_type == "mountain_range":
            return 2
        if feature_type == "forest":
            return 3
        if feature_type == "grassland":
            return 5
        if feature_type == "lake":
            return 0
        return None
    if feature_type == "district":
        return 1
    if feature_type in ("canal",):
        return 2
    if feature_type == "park":
        return 3
    if feature_type == "road":
        return 4
    if feature_type == "city_wall":
        return 1
    return None


def initialize_terrain_grid_from_features(generation: dict) -> dict:
    """Bootstrap terrain_grid from existing vector polygons (v4 → v5 lazy upgrade)."""
    scope = generation.get("scope") or WORLD_SCOPE
    width = TERRAIN_GRID_WIDTH
    height = TERRAIN_GRID_HEIGHT
    cells = [0] * (width * height)
    features = generation.get("features") or []
    for gy in range(height):
        ny = (gy + 0.5) / height
        for gx in range(width):
            nx = (gx + 0.5) / width
            for feature in features:
                ftype = feature.get("type")
                code = _feature_to_grid_code(ftype, scope)
                if code is None:
                    continue
                points = feature.get("points")
                if points and _point_in_polygon(nx, ny, points):
                    cells[gy * width + gx] = code
                    break
    upgraded = dict(generation)
    upgraded["schema_version"] = GENERATION_SCHEMA_VERSION
    upgraded["terrain_grid"] = {
        "width": width,
        "height": height,
        "encoding": "rle",
        "cells": encode_terrain_rle(cells),
    }
    meta = dict(upgraded.get("editor_meta") or {})
    if not meta.get("grid_initialized_from"):
        meta["grid_initialized_from"] = "procedural_v4"
    upgraded["editor_meta"] = meta
    return upgraded


def ensure_studio_ready_generation(
    generation: dict | None,
    scope: str,
    profile: dict | None = None,
) -> dict:
    """Return a v7 generation dict with hex_grid (world, city, shop)."""
    gen = dict(generation or {})
    gen["scope"] = gen.get("scope") or scope
    schema = int(gen.get("schema_version") or 0)
    if schema < 5:
        gen = initialize_terrain_grid_from_features(gen)
        schema = int(gen.get("schema_version") or 0)
    if schema < V6_SCHEMA_VERSION:
        layout, detail = _resolve_seeds_from_generation(gen)
        prof = profile or gen.get("profile") or map_generation_profile(None)
        cell_graph = migrate_v5_to_v6(
            gen,
            scope,
            prof,
            layout,
            detail,
            decode_terrain_rle,
            encode_terrain_rle,
        )
        style = gen.get("style_preset") or gen.get("palette") or "parchment_atlas"
        gen = build_generation_from_cell_graph(
            cell_graph,
            scope,
            layout,
            detail,
            prof,
            validate_style_preset(style),
            gen.get("render_palette") or style_render_palette(style, prof.get("biome_warmth", 5.0)),
            encode_terrain_rle,
        )
        meta = dict(gen.get("editor_meta") or {})
        meta["migrated_from_v5"] = True
        gen["editor_meta"] = meta
        schema = int(gen.get("schema_version") or 0)
    if scope == WORLD_SCOPE and schema < V7_SCHEMA_VERSION:
        gen = _migrate_world_to_v7(gen, scope, profile)
    elif scope == CITY_SCOPE and schema < V7_SCHEMA_VERSION:
        gen = _migrate_city_to_v7(gen, profile)
    elif scope == SHOP_SCOPE and schema < V7_SCHEMA_VERSION:
        gen = _migrate_shop_to_v7(gen, profile)
    elif scope != WORLD_SCOPE and schema < V7_SCHEMA_VERSION:
        gen["schema_version"] = V7_SCHEMA_VERSION
    if not gen.get("terrain_grid"):
        gen["terrain_grid"] = empty_terrain_grid()
    if scope in (WORLD_SCOPE, CITY_SCOPE, SHOP_SCOPE):
        if gen.get("hex_grid"):
            gen = _finalize_hex_grid_derivation(gen, scope)
    elif gen.get("cell_graph"):
        gen = _refresh_terrain_grid_from_cell_graph(gen, scope)
    return gen


def canvas_has_studio_edits(generation: dict | None) -> bool:
    meta = (generation or {}).get("editor_meta") or {}
    return bool(meta.get("last_edited_at"))


def _validate_point(pt) -> list[float]:
    if not isinstance(pt, (list, tuple)) or len(pt) < 2:
        raise MapValidationError("Feature points must be [x, y] pairs.")
    try:
        x = float(pt[0])
        y = float(pt[1])
    except (TypeError, ValueError) as exc:
        raise MapValidationError("Feature coordinates must be numbers.") from exc
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        raise MapValidationError("Feature coordinates must be between 0 and 1.")
    return [round(x, 4), round(y, 4)]


def _validate_feature(feature: dict, scope: str) -> dict:
    if not isinstance(feature, dict):
        raise MapValidationError("Each feature must be an object.")
    ftype = feature.get("type")
    allowed = WORLD_FEATURE_TYPES if scope == WORLD_SCOPE else CITY_FEATURE_TYPES
    if ftype not in allowed:
        raise MapValidationError(f"Unsupported feature type: {ftype}")
    out: dict = {"type": ftype}
    if ftype == "plaza":
        pt = _validate_point([feature.get("x"), feature.get("y")])
        out["x"] = pt[0]
        out["y"] = pt[1]
        try:
            out["size"] = max(0.01, min(0.25, float(feature.get("size", 0.05))))
        except (TypeError, ValueError) as exc:
            raise MapValidationError("plaza.size must be a number.") from exc
    else:
        points = feature.get("points")
        min_pts = 2
        if ftype == "region_tint" and feature.get("region_id") is not None:
            min_pts = 3
        if not isinstance(points, list) or len(points) < min_pts:
            raise MapValidationError(f"{ftype} requires at least {min_pts} points.")
        out["points"] = [_validate_point(p) for p in points]
    if ftype == "district" and feature.get("label"):
        out["label"] = str(feature["label"])[:80]
    if ftype == "region_tint":
        if feature.get("label"):
            out["label"] = str(feature["label"])[:80]
        if feature.get("region_id") is not None:
            try:
                out["region_id"] = int(feature["region_id"])
            except (TypeError, ValueError) as exc:
                raise MapValidationError("region_tint.region_id must be an integer.") from exc
        for color_key in ("main_color", "secondary_color"):
            raw_color = feature.get(color_key)
            if raw_color:
                cleaned = str(raw_color).strip()
                if re.fullmatch(r"#[0-9A-Fa-f]{6}", cleaned):
                    out[color_key] = cleaned.lower()
    if ftype == "mountain_range" and feature.get("peak_scale"):
        scales = feature["peak_scale"]
        if isinstance(scales, list):
            out["peak_scale"] = [round(float(s), 3) for s in scales[: len(out.get("points", []))]]
    if feature.get("gm_drawn") is True:
        out["gm_drawn"] = True
    return out


def _validate_cell_graph(cell_graph: dict, scope: str) -> dict:
    if not isinstance(cell_graph, dict):
        raise MapValidationError("cell_graph must be an object.")
    sites = cell_graph.get("sites")
    if not isinstance(sites, list) or len(sites) > MAX_CELL_GRAPH_SITES:
        raise MapValidationError("cell_graph.sites invalid or exceeds maximum.")
    out_sites = [_validate_point(p) for p in sites]
    cells_in = cell_graph.get("cells")
    if not isinstance(cells_in, list):
        raise MapValidationError("cell_graph.cells must be an array.")
    cells_out: list[dict] = []
    for cell in cells_in:
        if not isinstance(cell, dict):
            raise MapValidationError("Each cell must be an object.")
        cid = int(cell.get("id", len(cells_out)))
        poly = cell.get("polygon")
        if not isinstance(poly, list) or len(poly) < 3:
            raise MapValidationError("Each cell requires a polygon with 3+ points.")
        centroid = cell.get("centroid")
        if not isinstance(centroid, (list, tuple)) or len(centroid) < 2:
            centroid = _validate_point([poly[0][0], poly[0][1]])
        else:
            centroid = _validate_point(centroid)
        cells_out.append({
            "id": cid,
            "polygon": [_validate_point(p) for p in poly[:12]],
            "centroid": centroid,
            "elevation": round(max(0.0, min(1.0, float(cell.get("elevation", 0)))), 4),
            "moisture": round(max(0.0, min(1.0, float(cell.get("moisture", 0.5)))), 4),
            "biome": str(cell.get("biome", "land"))[:32],
            "terrain_code": max(0, min(TERRAIN_CELL_MAX, int(cell.get("terrain_code", 1)))),
            "label": str(cell.get("label", ""))[:80],
        })
    adjacency = cell_graph.get("adjacency")
    if adjacency is not None:
        if not isinstance(adjacency, list):
            raise MapValidationError("cell_graph.adjacency must be an array.")
        adjacency = [
            sorted({int(n) for n in (row or []) if int(n) >= 0})
            for row in adjacency
        ]
    tectonic_lines = []
    for line in cell_graph.get("tectonic_lines") or []:
        if not isinstance(line, dict):
            continue
        pts = line.get("points")
        if isinstance(pts, list) and len(pts) >= 2:
            tectonic_lines.append({
                "id": str(line.get("id", f"t{len(tectonic_lines)}"))[:16],
                "points": [_validate_point(p) for p in pts],
                "strength": round(max(0.0, min(1.0, float(line.get("strength", 1.0)))), 3),
            })
    wind = cell_graph.get("wind_vector")
    if isinstance(wind, (list, tuple)) and len(wind) >= 2:
        wind_vector = [round(float(wind[0]), 4), round(float(wind[1]), 4)]
    else:
        wind_vector = [1.0, 0.0]
    rivers_out = []
    for river in cell_graph.get("rivers") or []:
        if not isinstance(river, dict):
            continue
        path = river.get("cell_path")
        if isinstance(path, list) and len(path) >= 2:
            rivers_out.append({
                "id": str(river.get("id", f"r{len(rivers_out)}"))[:16],
                "cell_path": [int(c) for c in path],
                "tributaries": list(river.get("tributaries") or []),
            })
    out: dict = {
        "site_count": len(out_sites),
        "sites": out_sites,
        "cells": cells_out,
        "adjacency": adjacency or [],
        "tectonic_lines": tectonic_lines,
        "wind_vector": wind_vector,
        "rivers": rivers_out,
    }
    if cell_graph.get("landmass_polygon"):
        out["landmass_polygon"] = [
            _validate_point(p) for p in cell_graph["landmass_polygon"]
        ]
    if cell_graph.get("trade_route_paths"):
        routes = []
        for route in cell_graph["trade_route_paths"]:
            if isinstance(route, dict) and route.get("points"):
                routes.append({
                    "points": [_validate_point(p) for p in route["points"]],
                    "cell_path": [int(c) for c in (route.get("cell_path") or [])],
                })
        out["trade_route_paths"] = routes
    return out


def _validate_hex_grid(hex_grid: dict) -> dict:
    if not isinstance(hex_grid, dict):
        raise MapValidationError("hex_grid must be an object.")
    width = int(hex_grid.get("width", hex_grid_mod.DEFAULT_HEX_WIDTH))
    height = int(hex_grid.get("height", hex_grid_mod.DEFAULT_HEX_HEIGHT))
    if width < 8 or height < 8 or width > MAX_HEX_GRID_WIDTH or height > MAX_HEX_GRID_HEIGHT:
        raise MapValidationError("hex_grid dimensions out of allowed range.")
    if width * height > MAX_HEX_GRID_CELLS:
        raise MapValidationError("hex_grid exceeds maximum cell count.")
    if hex_grid.get("encoding") != "rle":
        raise MapValidationError("hex_grid.encoding must be 'rle'.")
    cells = decode_terrain_rle(str(hex_grid.get("cells", "")), width * height)
    if any(c < 0 or c > TERRAIN_CELL_MAX for c in cells):
        raise MapValidationError("hex_grid contains invalid cell codes.")
    hex_size = float(hex_grid.get("hex_size", hex_grid_mod.DEFAULT_HEX_SIZE))
    coord_space = str(hex_grid.get("coordinate_space") or "world").strip().lower()
    if coord_space == "norm":
        hex_size = max(0.012, min(0.06, hex_size))
    else:
        if hex_size < 1.0:
            hex_size = hex_grid_mod.DEFAULT_HEX_SIZE
        hex_size = max(6.0, min(24.0, hex_size))
    origin = hex_grid.get("origin")
    if isinstance(origin, (list, tuple)) and len(origin) >= 2:
        origin_out = [round(float(origin[0]), 5), round(float(origin[1]), 5)]
    else:
        ox, oy = hex_grid_mod.grid_origin(hex_size, width, height)
        origin_out = [round(ox, 5), round(oy, 5)]
    out = {
        "orientation": "flat",
        "coordinate_space": coord_space if coord_space in ("norm", "world") else "world",
        "width": width,
        "height": height,
        "hex_size": round(hex_size, 5),
        "origin": origin_out,
        "encoding": "rle",
        "cells": encode_terrain_rle(cells),
    }
    wall = hex_grid.get("city_wall_polygon")
    if isinstance(wall, list) and len(wall) >= 3:
        out["city_wall_polygon"] = [_validate_point(p) for p in wall]
    return out


def _finalize_hex_grid_derivation(out: dict, scope: str) -> dict:
    """Re-bake terrain_grid and features from validated hex_grid."""
    from app.services.map_generation.hex_features import (
        derive_city_features_from_hex_grid,
        derive_features_from_hex_grid,
        derive_shop_features_from_hex_grid,
    )

    if scope not in (WORLD_SCOPE, CITY_SCOPE, SHOP_SCOPE):
        return out
    hg = out.get("hex_grid") or {}
    profile = out.get("profile") or map_generation_profile(None)
    out["terrain_grid"] = bake_terrain_grid(
        hg,
        *bake_dimensions(hg),
        encode_terrain_rle,
        decode_terrain_rle,
        city_scope=(scope in (CITY_SCOPE, SHOP_SCOPE)),
    )
    preserved = [
        f for f in (out.get("features") or [])
        if f.get("type") in ("lake", "plaza")
        or (
            f.get("type") == "region_tint"
            and f.get("region_id") is not None
        )
        or (
            f.get("type") in GM_DRAWN_LINE_TYPES
            and f.get("gm_drawn") is True
        )
    ]
    gm_lines = [f for f in preserved if f.get("type") in GM_DRAWN_LINE_TYPES]
    if scope == CITY_SCOPE:
        out["features"] = derive_city_features_from_hex_grid(hg, profile, decode_terrain_rle)
    elif scope == SHOP_SCOPE:
        out["features"] = derive_shop_features_from_hex_grid(hg, profile, decode_terrain_rle)
    else:
        lakes = [f for f in preserved if f.get("type") == "lake"]
        gm_regions = [f for f in preserved if f.get("type") == "region_tint"]
        out["features"] = derive_features_from_hex_grid(hg, profile, decode_terrain_rle)
        if lakes:
            out["features"] = list(out["features"]) + lakes
        if gm_regions:
            out["features"] = list(out["features"]) + gm_regions
    if gm_lines:
        out["features"] = list(out.get("features") or []) + gm_lines
    if scope == CITY_SCOPE and preserved:
        plazas = [f for f in preserved if f.get("type") == "plaza"]
        if plazas:
            out["features"] = list(out.get("features") or []) + plazas
    return out


def _migrate_world_to_v7(
    generation: dict,
    scope: str,
    profile: dict | None,
) -> dict:
    layout, detail = _resolve_seeds_from_generation(generation)
    prof = profile or generation.get("profile") or map_generation_profile(None)
    style = validate_style_preset(
        generation.get("style_preset") or generation.get("palette") or "parchment_atlas"
    )
    palette = generation.get("render_palette") or style_render_palette(
        style, prof.get("biome_warmth", 5.0)
    )
    terrain = generation.get("terrain_grid")
    if terrain and terrain.get("cells"):
        hex_g = hex_grid_from_terrain_grid(
            terrain, encode_terrain_rle, decode_terrain_rle
        )
    else:
        hex_g = hex_grid_mod.empty_hex_grid(encode_rle=encode_terrain_rle)
    upgraded = build_generation_from_hex_grid(
        hex_g, layout, detail, prof, style, palette,
        encode_terrain_rle, decode_terrain_rle,
    )
    meta = dict(generation.get("editor_meta") or {})
    meta["migrated_from_v6"] = True
    upgraded["editor_meta"] = meta
    return upgraded


def _migrate_city_to_v7(
    generation: dict,
    profile: dict | None,
) -> dict:
    layout, detail = _resolve_seeds_from_generation(generation)
    prof = _city_generation_profile(None, profile or generation.get("profile"))
    style = validate_style_preset(
        generation.get("style_preset") or generation.get("palette") or "parchment_atlas"
    )
    palette = generation.get("render_palette") or style_render_palette(
        style, prof.get("biome_warmth", 5.0)
    )
    terrain = generation.get("terrain_grid")
    if terrain and terrain.get("cells"):
        hex_g = hex_grid_from_terrain_grid(
            terrain, encode_terrain_rle, decode_terrain_rle
        )
    else:
        hex_g = generate_city_hex_grid(
            prof,
            layout,
            detail,
            encode_rle=encode_terrain_rle,
            decode_rle=decode_terrain_rle,
        )
    upgraded = build_generation_from_hex_grid(
        hex_g,
        layout,
        detail,
        prof,
        style,
        palette,
        encode_terrain_rle,
        decode_terrain_rle,
        scope=CITY_SCOPE,
    )
    meta = dict(generation.get("editor_meta") or {})
    meta["migrated_from_v6"] = True
    upgraded["editor_meta"] = meta
    return upgraded


def _migrate_shop_to_v7(
    generation: dict,
    profile: dict | None,
) -> dict:
    layout, detail = _resolve_seeds_from_generation(generation)
    prof = profile or generation.get("profile") or map_generation_profile(None)
    style = validate_style_preset(
        generation.get("style_preset") or generation.get("palette") or "parchment_atlas"
    )
    palette = generation.get("render_palette") or style_render_palette(
        style, prof.get("biome_warmth", 5.0)
    )
    terrain = generation.get("terrain_grid")
    if terrain and terrain.get("cells"):
        hex_g = hex_grid_from_terrain_grid(
            terrain, encode_terrain_rle, decode_terrain_rle
        )
    else:
        hex_g = generate_shop_hex_grid(
            prof,
            layout,
            detail,
            encode_rle=encode_terrain_rle,
            decode_rle=decode_terrain_rle,
        )
    upgraded = build_generation_from_hex_grid(
        hex_g,
        layout,
        detail,
        prof,
        style,
        palette,
        encode_terrain_rle,
        decode_terrain_rle,
        scope=SHOP_SCOPE,
    )
    meta = dict(generation.get("editor_meta") or {})
    meta["migrated_from_v6"] = True
    upgraded["editor_meta"] = meta
    return upgraded


def snap_marker_to_cell(generation: dict | None, x: float, y: float) -> dict | None:
    """Read-only: nearest hex or Voronoi cell for a normalized marker position."""
    gen = generation or {}
    scope = gen.get("scope") or WORLD_SCOPE
    if gen.get("hex_grid"):
        hg = gen["hex_grid"]
        hit = hex_grid_mod.nearest_hex(x, y, hg)
        if not hit:
            return None
        q, r = hit
        w = int(hg["width"])
        cells = decode_terrain_rle(
            str(hg.get("cells", "")),
            w * int(hg["height"]),
        )
        code = cells[hex_grid_mod.cell_index(q, r, w)]
        if scope == CITY_SCOPE:
            labels = {
                0: "wilderness",
                1: "courtyard",
                2: "canal",
                3: "park",
                4: "road",
                5: "building",
                6: "wall",
            }
        elif scope == SHOP_SCOPE:
            labels = {
                0: "outside",
                1: "floor",
                2: "counter",
                3: "display",
                4: "aisle",
                5: "shelf",
                6: "wall",
            }
        else:
            labels = {0: "water", 1: "plains", 2: "mountain", 3: "forest", 4: "desert"}
        return {
            "cell_id": f"{q},{r}",
            "biome": labels.get(code, "land"),
            "terrain_label": labels.get(code, "land"),
        }
    cg = (generation or {}).get("cell_graph") or {}
    cells = cg.get("cells") or []
    if not cells:
        return None
    best = None
    best_d = float("inf")
    for cell in cells:
        cx, cy = float(cell["centroid"][0]), float(cell["centroid"][1])
        d = (cx - x) ** 2 + (cy - y) ** 2
        if d < best_d:
            best_d = d
            best = cell
    if best is None:
        return None
    return {
        "cell_id": int(best["id"]),
        "biome": best.get("biome"),
        "terrain_label": str(best.get("label") or best.get("biome") or ""),
    }


def validate_partial_regen_mode(mode: str | None) -> str:
    cleaned = str(mode or "full").strip().lower()
    if cleaned not in MAP_PARTIAL_REGEN_MODES:
        raise MapValidationError(
            f"mode must be one of: {', '.join(sorted(MAP_PARTIAL_REGEN_MODES))}."
        )
    return cleaned


def validate_generation_json(data: dict, scope: str) -> dict:
    """Validate and normalize GM-submitted generation JSON for persistence."""
    if not isinstance(data, dict):
        raise MapValidationError("generation must be an object.")
    serialized = json.dumps(data, separators=(",", ":"))
    if len(serialized.encode("utf-8")) > MAX_GENERATION_JSON_BYTES:
        raise MapValidationError("generation JSON exceeds maximum allowed size.")

    out: dict = {
        "schema_version": GENERATION_SCHEMA_VERSION,
        "scope": scope,
    }
    for key in ("layout_seed", "detail_seed", "seed"):
        if data.get(key) is not None:
            out[key] = int(data[key]) & 0x7FFFFFFF
    if out.get("layout_seed") is not None:
        out["seed"] = out["layout_seed"]
    style = data.get("style_preset") or data.get("palette")
    if style:
        out["style_preset"] = validate_style_preset(style)
        out["palette"] = out["style_preset"]
    if isinstance(data.get("profile"), dict):
        out["profile"] = {
            k: _clamp_profile_value(k, v)
            for k, v in data["profile"].items()
            if k in PROFILE_CLAMP_KEYS
        }
    if isinstance(data.get("render_palette"), dict):
        out["render_palette"] = {
            str(k): str(v)[:32] for k, v in data["render_palette"].items()
        }

    grid = data.get("terrain_grid")
    if grid is not None:
        if not isinstance(grid, dict):
            raise MapValidationError("terrain_grid must be an object.")
        width = int(grid.get("width", TERRAIN_GRID_WIDTH))
        height = int(grid.get("height", TERRAIN_GRID_HEIGHT))
        if width < 1 or height < 1 or width > MAX_TERRAIN_GRID_WIDTH or height > MAX_TERRAIN_GRID_HEIGHT:
            raise MapValidationError("terrain_grid dimensions out of allowed range.")
        if width * height > MAX_TERRAIN_GRID_CELLS:
            raise MapValidationError("terrain_grid exceeds maximum cell count.")
        if grid.get("encoding") != "rle":
            raise MapValidationError("terrain_grid.encoding must be 'rle'.")
        cells = decode_terrain_rle(str(grid.get("cells", "")), width * height)
        if any(c < 0 or c > TERRAIN_CELL_MAX for c in cells):
            raise MapValidationError("terrain_grid contains invalid cell codes.")
        out["terrain_grid"] = {
            "width": width,
            "height": height,
            "encoding": "rle",
            "cells": encode_terrain_rle(cells),
        }

    features = data.get("features")
    preserved_features: list[dict] = []
    if features is not None:
        if not isinstance(features, list):
            raise MapValidationError("features must be an array.")
        if len(features) > MAX_MAP_FEATURES:
            raise MapValidationError(f"features exceeds maximum of {MAX_MAP_FEATURES}.")
        for f in features:
            if isinstance(f, dict) and f.get("type") in ("lake",):
                preserved_features.append(_validate_feature(f, scope))
        out["features"] = [_validate_feature(f, scope) for f in features]
    else:
        out["features"] = []

    cell_graph = data.get("cell_graph")
    if cell_graph is not None:
        out["cell_graph"] = _validate_cell_graph(cell_graph, scope)
        out = _finalize_cell_graph_derivation(out, scope)
        if preserved_features:
            out["features"] = list(out.get("features") or []) + preserved_features

    hex_grid = data.get("hex_grid")
    if hex_grid is not None and scope in (WORLD_SCOPE, CITY_SCOPE, SHOP_SCOPE):
        out["hex_grid"] = _validate_hex_grid(hex_grid)
        out = _finalize_hex_grid_derivation(out, scope)
        if preserved_features:
            out["features"] = list(out.get("features") or []) + preserved_features
    elif scope == WORLD_SCOPE and out.get("terrain_grid") and not out.get("hex_grid"):
        out["hex_grid"] = hex_grid_from_terrain_grid(
            out["terrain_grid"], encode_terrain_rle, decode_terrain_rle
        )
        out = _finalize_hex_grid_derivation(out, scope)

    if scope in (CITY_SCOPE, SHOP_SCOPE) and out.get("terrain_grid") and not out.get("hex_grid"):
        out["hex_grid"] = hex_grid_from_terrain_grid(
            out["terrain_grid"], encode_terrain_rle, decode_terrain_rle
        )
        out = _finalize_hex_grid_derivation(out, scope)

    meta = data.get("editor_meta") if isinstance(data.get("editor_meta"), dict) else {}
    out["editor_meta"] = {
        **meta,
        "last_edited_at": _utc_now_iso(),
    }
    return out


def _refresh_terrain_grid_from_cell_graph(generation: dict, scope: str) -> dict:
    """Re-rasterize terrain_grid from cell centroids (gapless Voronoi tiling)."""
    from app.services.map_generation.derive import derive_terrain_grid
    from app.services.map_generation import voronoi

    gen = dict(generation)
    cg = gen.get("cell_graph") or {}
    if not cg.get("cells"):
        return gen
    land_poly = cg.get("landmass_polygon")
    gen["terrain_grid"] = derive_terrain_grid(
        cg,
        TERRAIN_GRID_WIDTH,
        TERRAIN_GRID_HEIGHT,
        encode_terrain_rle,
        voronoi.point_in_polygon,
        landmask_polygon=land_poly,
        scope=scope,
    )
    return gen


def _finalize_cell_graph_derivation(out: dict, scope: str) -> dict:
    """Re-derive features and terrain_grid from validated cell_graph."""
    from app.services.map_generation.derive import derive_features, derive_terrain_grid
    from app.services.map_generation import voronoi

    cg = out.get("cell_graph") or {}
    land_poly = cg.get("landmass_polygon")
    out["features"] = derive_features(
        cg,
        scope,
        landmass_polygon=land_poly,
        island_polygons=cg.get("island_polygons"),
        extra_features=cg.get("extra_features"),
    )
    out["terrain_grid"] = derive_terrain_grid(
        cg,
        TERRAIN_GRID_WIDTH,
        TERRAIN_GRID_HEIGHT,
        encode_terrain_rle,
        voronoi.point_in_polygon,
        landmask_polygon=land_poly,
        scope=scope,
    )
    return out


def save_canvas_generation(
    canvas: MapCanvas,
    generation: dict,
    *,
    convert_from_upload: bool = False,
) -> None:
    """Persist validated studio edits. Caller commits."""
    validated = validate_generation_json(generation, canvas.scope)
    if convert_from_upload:
        delete_map_image(canvas)
        canvas.source_type = "generated"
        canvas.image_path = None
        canvas.width = 1024
        canvas.height = 1024
    canvas.generation_json = validated


def _generation_for_canvas_metadata(
    canvas: MapCanvas,
    settings: dict | None = None,
) -> dict:
    """Prepare generation JSON for overlay metadata without replacing uploads."""
    generation = dict(canvas.generation_json or {})
    if canvas.source_type == "uploaded":
        generation.setdefault("schema_version", GENERATION_SCHEMA_VERSION)
        generation["scope"] = canvas.scope
        return generation
    if settings is None:
        settings = _settings_for_campaign(canvas.campaign_id)
    profile = _merge_profile_for_canvas(canvas, settings, None)
    return ensure_studio_ready_generation(generation, canvas.scope, profile)


def convert_canvas_to_editable(canvas: MapCanvas, settings: dict | None = None) -> dict:
    """Remove uploaded background and return a studio-ready v6 generation."""
    if settings is None:
        settings = _settings_for_campaign(canvas.campaign_id)
    generation = canvas.generation_json or {}
    layout, detail = _resolve_seeds_from_generation(generation)
    profile = _merge_profile_for_canvas(canvas, settings, None)
    preset = generation.get("style_preset") or generation.get("palette")

    initial_sites = None
    land_poly = None
    img_path = map_underlay_file(canvas.id) if canvas.underlay_path else None
    if not img_path or not img_path.exists():
        uploaded = map_image_file(canvas.id)
        if canvas.source_type == "uploaded" and uploaded.exists():
            img_path = uploaded
    if img_path and img_path.exists():
        try:
            img = Image.open(img_path)
            initial_sites, land_poly, _cells = raster_import.import_raster_to_sites(
                img, canvas.scope, profile, layout,
            )
        except Exception:
            log.exception("raster_import_failed canvas_id=%s", canvas.id)

    delete_map_image(canvas)
    canvas.source_type = "generated"
    canvas.image_path = None

    if int(generation.get("schema_version") or 0) < V6_SCHEMA_VERSION or not generation.get("cell_graph"):
        if initial_sites is None and int(generation.get("schema_version") or 0) >= 5:
            generation = ensure_studio_ready_generation(generation, canvas.scope, profile)
        else:
            cell_graph = generate_map(
                canvas.scope,
                layout,
                profile,
                detail_seed=detail,
                mode="full",
                initial_sites=initial_sites,
                landmask_polygon=land_poly,
            )
            generation = build_generation_from_cell_graph(
                cell_graph,
                canvas.scope,
                layout,
                detail,
                profile,
                validate_style_preset(preset),
                style_render_palette(
                    validate_style_preset(preset),
                    profile.get("biome_warmth", 5.0),
                ),
                encode_terrain_rle,
            )
    else:
        generation = ensure_studio_ready_generation(generation, canvas.scope, profile)
    canvas.generation_json = generation
    canvas.width = 1024
    canvas.height = 1024
    return generation


def strip_editor_meta_for_player(generation: dict | None) -> dict:
    """Player payloads omit GM-only editor metadata."""
    gen = dict(generation or {})
    gen.pop("editor_meta", None)
    return gen


# ---------------------------------------------------------------------------
# Procedural background generation (visual metadata only, no gameplay rules)
# ---------------------------------------------------------------------------
def _round_point(x: float, y: float) -> list[float]:
    return [round(max(0.0, min(1.0, x)), 4), round(max(0.0, min(1.0, y)), 4)]


def _blob_points(
    rng: random.Random,
    cx: float,
    cy: float,
    radius_x: float,
    radius_y: float,
    count: int,
    *,
    wobble_rng: random.Random | None = None,
) -> list[list[float]]:
    """Generate an irregular normalized polygon around a center."""
    wobble_rng = wobble_rng or rng
    points = []
    for idx in range(count):
        angle = (math.tau * idx / count) + wobble_rng.uniform(-0.16, 0.16)
        wobble = wobble_rng.uniform(0.72, 1.22)
        x = cx + math.cos(angle) * radius_x * wobble
        y = cy + math.sin(angle) * radius_y * wobble
        points.append(_round_point(x, y))
    return points


def _polyline(
    rng: random.Random,
    start: tuple[float, float],
    end: tuple[float, float],
    bends: int,
    jitter: float,
    *,
    detail_rng: random.Random | None = None,
) -> list[list[float]]:
    """Generate a naturally bent line between two normalized points."""
    detail_rng = detail_rng or rng
    points = []
    for idx in range(bends + 2):
        t = idx / (bends + 1)
        x = start[0] + (end[0] - start[0]) * t + detail_rng.uniform(-jitter, jitter)
        y = start[1] + (end[1] - start[1]) * t + detail_rng.uniform(-jitter, jitter)
        points.append(_round_point(x, y))
    return points


def _edge_point(rng: random.Random, side: str | None = None) -> tuple[float, float]:
    """Pick a point on the normalized map edge."""
    side = side or rng.choice(("north", "south", "east", "west"))
    if side == "north":
        return (rng.uniform(0.12, 0.88), 0.04)
    if side == "south":
        return (rng.uniform(0.12, 0.88), 0.96)
    if side == "east":
        return (0.96, rng.uniform(0.12, 0.88))
    return (0.04, rng.uniform(0.12, 0.88))


def _ring_point(cx: float, cy: float, radius: float, angle: float) -> tuple[float, float]:
    return (
        max(0.08, min(0.92, cx + math.cos(angle) * radius)),
        max(0.08, min(0.92, cy + math.sin(angle) * radius)),
    )


def _settlement_hubs(rng: random.Random, count: int) -> list[tuple[float, float]]:
    """Plausible route anchors clustered on land, not map edges."""
    hubs = []
    for idx in range(max(2, count)):
        angle = (math.tau * idx / max(2, count)) + rng.uniform(-0.42, 0.42)
        radius = rng.uniform(0.12, 0.36)
        hubs.append(_ring_point(0.5, 0.52, radius, angle))
    hubs.sort(key=lambda p: (p[0], p[1]))
    return hubs


def _nearest_point(
    point: tuple[float, float],
    candidates: list[tuple[float, float]],
) -> tuple[float, float]:
    px, py = point
    return min(candidates, key=lambda p: (p[0] - px) ** 2 + (p[1] - py) ** 2)


def _midpoint_range(settings: dict | None, key: str, default: float) -> float:
    try:
        pair = ((settings or {}).get("ranges") or {}).get(key) or {}
        lo = float(pair.get("min"))
        hi = float(pair.get("max"))
        return (lo + hi) / 2.0
    except (TypeError, ValueError):
        return default


def _clamp_profile_value(key: str, value) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        num = 5.0
    if key == "landmass_scale":
        return max(1.0, min(10.0, num))
    if key in ("region_density",):
        return max(1.0, min(10.0, num))
    if key in ("city_density",):
        return max(1.0, min(40.0, num))
    if key in ("city_complexity",):
        return max(1.0, min(20.0, num))
    if key in ("island_count",):
        return max(0.0, min(10.0, num))
    if key in (
        "land_frequency",
        "vegetation_frequency",
        "grassland_frequency",
        "hills_frequency",
        "desert_frequency",
        "mountain_frequency",
        "swamp_frequency",
        "cluster_percent",
    ):
        return max(0.0, min(100.0, num))
    if key in ("hex_width", "hex_height"):
        return max(24.0, min(500.0, num))
    if key == "hex_size":
        return max(6.0, min(24.0, num))
    return max(0.0, min(10.0, num))


def validate_style_preset(preset: str | None) -> str:
    if preset is None:
        return "parchment_atlas"
    cleaned = str(preset).strip().lower()
    if cleaned in MAP_STYLE_PRESETS:
        return cleaned
    if cleaned in LEGACY_PALETTE_TO_STYLE:
        return LEGACY_PALETTE_TO_STYLE[cleaned]
    raise MapValidationError(
        f"style_preset must be one of: {', '.join(sorted(MAP_STYLE_PRESETS))}."
    )


def validate_regen_mode(mode: str | None) -> str:
    cleaned = str(mode or "full").strip().lower()
    if cleaned not in MAP_REGEN_MODES:
        raise MapValidationError(
            f"mode must be one of: {', '.join(sorted(MAP_REGEN_MODES))}."
        )
    return cleaned


def style_render_palette(preset: str, biome_warmth: float = 5.0) -> dict:
    """Server-side palette hints for the client renderer."""
    preset = validate_style_preset(preset)
    warmth = _clamp_profile_value("biome_warmth", biome_warmth) / 10.0
    palettes = {
        "parchment_atlas": {
            "water_shallow": "#9fc9c5",
            "water_deep": "#5a9aa8",
            "land": "#d8c690",
            "land_coast": "#e8d8a8",
            "coast_stroke": "#8e7a4e",
            "forest": "#2f5c2d",
            "forest_stipple": "#1e3d1c",
            "grassland": "#477c45",
            "hill_light": "#c4b878",
            "hill_shadow": "#9a8a58",
            "mountain_light": "#8a8070",
            "mountain_shadow": "#4a4038",
            "river": "#317aa3",
            "route": "#7c4a23",
            "stage_bg": "#ece3cd",
        },
        "satellite": {
            "water_shallow": "#4a90a4",
            "water_deep": "#1a3a52",
            "land": "#6b8e4e",
            "land_coast": "#8fbc6f",
            "coast_stroke": "#3d5c3a",
            "forest": "#152e14",
            "forest_stipple": "#0d2010",
            "grassland": "#2a5028",
            "hill_light": "#8aa870",
            "hill_shadow": "#4a6840",
            "mountain_light": "#a0a8b0",
            "mountain_shadow": "#505860",
            "river": "#2a6080",
            "route": "#c4a35a",
            "stage_bg": "#ccd4dd",
        },
        "dark_fantasy": {
            "water_shallow": "#2a4858",
            "water_deep": "#0a1828",
            "land": "#4a4038",
            "land_coast": "#5a5048",
            "coast_stroke": "#2a2018",
            "forest": "#0a2818",
            "forest_stipple": "#051810",
            "grassland": "#1a3828",
            "hill_light": "#5a5048",
            "hill_shadow": "#2a2018",
            "mountain_light": "#6a6068",
            "mountain_shadow": "#2a2830",
            "river": "#1a4868",
            "route": "#6a4030",
            "stage_bg": "#1a1818",
        },
        "ink_sketch": {
            "water_shallow": "#e8e4dc",
            "water_deep": "#c8c4bc",
            "land": "#f0ece4",
            "land_coast": "#faf8f4",
            "coast_stroke": "#2a2820",
            "forest": "#484840",
            "forest_stipple": "#303028",
            "grassland": "#686860",
            "hill_light": "#dcd8d0",
            "hill_shadow": "#a8a4a0",
            "mountain_light": "#888480",
            "mountain_shadow": "#484440",
            "river": "#686860",
            "route": "#404040",
            "stage_bg": "#f4f0e8",
        },
    }
    base = palettes[preset]
    if warmth > 0.55:
        shift = (warmth - 0.5) * 0.15
        return {**base, "warmth_shift": round(shift, 3)}
    if warmth < 0.45:
        shift = (0.5 - warmth) * 0.15
        return {**base, "cool_shift": round(shift, 3)}
    return dict(base)


def map_generation_profile(
    settings: dict | None = None,
    overrides: dict | None = None,
) -> dict:
    """Translate world-gen sliders into visual map-generation weights."""
    landmass = _midpoint_range(settings, "map_landmass_scale", 6.0)
    waterways = _midpoint_range(settings, "map_waterways", 4.0)
    roughness = _midpoint_range(settings, "map_terrain_roughness", 5.0)
    regions = _midpoint_range(settings, "num_regions", 3.0)
    cities = _midpoint_range(settings, "num_cities", 6.0)
    item_pool = _midpoint_range(settings, "global_item_pool_size", 85.0)
    city_variation = _midpoint_range(settings, "city_size_variation", 5.5)
    items_per_shop = _midpoint_range(settings, "items_per_shop", 10.0)
    tech_magic = _midpoint_range(settings, "tech_magic_balance", 5.0)
    profile = {
        "landmass_scale": max(1.0, min(10.0, landmass)),
        "waterways": max(0.0, min(10.0, waterways)),
        "terrain_roughness": max(0.0, min(10.0, roughness)),
        "coast_detail": 5.0,
        "island_count": 0.0,
        "biome_warmth": 5.0,
        "region_density": max(1.0, min(10.0, regions)),
        "city_density": max(1.0, min(40.0, cities)),
        "economy_density": max(0.0, min(10.0, (item_pool / 50.0) + (items_per_shop / 5.0))),
        "city_complexity": max(1.0, min(20.0, city_variation)),
        "tech_magic_balance": max(0.0, min(10.0, tech_magic)),
        "wind_direction": 2.5,
        "moisture_strength": 8.5,
        "land_frequency": max(10.0, min(95.0, 35.0 + landmass * 5.5)),
        "vegetation_frequency": 18.0,
        "grassland_frequency": 22.0,
        "hills_frequency": 12.0,
        "desert_frequency": 15.0,
        "mountain_frequency": max(2.0, min(30.0, roughness * 1.2)),
        "swamp_frequency": 5.0,
        "cluster_percent": 70.0,
        "land_form": "large_continents" if landmass >= 7 else ("archipelago" if landmass <= 4 else "scattered"),
        "hex_width": 200.0,
        "hex_height": 125.0,
        "hex_size": 12.0,
    }
    if overrides:
        for key, value in overrides.items():
            if key in PROFILE_CLAMP_KEYS:
                profile[key] = _clamp_profile_value(key, value)
            elif key == "land_form":
                cleaned = str(value).strip().lower()
                if cleaned in LAND_FORM_OPTIONS:
                    profile["land_form"] = cleaned
    return profile


def _city_generation_profile(
    settings: dict | None,
    base: dict | None = None,
) -> dict:
    """City canvases use a smaller hex grid tuned for walled districts."""
    profile = dict(base or map_generation_profile(settings))
    profile["hex_width"] = float(profile.get("hex_width") or CITY_DEFAULT_HEX_WIDTH)
    profile["hex_height"] = float(profile.get("hex_height") or CITY_DEFAULT_HEX_HEIGHT)
    profile["hex_size"] = float(profile.get("hex_size") or CITY_DEFAULT_HEX_SIZE)
    if profile["hex_width"] > 140:
        profile["hex_width"] = CITY_DEFAULT_HEX_WIDTH
    if profile["hex_height"] > 100:
        profile["hex_height"] = CITY_DEFAULT_HEX_HEIGHT
    return profile


def _settings_for_campaign(campaign_id: int) -> dict | None:
    row = CampaignWorldConfig.query.filter_by(campaign_id=campaign_id).first()
    if row and isinstance(row.settings_json, dict):
        return row.settings_json
    return None


def _top_goods_for_city(city: City) -> dict:
    shop_ids = [shop.shop_id for shop in city.shops]
    if not shop_ids:
        return {"by_price": [], "by_average_volume": []}

    rows = (
        db.session.query(
            Item.item_id,
            Item.name,
            db.func.avg(ShopInventory.dynamic_price).label("avg_price"),
            db.func.avg(ShopInventory.stock).label("avg_volume"),
        )
        .join(ShopInventory, ShopInventory.item_id == Item.item_id)
        .filter(
            ShopInventory.campaign_id == city.campaign_id,
            ShopInventory.shop_id.in_(shop_ids),
        )
        .group_by(Item.item_id, Item.name)
        .all()
    )
    goods = [
        {
            "id": item_id,
            "name": name,
            "average_price": round(float(avg_price or 0), 2),
            "average_volume": round(float(avg_volume or 0), 2),
        }
        for item_id, name, avg_price, avg_volume in rows
    ]
    return {
        "by_price": sorted(goods, key=lambda item: item["average_price"], reverse=True)[:5],
        "by_average_volume": sorted(
            goods, key=lambda item: item["average_volume"], reverse=True
        )[:5],
    }


def _top_goods_for_shop(shop: Shop) -> dict:
    rows = (
        db.session.query(
            Item.item_id,
            Item.name,
            ShopInventory.dynamic_price,
            ShopInventory.stock,
        )
        .join(ShopInventory, ShopInventory.item_id == Item.item_id)
        .filter(
            ShopInventory.campaign_id == shop.campaign_id,
            ShopInventory.shop_id == shop.shop_id,
        )
        .all()
    )
    goods = [
        {
            "id": item_id,
            "name": name,
            "average_price": round(float(dynamic_price or 0), 2),
            "average_volume": round(float(stock or 0), 2),
        }
        for item_id, name, dynamic_price, stock in rows
    ]
    return {
        "by_price": sorted(goods, key=lambda item: item["average_price"], reverse=True)[:5],
        "by_average_volume": sorted(
            goods, key=lambda item: item["average_volume"], reverse=True
        )[:5],
    }


def _npc_display_name(player: Player | None, campaign) -> str | None:
    if player is None:
        return None
    from app.services import character_sheet_service

    sheet = character_sheet_service.get_or_default_sheet(player, campaign)
    name = (sheet.get("name") or "").strip()
    return name or f"NPC #{player.id}"


def _player_for_map(campaign_id: int, player_id: int | None) -> Player | None:
    if not player_id:
        return None
    return Player.query.filter_by(
        id=int(player_id),
        campaign_id=campaign_id,
        is_npc=True,
    ).first()


def _map_person_field(
    person: Player | None,
    campaign,
    *,
    label: str,
    for_player: bool = False,
) -> dict | None:
    """Build ruler/owner row for map stat cards."""
    if person is None:
        if for_player:
            return None
        return {"label": label, "display": "Unassigned"}
    if for_player and not bool(getattr(person, "known_to_players", False)):
        return None
    display = _npc_display_name(person, campaign) or f"NPC #{person.id}"
    return {"label": label, "display": display, "player_id": person.id}


def _map_person_field_for_id(
    campaign_id: int,
    campaign,
    player_id: int | None,
    *,
    label: str,
    for_player: bool = False,
) -> dict | None:
    person = _player_for_map(campaign_id, player_id)
    if person is None and player_id:
        if for_player:
            return None
        return {
            "label": label,
            "display": f"NPC #{int(player_id)}",
            "player_id": int(player_id),
        }
    return _map_person_field(
        person,
        campaign,
        label=label,
        for_player=for_player,
    )


def _people_directory(campaign_id: int, campaign, *, for_player: bool = False) -> dict:
    """NPC id -> display info for map popouts."""
    directory: dict = {}
    npcs = (
        Player.query.filter_by(campaign_id=campaign_id, is_npc=True)
        .order_by(Player.id.asc())
        .all()
    )
    for npc in npcs:
        if for_player and not bool(getattr(npc, "known_to_players", False)):
            continue
        display = _npc_display_name(npc, campaign) or f"NPC #{npc.id}"
        directory[str(npc.id)] = {
            "label": "NPC",
            "display": display,
            "player_id": npc.id,
        }
    return directory


def _city_summary(city: City, campaign, *, for_player: bool = False) -> dict:
    population = int(city.population or 0)
    goods = _top_goods_for_city(city)
    return {
        "population": population,
        "species_population": species_compendium_service.city_species_population(
            city.campaign_id, city.city_id, population
        ),
        "top_goods_by_price": goods["by_price"],
        "top_goods_by_average_volume": goods["by_average_volume"],
        "owner": _map_person_field_for_id(
            city.campaign_id,
            campaign,
            city.owner_player_id,
            label="Owner",
            for_player=for_player,
        ),
    }


def _shop_summary(shop: Shop, campaign, *, for_player: bool = False) -> dict:
    goods = _top_goods_for_shop(shop)
    return {
        "top_goods_by_price": goods["by_price"],
        "top_goods_by_average_volume": goods["by_average_volume"],
        "owner": _map_person_field_for_id(
            shop.campaign_id,
            campaign,
            shop.owner_player_id,
            label="Owner",
            for_player=for_player,
        ),
    }


def _region_map_entry(region: Region, campaign, *, for_player: bool = False) -> dict:
    return {
        "id": region.id,
        "name": region.name,
        "ruler_player_id": region.ruler_player_id,
        "ruler": _map_person_field_for_id(
            region.campaign_id,
            campaign,
            region.ruler_player_id,
            label="Ruler",
            for_player=for_player,
        ),
    }


def _resolve_seeds_from_generation(generation: dict | None) -> tuple[int, int]:
    gen = generation or {}
    layout = gen.get("layout_seed")
    detail = gen.get("detail_seed")
    legacy = gen.get("seed")
    if layout is None:
        layout = legacy if legacy is not None else random.SystemRandom().randint(0, 0x7FFFFFFF)
    if detail is None:
        detail = legacy if legacy is not None else (int(layout) ^ 0xDEADBEEF) & 0x7FFFFFFF
    return int(layout) & 0x7FFFFFFF, int(detail) & 0x7FFFFFFF


def _island_count_for_profile(profile: dict, land: float, rough: float) -> int:
    explicit = profile.get("island_count", 0)
    if explicit and float(explicit) >= 1:
        return max(1, int(round(float(explicit))))
    return max(1, int(1 + rough / 2 + (10 - land) / 4))


def generate_canvas_background(
    scope: str,
    layout_seed: int,
    profile: dict | None = None,
    *,
    detail_seed: int | None = None,
    style_preset: str | None = None,
    mode: Literal["full", "layout", "details"] = "full",
    existing_generation: dict | None = None,
) -> dict:
    """Deterministic map metadata the client renders as a backdrop."""
    layout_seed = int(layout_seed) & 0x7FFFFFFF
    if detail_seed is None:
        detail_seed = (layout_seed ^ 0xDEADBEEF) & 0x7FFFFFFF
    else:
        detail_seed = int(detail_seed) & 0x7FFFFFFF
    profile = profile or map_generation_profile(None)
    style = validate_style_preset(style_preset or "parchment_atlas")
    render_palette = style_render_palette(style, profile.get("biome_warmth", 5.0))

    if scope == WORLD_SCOPE:
        existing_hex = (existing_generation or {}).get("hex_grid")
        hex_grid = generate_world_hex_grid(
            profile,
            layout_seed,
            detail_seed,
            mode=mode,
            existing=existing_hex,
            encode_rle=encode_terrain_rle,
            decode_rle=decode_terrain_rle,
        )
        return build_generation_from_hex_grid(
            hex_grid,
            layout_seed,
            detail_seed,
            profile,
            style,
            render_palette,
            encode_terrain_rle,
            decode_terrain_rle,
            scope=WORLD_SCOPE,
        )

    if scope == CITY_SCOPE:
        existing_hex = (existing_generation or {}).get("hex_grid")
        profile = _city_generation_profile(None, profile)
        hex_grid = generate_city_hex_grid(
            profile,
            layout_seed,
            detail_seed,
            mode=mode,
            existing=existing_hex,
            encode_rle=encode_terrain_rle,
            decode_rle=decode_terrain_rle,
        )
        return build_generation_from_hex_grid(
            hex_grid,
            layout_seed,
            detail_seed,
            profile,
            style,
            render_palette,
            encode_terrain_rle,
            decode_terrain_rle,
            scope=CITY_SCOPE,
        )

    if scope == SHOP_SCOPE:
        existing_hex = (existing_generation or {}).get("hex_grid")
        hex_grid = generate_shop_hex_grid(
            profile,
            layout_seed,
            detail_seed,
            mode=mode,
            existing=existing_hex,
            encode_rle=encode_terrain_rle,
            decode_rle=decode_terrain_rle,
        )
        return build_generation_from_hex_grid(
            hex_grid,
            layout_seed,
            detail_seed,
            profile,
            style,
            render_palette,
            encode_terrain_rle,
            decode_terrain_rle,
            scope=SHOP_SCOPE,
        )

    existing_graph = (existing_generation or {}).get("cell_graph")
    land_poly = None
    if existing_graph:
        land_poly = existing_graph.get("landmass_polygon")
    cell_graph = generate_map(
        scope,
        layout_seed,
        profile,
        detail_seed=detail_seed,
        mode=mode,
        existing_cell_graph=existing_graph,
        landmask_polygon=land_poly,
    )
    result = build_generation_from_cell_graph(
        cell_graph,
        scope,
        layout_seed,
        detail_seed,
        profile,
        style,
        render_palette,
        encode_terrain_rle,
    )
    result["schema_version"] = GENERATION_SCHEMA_VERSION
    return result


def apply_partial_regen(
    canvas: MapCanvas,
    mode: str,
    *,
    settings: dict | None = None,
    profile_overrides: dict | None = None,
) -> dict:
    """Re-run a subset of the cell-graph pipeline (vector layer edits)."""
    cleaned = validate_partial_regen_mode(mode)
    generation = dict(canvas.generation_json or {})
    if settings is None:
        settings = _settings_for_campaign(canvas.campaign_id)
    profile = _merge_profile_for_canvas(canvas, settings, profile_overrides)
    layout, detail = _resolve_seeds_from_generation(generation)
    if int(generation.get("schema_version") or 0) < V7_SCHEMA_VERSION:
        generation = ensure_studio_ready_generation(generation, canvas.scope, profile)
    if canvas.scope == WORLD_SCOPE:
        existing_hex = generation.get("hex_grid")
        hex_mode: Literal["full", "layout", "details"] = "full"
        if cleaned in ("layout",):
            hex_mode = "layout"
        elif cleaned in ("details", "climate", "hydrology", "tectonics"):
            hex_mode = "details"
        hex_grid = generate_world_hex_grid(
            profile,
            layout,
            detail,
            mode=hex_mode,
            existing=existing_hex,
            encode_rle=encode_terrain_rle,
            decode_rle=decode_terrain_rle,
        )
        style = generation.get("style_preset") or generation.get("palette") or "parchment_atlas"
        style = validate_style_preset(style)
        updated = build_generation_from_hex_grid(
            hex_grid,
            layout,
            detail,
            profile,
            style,
            generation.get("render_palette") or style_render_palette(style, profile.get("biome_warmth", 5.0)),
            encode_terrain_rle,
            decode_terrain_rle,
            scope=WORLD_SCOPE,
        )
    elif canvas.scope == CITY_SCOPE:
        profile = _city_generation_profile(settings, profile)
        existing_hex = generation.get("hex_grid")
        hex_mode: Literal["full", "layout", "details"] = "full"
        if cleaned in ("layout",):
            hex_mode = "layout"
        elif cleaned in ("details", "climate", "hydrology", "tectonics"):
            hex_mode = "details"
        hex_grid = generate_city_hex_grid(
            profile,
            layout,
            detail,
            mode=hex_mode,
            existing=existing_hex,
            encode_rle=encode_terrain_rle,
            decode_rle=decode_terrain_rle,
        )
        style = generation.get("style_preset") or generation.get("palette") or "parchment_atlas"
        style = validate_style_preset(style)
        updated = build_generation_from_hex_grid(
            hex_grid,
            layout,
            detail,
            profile,
            style,
            generation.get("render_palette") or style_render_palette(style, profile.get("biome_warmth", 5.0)),
            encode_terrain_rle,
            decode_terrain_rle,
            scope=CITY_SCOPE,
        )
    elif canvas.scope == SHOP_SCOPE:
        profile = _shop_generation_profile(settings, None)
        if canvas.shop_id:
            shop_row = Shop.query.filter_by(
                shop_id=canvas.shop_id, campaign_id=canvas.campaign_id
            ).first()
            if shop_row is not None:
                profile = _shop_generation_profile(settings, shop_row)
        existing_hex = generation.get("hex_grid")
        hex_mode: Literal["full", "layout", "details"] = "full"
        if cleaned in ("layout",):
            hex_mode = "layout"
        elif cleaned in ("details", "climate", "hydrology", "tectonics"):
            hex_mode = "details"
        hex_grid = generate_shop_hex_grid(
            profile,
            layout,
            detail,
            mode=hex_mode,
            existing=existing_hex,
            encode_rle=encode_terrain_rle,
            decode_rle=decode_terrain_rle,
        )
        style = generation.get("style_preset") or generation.get("palette") or "parchment_atlas"
        style = validate_style_preset(style)
        updated = build_generation_from_hex_grid(
            hex_grid,
            layout,
            detail,
            profile,
            style,
            generation.get("render_palette") or style_render_palette(style, profile.get("biome_warmth", 5.0)),
            encode_terrain_rle,
            decode_terrain_rle,
            scope=SHOP_SCOPE,
        )
    else:
        cell_graph = partial_regen(
            canvas.scope,
            generation,
            cleaned,  # type: ignore[arg-type]
            profile,
            layout,
            detail_seed=detail,
        )
        style = generation.get("style_preset") or generation.get("palette") or "parchment_atlas"
        style = validate_style_preset(style)
        updated = build_generation_from_cell_graph(
            cell_graph,
            canvas.scope,
            layout,
            detail,
            profile,
            style,
            generation.get("render_palette") or style_render_palette(style, profile.get("biome_warmth", 5.0)),
            encode_terrain_rle,
        )
        updated["schema_version"] = GENERATION_SCHEMA_VERSION
    meta = dict(generation.get("editor_meta") or {})
    meta["last_partial_regen"] = cleaned
    updated["editor_meta"] = meta
    canvas.generation_json = updated
    return updated



def preview_canvas_background(
    scope: str,
    layout_seed: int,
    profile: dict | None = None,
    *,
    detail_seed: int | None = None,
    style_preset: str | None = None,
) -> dict:
    """Pure preview helper — no DB mutation."""
    return generate_canvas_background(
        scope,
        layout_seed,
        profile,
        detail_seed=detail_seed,
        style_preset=style_preset,
    )


def _canvas_seed(
    campaign_id: int,
    city_id: int | None = None,
    shop_id: int | None = None,
) -> int:
    """Stable per-canvas seed; repeatable across processes (no hash())."""
    return (
        campaign_id * 1_000_003 + (city_id or 0) * 997 + (shop_id or 0) * 991
    ) & 0x7FFFFFFF


def _merge_profile_for_canvas(
    canvas: MapCanvas,
    settings: dict | None,
    profile_overrides: dict | None,
) -> dict:
    existing = (canvas.generation_json or {}).get("profile") or {}
    base = map_generation_profile(settings, overrides=existing)
    if profile_overrides:
        return map_generation_profile(settings, overrides={**base, **profile_overrides})
    return base


def _resolve_regen_seeds(
    generation: dict | None,
    mode: str,
    layout_seed: int | None,
    detail_seed: int | None,
) -> tuple[int, int]:
    cur_layout, cur_detail = _resolve_seeds_from_generation(generation)
    sys_rng = random.SystemRandom()
    if mode == "full":
        new_layout = (
            int(layout_seed) & 0x7FFFFFFF
            if layout_seed is not None
            else sys_rng.randint(0, 0x7FFFFFFF)
        )
        new_detail = (
            int(detail_seed) & 0x7FFFFFFF
            if detail_seed is not None
            else sys_rng.randint(0, 0x7FFFFFFF)
        )
        return new_layout, new_detail
    if mode == "layout":
        new_layout = (
            int(layout_seed) & 0x7FFFFFFF
            if layout_seed is not None
            else sys_rng.randint(0, 0x7FFFFFFF)
        )
        new_detail = (
            int(detail_seed) & 0x7FFFFFFF
            if detail_seed is not None
            else cur_detail
        )
        return new_layout, new_detail
    # details
    new_detail = (
        int(detail_seed) & 0x7FFFFFFF
        if detail_seed is not None
        else sys_rng.randint(0, 0x7FFFFFFF)
    )
    new_layout = (
        int(layout_seed) & 0x7FFFFFFF
        if layout_seed is not None
        else cur_layout
    )
    return new_layout, new_detail


def regenerate_canvas_background(
    canvas: MapCanvas,
    *,
    mode: Literal["layout", "details", "full"] = "full",
    layout_seed: int | None = None,
    detail_seed: int | None = None,
    profile_overrides: dict | None = None,
    style_preset: str | None = None,
    settings: dict | None = None,
) -> None:
    """Switch a canvas back to a (new) generated background. Caller commits."""
    mode = validate_regen_mode(mode)
    generation = canvas.generation_json or {}
    new_layout, new_detail = _resolve_regen_seeds(
        generation, mode, layout_seed, detail_seed
    )
    delete_map_image(canvas)
    canvas.source_type = "generated"
    canvas.image_path = None
    if settings is None:
        settings = _settings_for_campaign(canvas.campaign_id)
    profile = _merge_profile_for_canvas(canvas, settings, profile_overrides)
    preset = style_preset
    if preset is None:
        preset = generation.get("style_preset") or generation.get("palette")
    pipeline_mode: Literal["full", "layout", "details"] = (
        "full" if mode == "full" else ("layout" if mode == "layout" else "details")
    )
    canvas.generation_json = generate_canvas_background(
        canvas.scope,
        new_layout,
        profile,
        detail_seed=new_detail,
        style_preset=preset,
        mode=pipeline_mode,
        existing_generation=generation if mode != "full" else None,
    )
    canvas.width = 1024
    canvas.height = 1024


def parse_background_request(data: dict | None, canvas: MapCanvas) -> dict:
    """Validate JSON background/preview request fields."""
    data = data or {}
    mode = validate_regen_mode(data.get("mode"))
    if data.get("seed_locked") and mode == "layout":
        raise MapValidationError(
            "Layout seed is locked. Unlock it or use Regenerate details."
        )
    generation = canvas.generation_json or {}
    layout_seed = data.get("layout_seed")
    detail_seed = data.get("detail_seed")
    if layout_seed is not None:
        layout_seed = int(layout_seed) & 0x7FFFFFFF
    if detail_seed is not None:
        detail_seed = int(detail_seed) & 0x7FFFFFFF
    style_preset = data.get("style_preset")
    if style_preset is not None:
        style_preset = validate_style_preset(style_preset)
    profile_overrides = data.get("profile")
    if profile_overrides is not None:
        if not isinstance(profile_overrides, dict):
            raise MapValidationError("profile must be an object.")
        profile_overrides = {
            k: _clamp_profile_value(k, v)
            for k, v in profile_overrides.items()
            if k in PROFILE_CLAMP_KEYS
        }
    return {
        "mode": mode,
        "layout_seed": layout_seed,
        "detail_seed": detail_seed,
        "style_preset": style_preset,
        "profile_overrides": profile_overrides,
    }


def build_background_preview(
    canvas: MapCanvas,
    campaign_id: int,
    data: dict | None = None,
) -> dict:
    """Build preview generation JSON without mutating the canvas."""
    opts = parse_background_request(data, canvas)
    settings = _settings_for_campaign(campaign_id)
    profile = _merge_profile_for_canvas(canvas, settings, opts["profile_overrides"])
    layout, detail = _resolve_regen_seeds(
        canvas.generation_json,
        opts["mode"],
        opts["layout_seed"],
        opts["detail_seed"],
    )
    preset = opts["style_preset"]
    if preset is None:
        gen = canvas.generation_json or {}
        preset = gen.get("style_preset") or gen.get("palette")
    return preview_canvas_background(
        canvas.scope,
        layout,
        profile,
        detail_seed=detail,
        style_preset=preset,
    )


def _generation_needs_upgrade(canvas: MapCanvas) -> bool:
    if canvas.source_type != "generated":
        return False
    generation = canvas.generation_json or {}
    return int(generation.get("schema_version") or 0) < LEGACY_SCHEMA_REGEN_BELOW


# ---------------------------------------------------------------------------
# Canvas get-or-create
# ---------------------------------------------------------------------------
def get_or_create_world_canvas(
    campaign_id: int,
    seed: int | None = None,
    settings: dict | None = None,
) -> MapCanvas:
    """Fetch or create the campaign's world canvas. Flushes; caller commits.

    `seed` lets world generation reuse the campaign's resolved world seed so
    the generated backdrop is repeatable alongside the world itself.
    """
    canvas = MapCanvas.query.filter_by(
        campaign_id=campaign_id, scope=WORLD_SCOPE
    ).first()
    if canvas is None:
        if seed is None:
            seed = _canvas_seed(campaign_id)
        if settings is None:
            settings = _settings_for_campaign(campaign_id)
        canvas = MapCanvas(
            campaign_id=campaign_id,
            scope=WORLD_SCOPE,
            source_type="generated",
            generation_json=generate_canvas_background(
                WORLD_SCOPE,
                int(seed),
                map_generation_profile(settings),
            ),
        )
        db.session.add(canvas)
        db.session.flush()
    elif _generation_needs_upgrade(canvas):
        generation = canvas.generation_json or {}
        layout, detail = _resolve_seeds_from_generation(generation)
        regenerate_canvas_background(
            canvas,
            mode="full",
            layout_seed=layout,
            detail_seed=detail,
            settings=settings,
        )
    return canvas


def _city_has_building_layout(generation: dict) -> bool:
    hg_data = generation.get("hex_grid")
    if not hg_data or not hg_data.get("cells"):
        return False
    width = int(hg_data.get("width", 0))
    height = int(hg_data.get("height", 0))
    if width <= 0 or height <= 0:
        return False
    cells = decode_terrain_rle(str(hg_data["cells"]), width * height)
    return any(code == 5 for code in cells)


def _city_canvas_needs_hex_upgrade(canvas: MapCanvas) -> bool:
    if canvas.scope != CITY_SCOPE or canvas.source_type != "generated":
        return False
    if canvas.image_path:
        return False
    generation = canvas.generation_json or {}
    schema = int(generation.get("schema_version") or 0)
    if schema < V7_SCHEMA_VERSION:
        return True
    return not generation.get("hex_grid")


def _city_canvas_needs_building_layout(canvas: MapCanvas) -> bool:
    if canvas.scope != CITY_SCOPE or canvas.source_type != "generated":
        return False
    if canvas.image_path:
        return False
    generation = canvas.generation_json or {}
    if not generation.get("hex_grid"):
        return False
    return not _city_has_building_layout(generation)


def get_or_create_city_canvas(
    campaign_id: int,
    city: City,
    settings: dict | None = None,
) -> MapCanvas:
    """Fetch or create the canvas for one campaign city. Flushes; caller commits."""
    canvas = MapCanvas.query.filter_by(
        campaign_id=campaign_id, city_id=city.city_id, scope=CITY_SCOPE
    ).first()
    if settings is None:
        settings = _settings_for_campaign(campaign_id)
    if canvas is None:
        canvas = MapCanvas(
            campaign_id=campaign_id,
            city_id=city.city_id,
            scope=CITY_SCOPE,
            source_type="generated",
            generation_json=generate_canvas_background(
                CITY_SCOPE,
                _canvas_seed(campaign_id, city.city_id),
                _city_generation_profile(settings),
            ),
        )
        db.session.add(canvas)
        db.session.flush()
    elif _city_canvas_needs_building_layout(canvas):
        generation = canvas.generation_json or {}
        layout, detail = _resolve_seeds_from_generation(generation)
        regenerate_canvas_background(
            canvas,
            mode="full",
            layout_seed=layout,
            detail_seed=detail,
            settings=settings,
        )
    elif _city_canvas_needs_hex_upgrade(canvas):
        canvas.generation_json = ensure_studio_ready_generation(
            canvas.generation_json or {},
            CITY_SCOPE,
            _city_generation_profile(settings),
        )
    elif _generation_needs_upgrade(canvas):
        generation = canvas.generation_json or {}
        layout, detail = _resolve_seeds_from_generation(generation)
        regenerate_canvas_background(
            canvas,
            mode="full",
            layout_seed=layout,
            detail_seed=detail,
            settings=settings,
        )
    return canvas


def _shop_generation_profile(settings: dict | None, shop: Shop | None) -> dict:
    """Tighter interior layout for shop-floor canvases."""
    base = map_generation_profile(settings)
    complexity = min(float(base.get("city_complexity", 5)), 4.0)
    economy = float(base.get("economy_density", 5))
    if shop and shop.type:
        type_key = str(shop.type).lower()
        if "black" in type_key or "magic" in type_key:
            economy = max(economy, 6.0)
        elif "general" in type_key:
            economy = min(economy, 5.0)
    return {**base, "city_complexity": complexity, "economy_density": economy}


def _shop_canvas_needs_hex_upgrade(canvas: MapCanvas) -> bool:
    if canvas.scope != SHOP_SCOPE or canvas.source_type != "generated":
        return False
    if canvas.image_path:
        return False
    generation = canvas.generation_json or {}
    schema = int(generation.get("schema_version") or 0)
    if schema < V7_SCHEMA_VERSION:
        return True
    return not generation.get("hex_grid")


def _shop_canvas_needs_interior_layout(canvas: MapCanvas) -> bool:
    if canvas.scope != SHOP_SCOPE or canvas.source_type != "generated":
        return False
    if canvas.image_path:
        return False
    generation = canvas.generation_json or {}
    if not generation.get("hex_grid"):
        return False
    return not _city_has_building_layout(generation)


def get_or_create_shop_canvas(
    campaign_id: int,
    shop: Shop,
    settings: dict | None = None,
) -> MapCanvas:
    """Fetch or create the interior canvas for one campaign shop."""
    canvas = MapCanvas.query.filter_by(
        campaign_id=campaign_id, shop_id=shop.shop_id, scope=SHOP_SCOPE
    ).first()
    if settings is None:
        settings = _settings_for_campaign(campaign_id)
    profile = _shop_generation_profile(settings, shop)
    if canvas is None:
        canvas = MapCanvas(
            campaign_id=campaign_id,
            shop_id=shop.shop_id,
            scope=SHOP_SCOPE,
            source_type="generated",
            generation_json=generate_canvas_background(
                SHOP_SCOPE,
                _canvas_seed(campaign_id, shop_id=shop.shop_id),
                profile,
            ),
        )
        db.session.add(canvas)
        db.session.flush()
    elif _shop_canvas_needs_interior_layout(canvas):
        generation = canvas.generation_json or {}
        layout, detail = _resolve_seeds_from_generation(generation)
        regenerate_canvas_background(
            canvas,
            mode="full",
            layout_seed=layout,
            detail_seed=detail,
            settings=settings,
        )
    elif _shop_canvas_needs_hex_upgrade(canvas):
        generation = canvas.generation_json or {}
        layout, detail = _resolve_seeds_from_generation(generation)
        regenerate_canvas_background(
            canvas,
            mode="full",
            layout_seed=layout,
            detail_seed=detail,
            settings=settings,
        )
    elif _generation_needs_upgrade(canvas):
        generation = canvas.generation_json or {}
        layout, detail = _resolve_seeds_from_generation(generation)
        regenerate_canvas_background(
            canvas,
            mode="full",
            layout_seed=layout,
            detail_seed=detail,
            settings=settings,
        )
    return canvas


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------
def _canvas_dict(canvas: MapCanvas, *, for_player: bool = False) -> dict:
    generation = canvas.generation_json or {}
    if generation.get("cell_graph") and int(generation.get("schema_version") or 0) >= V6_SCHEMA_VERSION:
        generation = _refresh_terrain_grid_from_cell_graph(generation, canvas.scope)
    if for_player:
        generation = strip_editor_meta_for_player(generation)
    return {
        "id": canvas.id,
        "scope": canvas.scope,
        "city_id": canvas.city_id,
        "shop_id": canvas.shop_id,
        "source_type": canvas.source_type,
        "has_image": bool(canvas.image_path),
        "has_underlay": False if for_player else bool(getattr(canvas, "underlay_path", None)),
        "generation": generation,
        "width": canvas.width,
        "height": canvas.height,
    }


def _poi_dict(poi: MapPointOfInterest) -> dict:
    return {
        "id": poi.id,
        "label": poi.label,
        "note": poi.note or "",
        "x": poi.x,
        "y": poi.y,
        "visible_to_players": bool(poi.visible_to_players),
    }


def _encounter_dict(encounter: BattleEncounter) -> dict:
    return {
        "id": encounter.id,
        "name": encounter.name,
        "status": encounter.status,
        "visible_to_players": bool(encounter.visible_to_players),
        "map_canvas_id": encounter.map_canvas_id,
        "map_x": encounter.map_x,
        "map_y": encounter.map_y,
    }


def _visible_encounters_for_canvas(campaign_id: int, canvas_id: int) -> list[BattleEncounter]:
    return (
        BattleEncounter.query.filter_by(campaign_id=campaign_id, map_canvas_id=canvas_id)
        .filter(
            BattleEncounter.status != "ended",
            BattleEncounter.visible_to_players.is_(True),
            BattleEncounter.map_x.isnot(None),
            BattleEncounter.map_y.isnot(None),
        )
        .order_by(BattleEncounter.name, BattleEncounter.id)
        .all()
    )


def build_world_map_payload(campaign_id: int, *, for_player: bool = False) -> dict:
    """World canvas + campaign cities.

    Unmapped cities are returned for list controls, but their coordinates are
    ``None`` and they should not render as dots until the GM explicitly adds
    them to the map.
    """
    from app.models import Campaign

    campaign = Campaign.query.get(campaign_id)
    canvas = get_or_create_world_canvas(campaign_id)
    cities = (
        City.query.filter_by(campaign_id=campaign_id).order_by(City.name).all()
    )
    regions = (
        Region.query.filter_by(campaign_id=campaign_id).order_by(Region.name).all()
    )
    markers = MapMarker.query.filter_by(
        canvas_id=canvas.id, entity_type="city"
    ).all()
    marker_by_city = {m.city_id: m for m in markers}

    entities = []
    for c in cities:
        saved = marker_by_city.get(c.city_id)
        if saved is not None:
            x, y, is_on_map = saved.x, saved.y, True
            cell_info = snap_marker_to_cell(canvas.generation_json, saved.x, saved.y)
        else:
            x, y, is_on_map = None, None, False
            cell_info = None
        entity = {
            "entity_type": "city",
            "id": c.city_id,
            "name": c.name,
            "region_id": c.region_id,
            "region": c.region_obj.name if c.region_obj else (c.region or None),
            "owner_player_id": c.owner_player_id,
            "x": x,
            "y": y,
            "is_on_map": is_on_map,
            "is_suggested": False,
            "summary": _city_summary(c, campaign, for_player=for_player),
        }
        if cell_info:
            entity["cell_id"] = cell_info["cell_id"]
            entity["terrain_label"] = cell_info["terrain_label"]
        entities.append(entity)

    poi_query = MapPointOfInterest.query.filter_by(
        campaign_id=campaign_id,
        canvas_id=canvas.id,
    )
    if for_player:
        poi_query = poi_query.filter(MapPointOfInterest.visible_to_players.is_(True))
    pois = poi_query.order_by(MapPointOfInterest.label, MapPointOfInterest.id).all()

    payload = {
        "canvas": _canvas_dict(canvas, for_player=for_player),
        "entities": entities,
        "regions": [
            _region_map_entry(region, campaign, for_player=for_player)
            for region in regions
        ],
        "people": _people_directory(campaign_id, campaign, for_player=for_player),
        "points_of_interest": [_poi_dict(poi) for poi in pois],
    }
    if for_player:
        payload["encounters"] = [
            _encounter_dict(encounter)
            for encounter in _visible_encounters_for_canvas(campaign_id, canvas.id)
        ]
    return payload


def build_city_map_payload(campaign_id: int, city: City, *, for_player: bool = False) -> dict:
    """City canvas + shops attached to that city.

    Unmapped shops are returned for list controls, but do not render until the
    GM explicitly adds them to this city map.
    """
    from app.models import Campaign

    campaign = Campaign.query.get(campaign_id)
    canvas = get_or_create_city_canvas(campaign_id, city)
    shops = sorted(city.shops, key=lambda s: (s.name or "").lower())
    markers = MapMarker.query.filter_by(
        canvas_id=canvas.id, entity_type="shop"
    ).all()
    marker_by_shop = {m.shop_id: m for m in markers}
    poi_query = MapPointOfInterest.query.filter_by(
        campaign_id=campaign_id,
        canvas_id=canvas.id,
    )
    if for_player:
        poi_query = poi_query.filter(MapPointOfInterest.visible_to_players.is_(True))
    pois = poi_query.order_by(MapPointOfInterest.label, MapPointOfInterest.id).all()

    entities = []
    for s in shops:
        saved = marker_by_shop.get(s.shop_id)
        if saved is not None:
            x, y, is_on_map = saved.x, saved.y, True
        else:
            x, y, is_on_map = None, None, False
        entities.append(
            {
                "entity_type": "shop",
                "id": s.shop_id,
                "name": s.name,
                "type": s.type,
                "owner_player_id": s.owner_player_id,
                "x": x,
                "y": y,
                "is_on_map": is_on_map,
                "is_suggested": False,
                "summary": _shop_summary(s, campaign, for_player=for_player),
            }
        )

    payload = {
        "canvas": _canvas_dict(canvas, for_player=for_player),
        "city": {"id": city.city_id, "name": city.name},
        "entities": entities,
        "people": _people_directory(campaign_id, campaign, for_player=for_player),
        "points_of_interest": [_poi_dict(poi) for poi in pois],
    }
    if for_player:
        payload["encounters"] = [
            _encounter_dict(encounter)
            for encounter in _visible_encounters_for_canvas(campaign_id, canvas.id)
        ]
    return payload


def build_shop_map_payload(
    campaign_id: int,
    shop: Shop,
    *,
    city: City | None = None,
    for_player: bool = False,
) -> dict:
    """Shop interior canvas for one campaign shop."""
    canvas = get_or_create_shop_canvas(campaign_id, shop)
    linked_city = city
    if linked_city is None and shop.cities:
        linked_city = sorted(shop.cities, key=lambda c: (c.name or "").lower())[0]
    payload = {
        "canvas": _canvas_dict(canvas, for_player=for_player),
        "shop": {
            "id": shop.shop_id,
            "name": shop.name,
            "type": shop.type,
        },
        "entities": [],
        "points_of_interest": [],
    }
    if linked_city is not None:
        payload["city"] = {"id": linked_city.city_id, "name": linked_city.name}
    if for_player:
        payload["encounters"] = []
    return payload


def compendium_map_status(campaign_id: int) -> dict[str, set[int] | set[tuple[int, int]]]:
    """Map placement flags for GM compendium list buttons."""
    cities_on_world: set[int] = set()
    world_canvas = MapCanvas.query.filter_by(
        campaign_id=campaign_id, scope=WORLD_SCOPE
    ).first()
    if world_canvas is not None:
        for row in MapMarker.query.filter_by(
            canvas_id=world_canvas.id, entity_type="city"
        ).all():
            if row.city_id is not None:
                cities_on_world.add(int(row.city_id))

    shops_on_city: set[tuple[int, int]] = set()
    city_canvases = MapCanvas.query.filter_by(
        campaign_id=campaign_id, scope="city"
    ).all()
    if city_canvases:
        canvas_city = {c.id: c.city_id for c in city_canvases if c.city_id is not None}
        canvas_ids = list(canvas_city.keys())
        if canvas_ids:
            for row in MapMarker.query.filter(
                MapMarker.canvas_id.in_(canvas_ids),
                MapMarker.entity_type == "shop",
            ).all():
                city_id = canvas_city.get(row.canvas_id)
                if row.shop_id is not None and city_id is not None:
                    shops_on_city.add((int(row.shop_id), int(city_id)))

    return {
        "cities_on_world": cities_on_world,
        "shops_on_city": shops_on_city,
    }


def _is_gm_region_boundary(feature: dict) -> bool:
    return (
        isinstance(feature, dict)
        and feature.get("type") == "region_tint"
        and feature.get("region_id") is not None
    )


def region_boundary_from_generation(
    generation: dict | None, region_id: int
) -> list[list[float]] | None:
    """Return normalized boundary points for a campaign region, if defined."""
    if not generation:
        return None
    for feature in generation.get("features") or []:
        if _is_gm_region_boundary(feature) and int(feature["region_id"]) == int(region_id):
            points = feature.get("points")
            if isinstance(points, list) and len(points) >= 3:
                return points
    return None


def regions_with_boundaries(campaign_id: int) -> set[int]:
    """Region IDs that have a GM-drawn boundary on the world map."""
    world_canvas = MapCanvas.query.filter_by(
        campaign_id=campaign_id, scope=WORLD_SCOPE
    ).first()
    if world_canvas is None or not world_canvas.generation_json:
        return set()
    found: set[int] = set()
    for feature in (world_canvas.generation_json or {}).get("features") or []:
        if not _is_gm_region_boundary(feature):
            continue
        points = feature.get("points")
        if isinstance(points, list) and len(points) >= 3:
            found.add(int(feature["region_id"]))
    return found


DEFAULT_NATION_MAIN_COLOR = "#c084fc"
DEFAULT_NATION_BORDER_COLOR = "#7c3aed"


def _nation_colors_for_region(campaign_id: int, region_id: int) -> tuple[str, str]:
    from app.models import Region

    region = Region.query.filter_by(id=region_id, campaign_id=campaign_id).first()
    if region is None:
        return DEFAULT_NATION_MAIN_COLOR, DEFAULT_NATION_BORDER_COLOR
    return (
        region.main_color or DEFAULT_NATION_MAIN_COLOR,
        region.secondary_color or DEFAULT_NATION_BORDER_COLOR,
    )


def sync_region_map_appearance(campaign_id: int, region) -> bool:
    """Copy nation fill/border colors onto the world-map region_tint feature."""
    canvas = MapCanvas.query.filter_by(
        campaign_id=campaign_id, scope=WORLD_SCOPE
    ).first()
    if canvas is None or not canvas.generation_json:
        return False
    generation = dict(canvas.generation_json)
    features = list(generation.get("features") or [])
    main_color, secondary_color = _nation_colors_for_region(campaign_id, region.id)
    changed = False
    updated: list[dict] = []
    for feature in features:
        if (
            _is_gm_region_boundary(feature)
            and int(feature.get("region_id", -1)) == int(region.id)
        ):
            merged = dict(feature)
            merged["main_color"] = main_color
            merged["secondary_color"] = secondary_color
            updated.append(merged)
            changed = True
        else:
            updated.append(feature)
    if not changed:
        return False
    generation["features"] = updated
    save_canvas_generation(canvas, generation)
    return True


def upsert_region_boundary(
    campaign_id: int,
    region_id: int,
    region_name: str,
    points: list[list[float]] | None,
) -> dict:
    """Create, update, or clear a GM-drawn region boundary on the world map."""
    canvas = get_or_create_world_canvas(campaign_id)
    settings = _settings_for_campaign(campaign_id)
    generation = _generation_for_canvas_metadata(canvas, settings)
    features = [
        f
        for f in (generation.get("features") or [])
        if not (
            _is_gm_region_boundary(f)
            and int(f.get("region_id", -1)) == int(region_id)
        )
    ]
    if points:
        main_color, secondary_color = _nation_colors_for_region(campaign_id, region_id)
        validated = _validate_feature(
            {
                "type": "region_tint",
                "region_id": region_id,
                "label": region_name,
                "points": points,
                "main_color": main_color,
                "secondary_color": secondary_color,
            },
            WORLD_SCOPE,
        )
        features.append(validated)
    generation["features"] = features
    save_canvas_generation(canvas, generation)
    return generation


# ---------------------------------------------------------------------------
# Marker upsert
# ---------------------------------------------------------------------------
def upsert_marker(
    campaign_id: int,
    canvas: MapCanvas,
    entity_type: str,
    entity_id: int,
    x: float,
    y: float,
) -> MapMarker:
    """Create or move a marker. Validates bounds, scope, and ownership.

    The canvas must already be resolved against the active campaign by the
    caller; this function re-checks anyway, then enforces canvas-scope
    rules: world canvases accept only city markers for campaign cities;
    city canvases accept only shop markers for shops attached to that city.

    Flushes; caller commits.
    """
    if canvas.campaign_id != campaign_id:
        raise LookupError("Canvas does not belong to the active campaign.")
    if not (0.0 <= x <= 1.0) or not (0.0 <= y <= 1.0):
        raise MapValidationError("Coordinates must be between 0.0 and 1.0.")

    if entity_type == "city":
        if canvas.scope != WORLD_SCOPE:
            raise MapValidationError("City markers belong on the world map.")
        city = City.query.filter_by(
            city_id=entity_id, campaign_id=campaign_id
        ).first()
        if city is None:
            raise LookupError("City not found in this campaign.")
        marker = MapMarker.query.filter_by(
            canvas_id=canvas.id, city_id=city.city_id
        ).first()
        if marker is None:
            marker = MapMarker(
                canvas_id=canvas.id,
                campaign_id=campaign_id,
                entity_type="city",
                city_id=city.city_id,
            )
            db.session.add(marker)
    elif entity_type == "shop":
        if canvas.scope != CITY_SCOPE:
            raise MapValidationError("Shop markers belong on a city map.")
        shop = Shop.query.filter_by(
            shop_id=entity_id, campaign_id=campaign_id
        ).first()
        if shop is None:
            raise LookupError("Shop not found in this campaign.")
        if canvas.city_id not in [c.city_id for c in shop.cities]:
            raise MapValidationError("Shop is not attached to this city.")
        marker = MapMarker.query.filter_by(
            canvas_id=canvas.id, shop_id=shop.shop_id
        ).first()
        if marker is None:
            marker = MapMarker(
                canvas_id=canvas.id,
                campaign_id=campaign_id,
                entity_type="shop",
                shop_id=shop.shop_id,
            )
            db.session.add(marker)
    else:
        raise MapValidationError("entity_type must be 'city' or 'shop'.")

    marker.x = float(x)
    marker.y = float(y)
    db.session.flush()
    return marker


def remove_marker(
    campaign_id: int,
    canvas: MapCanvas,
    entity_type: str,
    entity_id: int,
) -> bool:
    """Remove a city/shop marker from a validated campaign canvas."""
    if canvas.campaign_id != campaign_id:
        raise LookupError("Canvas does not belong to the active campaign.")

    if entity_type == "city":
        if canvas.scope != WORLD_SCOPE:
            raise MapValidationError("City markers belong on the world map.")
        city = City.query.filter_by(city_id=entity_id, campaign_id=campaign_id).first()
        if city is None:
            raise LookupError("City not found in this campaign.")
        marker = MapMarker.query.filter_by(
            canvas_id=canvas.id, city_id=city.city_id
        ).first()
    elif entity_type == "shop":
        if canvas.scope != CITY_SCOPE:
            raise MapValidationError("Shop markers belong on a city map.")
        shop = Shop.query.filter_by(shop_id=entity_id, campaign_id=campaign_id).first()
        if shop is None:
            raise LookupError("Shop not found in this campaign.")
        if canvas.city_id not in [c.city_id for c in shop.cities]:
            raise MapValidationError("Shop is not attached to this city.")
        marker = MapMarker.query.filter_by(
            canvas_id=canvas.id, shop_id=shop.shop_id
        ).first()
    else:
        raise MapValidationError("entity_type must be 'city' or 'shop'.")

    if marker is None:
        return False
    db.session.delete(marker)
    db.session.flush()
    return True


def upsert_poi(
    campaign_id: int,
    canvas: MapCanvas,
    label: str,
    note: str,
    x: float,
    y: float,
    visible_to_players: bool = False,
    poi_id: int | None = None,
) -> MapPointOfInterest:
    """Create or update a GM-authored world-map point of interest."""
    if canvas.campaign_id != campaign_id:
        raise LookupError("Canvas does not belong to the active campaign.")
    if canvas.scope != WORLD_SCOPE:
        raise MapValidationError("Points of interest belong on the world map.")
    if not (0.0 <= x <= 1.0) or not (0.0 <= y <= 1.0):
        raise MapValidationError("Coordinates must be between 0.0 and 1.0.")

    label = (label or "").strip()
    note = (note or "").strip()
    if not label:
        raise MapValidationError("POI label is required.")
    if len(label) > 120:
        raise MapValidationError("POI label must be 120 characters or fewer.")
    if len(note) > 2000:
        raise MapValidationError("POI note must be 2000 characters or fewer.")

    if poi_id is not None:
        poi = MapPointOfInterest.query.filter_by(
            id=poi_id, campaign_id=campaign_id, canvas_id=canvas.id
        ).first()
        if poi is None:
            raise LookupError("Point of interest not found in this campaign.")
    else:
        poi = MapPointOfInterest(canvas_id=canvas.id, campaign_id=campaign_id)
        db.session.add(poi)

    poi.label = label
    poi.note = note
    poi.x = float(x)
    poi.y = float(y)
    poi.visible_to_players = bool(visible_to_players)
    db.session.flush()
    return poi


def remove_poi(campaign_id: int, canvas: MapCanvas, poi_id: int) -> bool:
    """Remove a GM-authored point of interest from the world map."""
    if canvas.campaign_id != campaign_id:
        raise LookupError("Canvas does not belong to the active campaign.")
    if canvas.scope != WORLD_SCOPE:
        raise MapValidationError("Points of interest belong on the world map.")
    poi = MapPointOfInterest.query.filter_by(
        id=poi_id, campaign_id=campaign_id, canvas_id=canvas.id
    ).first()
    if poi is None:
        return False
    db.session.delete(poi)
    db.session.flush()
    return True
