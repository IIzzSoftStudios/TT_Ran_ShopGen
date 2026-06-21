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
import logging
import math
import os
import random
from pathlib import Path

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
    Shop,
    ShopInventory,
)
from app.services import species_compendium_service

log = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 4 * 1024 * 1024  # 4 MB raw upload ceiling
MAX_MAP_EDGE = 2048  # uploaded backgrounds are bounded to this edge
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}

WORLD_SCOPE = "world"
CITY_SCOPE = "city"

GENERATION_SCHEMA_VERSION = 3


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


def save_map_upload(canvas: MapCanvas, file_storage) -> None:
    """Validate, bound, and persist an uploaded background as WebP.

    Mirrors the avatar pipeline (`app/services/user_avatar.py`) but with a
    larger size budget appropriate for map art. Mutates the canvas row;
    caller commits.
    """
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

    img = img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB")
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
) -> list[list[float]]:
    """Generate an irregular normalized polygon around a center."""
    import math

    points = []
    for idx in range(count):
        angle = (math.tau * idx / count) + rng.uniform(-0.16, 0.16)
        wobble = rng.uniform(0.72, 1.22)
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
) -> list[list[float]]:
    """Generate a naturally bent line between two normalized points."""
    points = []
    for idx in range(bends + 2):
        t = idx / (bends + 1)
        x = start[0] + (end[0] - start[0]) * t + rng.uniform(-jitter, jitter)
        y = start[1] + (end[1] - start[1]) * t + rng.uniform(-jitter, jitter)
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


def map_generation_profile(settings: dict | None = None) -> dict:
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
    return {
        "landmass_scale": max(1.0, min(10.0, landmass)),
        "waterways": max(0.0, min(10.0, waterways)),
        "terrain_roughness": max(0.0, min(10.0, roughness)),
        "region_density": max(1.0, min(10.0, regions)),
        "city_density": max(1.0, min(40.0, cities)),
        "economy_density": max(0.0, min(10.0, (item_pool / 50.0) + (items_per_shop / 5.0))),
        "city_complexity": max(1.0, min(20.0, city_variation)),
        "tech_magic_balance": max(0.0, min(10.0, tech_magic)),
    }


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


def _city_summary(city: City) -> dict:
    population = int(city.population or 0)
    goods = _top_goods_for_city(city)
    return {
        "population": population,
        "species_population": species_compendium_service.city_species_population(
            city.campaign_id, city.city_id, population
        ),
        "top_goods_by_price": goods["by_price"],
        "top_goods_by_average_volume": goods["by_average_volume"],
    }


def _shop_summary(shop: Shop) -> dict:
    goods = _top_goods_for_shop(shop)
    return {
        "top_goods_by_price": goods["by_price"],
        "top_goods_by_average_volume": goods["by_average_volume"],
    }


def generate_canvas_background(scope: str, seed: int, profile: dict | None = None) -> dict:
    """Deterministic lightweight metadata the client renders as a backdrop."""
    rng = random.Random(seed)
    profile = profile or map_generation_profile(None)
    if scope == WORLD_SCOPE:
        land = profile["landmass_scale"]
        water = profile["waterways"]
        rough = profile["terrain_roughness"]
        region_density = profile["region_density"]
        economy = profile["economy_density"]
        tech = profile["tech_magic_balance"]
        city_density = profile["city_density"]
        palette_options = ["parchment", "verdant", "ashen"]
        if water >= 7:
            palette_options.extend(["verdant", "parchment"])
        if rough >= 7 or tech >= 7:
            palette_options.extend(["ashen", "slate"])
        palette = rng.choice(palette_options)
        land_rx = 0.24 + (land / 10.0) * 0.2
        land_ry = 0.22 + (land / 10.0) * 0.18
        wobble_points = int(18 + rough)
        hubs = _settlement_hubs(rng, max(3, int(2 + city_density / 5)))
        features = [
            {
                "type": "landmass",
                "points": _blob_points(rng, 0.48, 0.52, land_rx, land_ry, wobble_points),
            }
        ]
        mountain_paths: list[list[list[float]]] = []
        for _ in range(max(1, int(1 + rough / 2))):
            start = (rng.uniform(0.16, 0.34), rng.uniform(0.16, 0.78))
            end = (rng.uniform(0.58, 0.86), rng.uniform(0.18, 0.76))
            path = _polyline(
                rng,
                start,
                end,
                rng.randint(3, 5),
                0.035 + rough / 220,
            )
            mountain_paths.append(path)
            features.append({"type": "mountain_range", "points": path})

        for _ in range(max(1, int(1 + rough / 2 + (10 - land) / 4))):
            angle = rng.uniform(0, math.tau)
            cx = 0.5 + math.cos(angle) * rng.uniform(land_rx + 0.04, 0.48)
            cy = 0.52 + math.sin(angle) * rng.uniform(land_ry + 0.04, 0.42)
            features.append(
                {
                    "type": "island",
                    "points": _blob_points(
                        rng,
                        cx,
                        cy,
                        rng.uniform(0.04, 0.09),
                        rng.uniform(0.035, 0.08),
                        rng.randint(8, 13),
                    ),
                }
            )
        for _ in range(max(0, int(1 + water / 2))):
            if mountain_paths:
                source_path = rng.choice(mountain_paths)
                source = tuple(rng.choice(source_path[1:-1] or source_path))
            else:
                source = (rng.uniform(0.25, 0.75), rng.uniform(0.12, 0.35))
            mouth_side = "south" if source[1] < 0.55 else rng.choice(("east", "west"))
            mouth = _edge_point(rng, mouth_side)
            features.append(
                {
                    "type": "river",
                    "points": _polyline(
                        rng,
                        source,
                        mouth,
                        rng.randint(3, 6),
                        0.04 + (water / 10.0) * 0.06,
                    ),
                }
            )
        route_count = min(len(hubs) - 1, max(1, int(1 + economy / 3 + city_density / 18)))
        for idx in range(route_count):
            start = hubs[idx]
            end = hubs[idx + 1]
            features.append(
                {
                    "type": "trade_route",
                    "points": _polyline(
                        rng,
                        start,
                        end,
                        rng.randint(2, 4),
                        0.025 + economy / 260,
                    ),
                }
            )
        for _ in range(max(1, int(2 + rough / 2 + max(0, 5 - tech) / 2))):
            anchor = rng.choice(hubs)
            features.append(
                {
                    "type": "forest",
                    "points": _blob_points(
                        rng,
                        anchor[0] + rng.uniform(-0.18, 0.18),
                        anchor[1] + rng.uniform(-0.18, 0.18),
                        rng.uniform(0.05, 0.12),
                        rng.uniform(0.04, 0.1),
                        rng.randint(7, 12),
                    ),
                }
            )
        for idx in range(max(1, int(round(region_density)))):
            center = hubs[idx % len(hubs)]
            features.append(
                {
                    "type": "region_tint",
                    "label": f"Region {idx + 1}",
                    "points": _blob_points(
                        rng,
                        center[0],
                        center[1],
                        rng.uniform(0.12, 0.2),
                        rng.uniform(0.1, 0.18),
                        rng.randint(7, 11),
                    ),
                }
            )
    else:
        economy = profile["economy_density"]
        city_complexity = profile["city_complexity"]
        water = profile["waterways"]
        tech = profile["tech_magic_balance"]
        palette_options = ["slate", "sandstone", "timber"]
        if tech <= 3:
            palette_options.extend(["timber", "sandstone"])
        elif tech >= 7:
            palette_options.extend(["slate", "ashen"])
        palette = rng.choice(palette_options)
        wall_radius = 0.28 + min(0.12, city_complexity / 100.0 + economy / 100.0)
        wall = _blob_points(rng, 0.5, 0.52, wall_radius, wall_radius * 0.9, 18)
        features = [{"type": "city_wall", "points": wall}]
        district_count = max(3, int(3 + city_complexity / 3 + economy / 3))
        center = (0.5, 0.52)
        district_centers: list[tuple[float, float]] = []
        district_labels = ["Market", "Docks", "Guilds", "Temple", "Commons", "Old Town"]
        if economy >= 6:
            district_labels.extend(["Bazaar", "Warehouse", "Artisans"])
        if tech >= 7:
            district_labels.extend(["Works", "Rail Yard", "Foundry"])
        if tech <= 3:
            district_labels.extend(["Sanctum", "Shrine", "Arcane Ward"])
        for idx in range(district_count):
            angle = (math.tau * idx / district_count) + rng.uniform(-0.18, 0.18)
            radius = rng.uniform(0.13, wall_radius * 0.82)
            dcx, dcy = _ring_point(center[0], center[1], radius, angle)
            district_centers.append((dcx, dcy))
            features.append(
                {
                    "type": "district",
                    "label": rng.choice(district_labels),
                    "points": _blob_points(
                        rng,
                        dcx,
                        dcy,
                        rng.uniform(0.08, 0.15),
                        rng.uniform(0.06, 0.13),
                        rng.randint(6, 10),
                    ),
                }
            )
        road_count = max(3, int(3 + economy / 2 + tech / 3))
        for target in district_centers[:road_count]:
            features.append(
                {
                    "type": "road",
                    "points": _polyline(
                        rng,
                        center,
                        target,
                        rng.randint(1, 3),
                        0.018 + max(0, 8 - tech) / 260,
                    ),
                }
            )
        if len(district_centers) >= 4:
            ring_points = [
                _round_point(x, y)
                for x, y in sorted(
                    district_centers,
                    key=lambda p: math.atan2(p[1] - center[1], p[0] - center[0]),
                )
            ]
            ring_points.append(ring_points[0])
            features.append({"type": "road", "points": ring_points})
        for _ in range(max(0, int(water / 4))):
            canal_y = rng.uniform(0.28, 0.74)
            features.append(
                {
                    "type": "canal",
                    "points": _polyline(
                        rng,
                        (0.08, canal_y),
                        (0.92, min(0.9, max(0.1, canal_y + rng.uniform(-0.18, 0.18)))),
                        rng.randint(3, 5),
                        0.05,
                    ),
                }
            )
        features.append(
            {
                "type": "plaza",
                "x": round(center[0] + rng.uniform(-0.03, 0.03), 4),
                "y": round(center[1] + rng.uniform(-0.03, 0.03), 4),
                "size": round(rng.uniform(0.06, 0.1) + economy / 180, 4),
            }
        )
        park_count = max(1, int(1 + max(0, 6 - economy) / 2 + max(0, 4 - tech) / 3))
        for _ in range(park_count):
            if district_centers:
                far = max(
                    district_centers,
                    key=lambda p: (p[0] - center[0]) ** 2 + (p[1] - center[1]) ** 2,
                )
                px = far[0] + rng.uniform(-0.08, 0.08)
                py = far[1] + rng.uniform(-0.08, 0.08)
            else:
                px, py = rng.uniform(0.2, 0.8), rng.uniform(0.2, 0.8)
            features.append(
                {
                    "type": "park",
                    "points": _blob_points(
                        rng,
                        px,
                        py,
                        rng.uniform(0.04, 0.08),
                        rng.uniform(0.035, 0.07),
                        rng.randint(6, 10),
                    ),
                }
            )
    return {
        "schema_version": GENERATION_SCHEMA_VERSION,
        "seed": seed,
        "scope": scope,
        "palette": palette,
        "profile": profile,
        "features": features,
    }


def _canvas_seed(campaign_id: int, city_id: int | None = None) -> int:
    """Stable per-canvas seed; repeatable across processes (no hash())."""
    return (campaign_id * 1_000_003 + (city_id or 0)) & 0x7FFFFFFF


def regenerate_canvas_background(
    canvas: MapCanvas,
    seed: int | None = None,
    settings: dict | None = None,
) -> None:
    """Switch a canvas back to a (new) generated background. Caller commits."""
    if seed is None:
        # New random seed so "regenerate" produces a different look.
        seed = random.SystemRandom().randint(0, 0x7FFFFFFF)
    delete_map_image(canvas)
    canvas.source_type = "generated"
    canvas.image_path = None
    if settings is None:
        settings = _settings_for_campaign(canvas.campaign_id)
    canvas.generation_json = generate_canvas_background(
        canvas.scope,
        seed,
        map_generation_profile(settings),
    )
    canvas.width = 1024
    canvas.height = 1024


def _generation_needs_upgrade(canvas: MapCanvas) -> bool:
    if canvas.source_type != "generated":
        return False
    generation = canvas.generation_json or {}
    return int(generation.get("schema_version") or 0) < GENERATION_SCHEMA_VERSION


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
        regenerate_canvas_background(
            canvas,
            seed=int(generation.get("seed") or seed or _canvas_seed(campaign_id)),
            settings=settings,
        )
    return canvas


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
                map_generation_profile(settings),
            ),
        )
        db.session.add(canvas)
        db.session.flush()
    elif _generation_needs_upgrade(canvas):
        generation = canvas.generation_json or {}
        regenerate_canvas_background(
            canvas,
            seed=int(generation.get("seed") or _canvas_seed(campaign_id, city.city_id)),
            settings=settings,
        )
    return canvas


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------
def _canvas_dict(canvas: MapCanvas) -> dict:
    return {
        "id": canvas.id,
        "scope": canvas.scope,
        "city_id": canvas.city_id,
        "source_type": canvas.source_type,
        "has_image": bool(canvas.image_path),
        "generation": canvas.generation_json or {},
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
    canvas = get_or_create_world_canvas(campaign_id)
    cities = (
        City.query.filter_by(campaign_id=campaign_id).order_by(City.name).all()
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
        else:
            x, y, is_on_map = None, None, False
        entities.append(
            {
                "entity_type": "city",
                "id": c.city_id,
                "name": c.name,
                "region_id": c.region_id,
                "region": c.region_obj.name if c.region_obj else (c.region or None),
                "x": x,
                "y": y,
                "is_on_map": is_on_map,
                "is_suggested": False,
                "summary": _city_summary(c),
            }
        )

    poi_query = MapPointOfInterest.query.filter_by(
        campaign_id=campaign_id,
        canvas_id=canvas.id,
    )
    if for_player:
        poi_query = poi_query.filter(MapPointOfInterest.visible_to_players.is_(True))
    pois = poi_query.order_by(MapPointOfInterest.label, MapPointOfInterest.id).all()

    payload = {
        "canvas": _canvas_dict(canvas),
        "entities": entities,
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
                "x": x,
                "y": y,
                "is_on_map": is_on_map,
                "is_suggested": False,
                "summary": _shop_summary(s),
            }
        )

    payload = {
        "canvas": _canvas_dict(canvas),
        "city": {"id": city.city_id, "name": city.name},
        "entities": entities,
        "points_of_interest": [_poi_dict(poi) for poi in pois],
    }
    if for_player:
        payload["encounters"] = [
            _encounter_dict(encounter)
            for encounter in _visible_encounters_for_canvas(campaign_id, canvas.id)
        ]
    return payload


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
