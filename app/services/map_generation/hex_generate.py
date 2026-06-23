"""Procedural hex-grid world generation (Worldographer-style frequencies + clustering)."""

from __future__ import annotations

import math
import random
from collections import deque
from typing import Any, Callable, Literal

from app.services.map_generation import hex_grid as hg

LandForm = Literal["large_continents", "archipelago", "scattered"]


def _pct(profile: dict, key: str, default: float) -> float:
    raw = profile.get(key, default)
    try:
        val = float(raw)
    except (TypeError, ValueError):
        val = default
    if val > 1.0:
        val = val / 100.0
    return max(0.0, min(1.0, val))


def _land_form(profile: dict) -> LandForm:
    form = str(profile.get("land_form", "large_continents")).strip().lower()
    if form in ("archipelago", "scattered", "large_continents"):
        return form  # type: ignore[return-value]
    scale = float(profile.get("landmass_scale", 6))
    if scale >= 7:
        return "large_continents"
    if scale <= 4:
        return "archipelago"
    return "scattered"


def _grow_blob(
    cells: list[int],
    width: int,
    height: int,
    seeds: list[tuple[int, int]],
    target_add: int,
    cluster: float,
    rng: random.Random,
) -> None:
    added = 0
    frontier: deque[tuple[int, int]] = deque(seeds)
    seen = set(seeds)
    while added < target_add and frontier:
        q, r = frontier.popleft()
        if not hg.in_bounds(q, r, width, height):
            continue
        idx = hg.cell_index(q, r, width)
        if not hg.land_code(cells[idx]):
            cells[idx] = 1
            added += 1
        nbs = list(hg.neighbors(q, r))
        rng.shuffle(nbs)
        if cluster > 0.5:
            nbs.sort(
                key=lambda nb: -sum(
                    1
                    for nq, nr in hg.neighbors(nb[0], nb[1])
                    if hg.in_bounds(nq, nr, width, height)
                    and hg.land_code(cells[hg.cell_index(nq, nr, width)])
                )
            )
        for nq, nr in nbs:
            if (nq, nr) in seen:
                continue
            if not hg.in_bounds(nq, nr, width, height):
                continue
            if rng.random() > 0.15 + cluster * 0.7:
                continue
            seen.add((nq, nr))
            frontier.append((nq, nr))


def _place_land(
    cells: list[int],
    width: int,
    height: int,
    profile: dict,
    rng: random.Random,
) -> None:
    total = width * height
    land_freq = _pct(profile, "land_frequency", 0.55)
    if "land_frequency" not in profile and profile.get("landmass_scale") is not None:
        land_freq = 0.35 + float(profile.get("landmass_scale", 6)) / 20.0
    if land_freq <= 0:
        return
    target_land = max(1, int(round(total * land_freq)))
    cluster = _pct(profile, "cluster_percent", 0.70)
    form = _land_form(profile)

    explicit_islands = profile.get("island_count", 0)
    island_seeds = 0
    if explicit_islands and float(explicit_islands) >= 1:
        form = "archipelago"
        island_seeds = max(1, int(round(float(explicit_islands))))

    seeds: list[tuple[int, int]] = []
    if explicit_islands and float(explicit_islands) >= 1 and form == "archipelago":
        count = island_seeds
        margin = max(2, min(width, height) // 8)
        for i in range(count):
            angle = (math.tau * i / max(1, count)) + rng.uniform(-0.2, 0.2)
            q = int(width / 2 + math.cos(angle) * (width / 2 - margin))
            r = int(height / 2 + math.sin(angle) * (height / 2 - margin))
            q = max(margin, min(width - margin - 1, q))
            r = max(margin, min(height - margin - 1, r))
            seeds.append((q, r))
        per_island = max(6, min(14, target_land // max(1, count * 2)))
        for seed in seeds:
            _grow_blob(cells, width, height, [seed], per_island, 0.35, rng)
        return

    if form == "large_continents":
        seeds.append((width // 2, height // 2))
        for _ in range(rng.randint(1, 3)):
            seeds.append(
                (rng.randint(width // 4, 3 * width // 4), rng.randint(height // 4, 3 * height // 4))
            )
    elif form == "archipelago":
        count = island_seeds if explicit_islands and float(explicit_islands) >= 1 else max(8, int(land_freq * total / 80))
        for _ in range(count):
            seeds.append((rng.randint(0, width - 1), rng.randint(0, height - 1)))
    else:
        count = max(4, int(land_freq * total / 200))
        for _ in range(count):
            seeds.append((rng.randint(0, width - 1), rng.randint(0, height - 1)))

    _grow_blob(cells, width, height, seeds, target_land, cluster, rng)


def _apply_biomes(
    cells: list[int],
    width: int,
    height: int,
    profile: dict,
    rng: random.Random,
) -> None:
    mountain_p = _pct(profile, "mountain_frequency", 0.08)
    if "mountain_frequency" not in profile:
        mountain_p = float(profile.get("terrain_roughness", 5)) / 100.0
    forest_p = _pct(profile, "vegetation_frequency", 0.18)
    grassland_p = _pct(profile, "grassland_frequency", 0.22)
    hills_p = _pct(profile, "hills_frequency", 0.12)
    desert_p = _pct(profile, "desert_frequency", 0.15)
    swamp_p = _pct(profile, "swamp_frequency", 0.05)
    cluster = _pct(profile, "cluster_percent", 0.70)

    land_coords = [
        (q, r)
        for q, r in hg.iter_hexes(width, height)
        if hg.land_code(cells[hg.cell_index(q, r, width)])
    ]
    rng.shuffle(land_coords)

    def neighbor_same(q: int, r: int, code: int) -> int:
        return sum(
            1
            for nq, nr in hg.neighbors(q, r)
            if hg.in_bounds(nq, nr, width, height)
            and cells[hg.cell_index(nq, nr, width)] == code
        )

    for q, r in land_coords:
        if rng.random() > mountain_p:
            continue
        if neighbor_same(q, r, 2) or rng.random() < cluster:
            cells[hg.cell_index(q, r, width)] = 2

    for q, r in land_coords:
        idx = hg.cell_index(q, r, width)
        if cells[idx] != 1:
            continue
        if rng.random() > hills_p:
            continue
        if neighbor_same(q, r, 6) or rng.random() < cluster:
            cells[idx] = 6

    for q, r in land_coords:
        idx = hg.cell_index(q, r, width)
        if cells[idx] != 1:
            continue
        if rng.random() > grassland_p:
            continue
        if neighbor_same(q, r, 5) or rng.random() < cluster:
            cells[idx] = 5

    for q, r in land_coords:
        idx = hg.cell_index(q, r, width)
        if cells[idx] not in (1, 5):
            continue
        if rng.random() > forest_p:
            continue
        if neighbor_same(q, r, 3) or rng.random() < cluster:
            cells[idx] = 3

    for q, r in land_coords:
        idx = hg.cell_index(q, r, width)
        if cells[idx] != 1:
            continue
        if rng.random() > desert_p:
            continue
        if neighbor_same(q, r, 4) or rng.random() < cluster * 0.8:
            cells[idx] = 4

    if swamp_p > 0:
        for q, r in land_coords:
            idx = hg.cell_index(q, r, width)
            if cells[idx] not in (1, 5):
                continue
            near_water = any(
                not hg.in_bounds(nq, nr, width, height)
                or cells[hg.cell_index(nq, nr, width)] == 0
                for nq, nr in hg.neighbors(q, r)
            )
            if near_water and rng.random() < swamp_p:
                cells[idx] = 5


def _hex_dims(profile: dict, existing: dict | None) -> tuple[int, int, float]:
    if existing:
        width = int(existing.get("width", hg.DEFAULT_HEX_WIDTH))
        height = int(existing.get("height", hg.DEFAULT_HEX_HEIGHT))
        hex_size = float(existing.get("hex_size", hg.DEFAULT_HEX_SIZE))
    else:
        width = int(profile.get("hex_width", hg.DEFAULT_HEX_WIDTH))
        height = int(profile.get("hex_height", hg.DEFAULT_HEX_HEIGHT))
        hex_size = float(profile.get("hex_size", hg.DEFAULT_HEX_SIZE))
    width = max(24, min(hg.MAX_HEX_WIDTH, width))
    height = max(16, min(hg.MAX_HEX_HEIGHT, height))
    hex_size = max(6.0, min(24.0, hex_size))
    return width, height, hex_size


def generate_world_hex_grid(
    profile: dict,
    layout_seed: int,
    detail_seed: int | None,
    *,
    mode: Literal["full", "layout", "details"] = "full",
    existing: dict | None = None,
    encode_rle: Callable[[list[int]], str],
    decode_rle: Callable[[str, int], list[int]],
) -> dict:
    """Return hex_grid dict with clustered terrain codes."""
    layout_seed = int(layout_seed) & 0x7FFFFFFF
    detail_seed = (
        (int(detail_seed) & 0x7FFFFFFF)
        if detail_seed is not None
        else (layout_seed ^ 0xDEADBEEF) & 0x7FFFFFFF
    )
    layout_rng = random.Random(layout_seed)
    detail_rng = random.Random(detail_seed)

    width, height, hex_size = _hex_dims(profile, existing)
    ox, oy = hg.grid_origin(hex_size, width, height)

    if mode == "details" and existing:
        cells = decode_rle(str(existing.get("cells", "")), width * height)
        water_mask = [0 if hg.land_code(c) else 1 for c in cells]
        _apply_biomes(cells, width, height, profile, detail_rng)
        for idx, mask in enumerate(water_mask):
            if mask:
                cells[idx] = 0
    elif mode == "layout":
        cells = [0] * (width * height)
        _place_land(cells, width, height, profile, layout_rng)
        _apply_biomes(cells, width, height, profile, detail_rng)
    elif mode == "full" and existing and profile.get("preserve_hex_layout"):
        cells = decode_rle(str(existing.get("cells", "")), width * height)
    else:
        cells = [0] * (width * height)
        _place_land(cells, width, height, profile, layout_rng)
        _apply_biomes(cells, width, height, profile, detail_rng)

    return {
        "orientation": "flat",
        "coordinate_space": "world",
        "width": width,
        "height": height,
        "hex_size": round(hex_size, 5),
        "origin": [round(ox, 5), round(oy, 5)],
        "encoding": "rle",
        "cells": encode_rle(cells),
        "layout_seed": layout_seed,
        "detail_seed": detail_seed,
    }


# City hex terrain: 0 outside, 1 courtyard/plaza, 2 water, 3 park, 4 road, 5 building, 6 wall
CITY_TERRAIN_WALL = 6
CITY_TERRAIN_BUILDING = 5
CITY_DEFAULT_HEX_WIDTH = 100
CITY_DEFAULT_HEX_HEIGHT = 72
CITY_DEFAULT_HEX_SIZE = 14.0


def _blob_points(
    rng: random.Random,
    cx: float,
    cy: float,
    radius_x: float,
    radius_y: float,
    count: int,
    detail_rng: random.Random | None = None,
) -> list[list[float]]:
    wobble_rng = detail_rng or rng
    points: list[list[float]] = []
    for idx in range(count):
        angle = (math.tau * idx / count) + wobble_rng.uniform(-0.16, 0.16)
        wobble = wobble_rng.uniform(0.72, 1.22)
        x = cx + math.cos(angle) * radius_x * wobble
        y = cy + math.sin(angle) * radius_y * wobble
        points.append([round(max(0.0, min(1.0, x)), 4), round(max(0.0, min(1.0, y)), 4)])
    return points


def _city_wall_polygon(
    rng: random.Random,
    profile: dict,
    detail_rng: random.Random,
) -> list[list[float]]:
    economy = float(profile.get("economy_density", 5))
    complexity = float(profile.get("city_complexity", 5))
    wall_radius = 0.28 + min(0.12, complexity / 100.0 + economy / 100.0)
    return _blob_points(rng, 0.5, 0.52, wall_radius, wall_radius * 0.9, 18, detail_rng)


def _city_hex_dims(profile: dict, existing: dict | None) -> tuple[int, int, float]:
    if existing:
        width = int(existing.get("width", CITY_DEFAULT_HEX_WIDTH))
        height = int(existing.get("height", CITY_DEFAULT_HEX_HEIGHT))
        hex_size = float(existing.get("hex_size", CITY_DEFAULT_HEX_SIZE))
    else:
        width = int(profile.get("hex_width", CITY_DEFAULT_HEX_WIDTH))
        height = int(profile.get("hex_height", CITY_DEFAULT_HEX_HEIGHT))
        hex_size = float(profile.get("hex_size", CITY_DEFAULT_HEX_SIZE))
    width = max(24, min(hg.MAX_HEX_WIDTH, width))
    height = max(16, min(hg.MAX_HEX_HEIGHT, height))
    hex_size = max(6.0, min(24.0, hex_size))
    return width, height, hex_size


def _place_city_interior(
    cells: list[int],
    width: int,
    height: int,
    wall_poly: list[list[float]],
    hex_size: float,
    origin: tuple[float, float],
    point_in_polygon: Any,
) -> None:
    from app.services.map_generation import voronoi

    pin = point_in_polygon or voronoi.point_in_polygon
    map_w, map_h = hg.map_pixel_size(width, height, hex_size, origin[0], origin[1])
    for q, r in hg.iter_hexes(width, height):
        wx, wy = hg.axial_to_world(q, r, hex_size, origin[0], origin[1])
        nx, ny = hg.world_to_norm(wx, wy, map_w, map_h)
        idx = hg.cell_index(q, r, width)
        cells[idx] = 1 if pin(nx, ny, wall_poly) else 0


def _grow_city_feature(
    cells: list[int],
    width: int,
    height: int,
    seeds: list[tuple[int, int]],
    target_add: int,
    target_code: int,
    cluster: float,
    rng: random.Random,
    *,
    source_code: int = 1,
) -> None:
    added = 0
    frontier: deque[tuple[int, int]] = deque(seeds)
    seen = set(seeds)
    while added < target_add and frontier:
        q, r = frontier.popleft()
        if not hg.in_bounds(q, r, width, height):
            continue
        idx = hg.cell_index(q, r, width)
        if cells[idx] != source_code:
            continue
        cells[idx] = target_code
        added += 1
        nbs = list(hg.neighbors(q, r))
        rng.shuffle(nbs)
        if cluster > 0.5:
            nbs.sort(
                key=lambda nb: -sum(
                    1
                    for nq, nr in hg.neighbors(nb[0], nb[1])
                    if hg.in_bounds(nq, nr, width, height)
                    and cells[hg.cell_index(nq, nr, width)] == target_code
                )
            )
        for nq, nr in nbs:
            if (nq, nr) in seen:
                continue
            if not hg.in_bounds(nq, nr, width, height):
                continue
            if rng.random() > 0.2 + cluster * 0.65:
                continue
            seen.add((nq, nr))
            frontier.append((nq, nr))


def _build_urban_layout(
    cells: list[int],
    width: int,
    height: int,
    profile: dict,
    rng: random.Random,
    wall_poly: list[list[float]],
    hex_size: float,
    origin: tuple[float, float],
) -> None:
    """Lay out walls, streets, building blocks, parks, and canals inside the footprint."""
    interior = [
        (q, r)
        for q, r in hg.iter_hexes(width, height)
        if cells[hg.cell_index(q, r, width)] == 1
    ]
    if not interior:
        return

    complexity = float(profile.get("city_complexity", 5))
    economy = float(profile.get("economy_density", 5))
    water_freq = float(profile.get("waterways", 4))

    for q, r in interior:
        idx = hg.cell_index(q, r, width)
        for nq, nr in hg.neighbors(q, r):
            if not hg.in_bounds(nq, nr, width, height):
                cells[idx] = CITY_TERRAIN_WALL
                break
            if cells[hg.cell_index(nq, nr, width)] == 0:
                cells[idx] = CITY_TERRAIN_WALL
                break

    spacing = max(4, min(8, int(9 - complexity / 4)))
    offset_q = rng.randint(0, spacing - 1)
    offset_r = rng.randint(0, spacing - 1)
    for q, r in interior:
        idx = hg.cell_index(q, r, width)
        if cells[idx] != 1:
            continue
        if (q - offset_q) % spacing == 0 or (r - offset_r) % spacing == 0:
            cells[idx] = 4

    map_w, map_h = hg.map_pixel_size(width, height, hex_size, origin[0], origin[1])
    center_q, center_r = hg.world_to_axial(
        map_w * 0.5, map_h * 0.52, hex_size, origin[0], origin[1]
    )

    for dq in range(-2, 3):
        for dr in range(-2, 3):
            cq, cr = center_q + dq, center_r + dr
            if not hg.in_bounds(cq, cr, width, height):
                continue
            idx = hg.cell_index(cq, cr, width)
            if cells[idx] in (1, 4, 5):
                cells[idx] = 1

    for dq, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        cq, cr = center_q, center_r
        for _ in range(max(width, height)):
            if not hg.in_bounds(cq, cr, width, height):
                break
            idx = hg.cell_index(cq, cr, width)
            if cells[idx] == 0:
                break
            if cells[idx] != CITY_TERRAIN_WALL:
                cells[idx] = 4
            cq += dq
            cr += dr

    density = min(0.94, 0.62 + economy / 22.0 + complexity / 35.0)
    for q, r in interior:
        idx = hg.cell_index(q, r, width)
        if cells[idx] == 1 and rng.random() < density:
            cells[idx] = CITY_TERRAIN_BUILDING

    if water_freq >= 2.5:
        canal_row = min(height - 2, max(2, offset_r + spacing // 2))
        for q in range(width):
            if not hg.in_bounds(q, canal_row, width, height):
                continue
            idx = hg.cell_index(q, canal_row, width)
            if cells[idx] in (1, CITY_TERRAIN_BUILDING) and rng.random() < 0.75:
                cells[idx] = 2

    park_budget = max(10, int(len(interior) * 0.05))
    park_seeds = [
        (max(1, width // 7), max(1, height // 7)),
        (max(1, (6 * width) // 7), max(1, height // 7)),
        (max(1, width // 7), max(1, (6 * height) // 7)),
    ]
    rng.shuffle(park_seeds)
    for seed in park_seeds[:2]:
        _grow_city_feature(
            cells, width, height, [seed], park_budget // 2, 3, 0.55, rng, source_code=1
        )
        _grow_city_feature(
            cells,
            width,
            height,
            [seed],
            park_budget // 2,
            3,
            0.55,
            rng,
            source_code=CITY_TERRAIN_BUILDING,
        )


def generate_city_hex_grid(
    profile: dict,
    layout_seed: int,
    detail_seed: int | None,
    *,
    mode: Literal["full", "layout", "details"] = "full",
    existing: dict | None = None,
    encode_rle: Callable[[list[int]], str],
    decode_rle: Callable[[str, int], list[int]],
) -> dict:
    """Return hex_grid dict with city terrain codes inside a walled footprint."""
    layout_seed = int(layout_seed) & 0x7FFFFFFF
    detail_seed = (
        (int(detail_seed) & 0x7FFFFFFF)
        if detail_seed is not None
        else (layout_seed ^ 0xDEADBEEF) & 0x7FFFFFFF
    )
    layout_rng = random.Random(layout_seed)
    detail_rng = random.Random(detail_seed)

    width, height, hex_size = _city_hex_dims(profile, existing)
    ox, oy = hg.grid_origin(hex_size, width, height)
    wall_poly = _city_wall_polygon(layout_rng, profile, detail_rng)
    if mode == "details" and existing and existing.get("city_wall_polygon"):
        stored = existing.get("city_wall_polygon")
        if isinstance(stored, list) and len(stored) >= 3:
            wall_poly = stored

    if mode == "details" and existing:
        cells = decode_rle(str(existing.get("cells", "")), width * height)
        for idx, code in enumerate(cells):
            if code >= 1:
                cells[idx] = 1
    else:
        cells = [0] * (width * height)
        _place_city_interior(cells, width, height, wall_poly, hex_size, (ox, oy), None)

    _build_urban_layout(cells, width, height, profile, detail_rng, wall_poly, hex_size, (ox, oy))

    return {
        "orientation": "flat",
        "coordinate_space": "world",
        "width": width,
        "height": height,
        "hex_size": round(hex_size, 5),
        "origin": [round(ox, 5), round(oy, 5)],
        "encoding": "rle",
        "cells": encode_rle(cells),
        "layout_seed": layout_seed,
        "detail_seed": detail_seed,
        "city_wall_polygon": wall_poly,
    }


# Shop interior hex terrain: 0 outside, 1 floor, 2 counter, 3 display, 4 aisle, 5 shelf, 6 wall
SHOP_TERRAIN_WALL = 6
SHOP_TERRAIN_SHELF = 5
SHOP_TERRAIN_AISLE = 4
SHOP_TERRAIN_DISPLAY = 3
SHOP_TERRAIN_COUNTER = 2
SHOP_DEFAULT_HEX_WIDTH = 56
SHOP_DEFAULT_HEX_HEIGHT = 42
SHOP_DEFAULT_HEX_SIZE = 16.0


def _shop_hex_dims(profile: dict, existing: dict | None) -> tuple[int, int, float]:
    if existing:
        width = int(existing.get("width", SHOP_DEFAULT_HEX_WIDTH))
        height = int(existing.get("height", SHOP_DEFAULT_HEX_HEIGHT))
        hex_size = float(existing.get("hex_size", SHOP_DEFAULT_HEX_SIZE))
    else:
        width = int(profile.get("hex_width", SHOP_DEFAULT_HEX_WIDTH))
        height = int(profile.get("hex_height", SHOP_DEFAULT_HEX_HEIGHT))
        hex_size = float(profile.get("hex_size", SHOP_DEFAULT_HEX_SIZE))
    width = max(20, min(hg.MAX_HEX_WIDTH, width))
    height = max(14, min(hg.MAX_HEX_HEIGHT, height))
    hex_size = max(8.0, min(22.0, hex_size))
    return width, height, hex_size


def _shop_footprint_polygon(rng: random.Random) -> list[list[float]]:
    margin_x = rng.uniform(0.11, 0.16)
    margin_y = rng.uniform(0.14, 0.20)
    return [
        [round(margin_x, 4), round(margin_y, 4)],
        [round(1.0 - margin_x, 4), round(margin_y, 4)],
        [round(1.0 - margin_x, 4), round(1.0 - margin_y, 4)],
        [round(margin_x, 4), round(1.0 - margin_y, 4)],
    ]


def _build_shop_interior_layout(
    cells: list[int],
    width: int,
    height: int,
    profile: dict,
    rng: random.Random,
    footprint_poly: list[list[float]],
    hex_size: float,
    origin: tuple[float, float],
) -> None:
    """Lay out walls, entrance, counter, aisles, shelves, and display nooks."""
    interior = [
        (q, r)
        for q, r in hg.iter_hexes(width, height)
        if cells[hg.cell_index(q, r, width)] == 1
    ]
    if not interior:
        return

    map_w, map_h = hg.map_pixel_size(width, height, hex_size, origin[0], origin[1])
    entrance_q, entrance_r = hg.world_to_axial(
        map_w * 0.5, map_h * 0.9, hex_size, origin[0], origin[1]
    )
    economy = float(profile.get("economy_density", 5))
    complexity = float(profile.get("city_complexity", 4))

    for q, r in interior:
        idx = hg.cell_index(q, r, width)
        is_edge = False
        for nq, nr in hg.neighbors(q, r):
            if not hg.in_bounds(nq, nr, width, height):
                is_edge = True
                break
            if cells[hg.cell_index(nq, nr, width)] == 0:
                is_edge = True
                break
        if is_edge:
            if abs(q - entrance_q) <= 1 and r >= height - max(3, height // 6):
                cells[idx] = SHOP_TERRAIN_AISLE
            else:
                cells[idx] = SHOP_TERRAIN_WALL

    for dq in range(-1, 2):
        eq = entrance_q + dq
        for dr in range(0, max(3, height // 5)):
            er = entrance_r - dr
            if not hg.in_bounds(eq, er, width, height):
                continue
            eidx = hg.cell_index(eq, er, width)
            if cells[eidx] in (1, SHOP_TERRAIN_WALL):
                cells[eidx] = SHOP_TERRAIN_AISLE

    counter_row = max(2, height // 6)
    for q in range(width):
        for r in range(counter_row):
            if not hg.in_bounds(q, r, width, height):
                continue
            idx = hg.cell_index(q, r, width)
            if cells[idx] in (1, SHOP_TERRAIN_WALL):
                cells[idx] = SHOP_TERRAIN_COUNTER

    aisle_spacing = max(3, min(6, int(8 - complexity / 2)))
    for q, r in interior:
        idx = hg.cell_index(q, r, width)
        if cells[idx] not in (1, SHOP_TERRAIN_SHELF):
            continue
        if q % aisle_spacing == 0 or r % aisle_spacing == 0:
            cells[idx] = SHOP_TERRAIN_AISLE

    shelf_chance = min(0.88, 0.45 + economy / 18.0)
    for q, r in interior:
        idx = hg.cell_index(q, r, width)
        if cells[idx] != 1:
            continue
        edge_dist = min(q, r, width - 1 - q, height - 1 - r)
        if edge_dist <= 1 and rng.random() < shelf_chance:
            cells[idx] = SHOP_TERRAIN_SHELF

    display_budget = max(6, int(len(interior) * 0.06))
    display_seeds = [
        (entrance_q - 2, entrance_r - 1),
        (entrance_q + 2, entrance_r - 1),
        (entrance_q, entrance_r - 2),
    ]
    rng.shuffle(display_seeds)
    for seed in display_seeds[:2]:
        if hg.in_bounds(seed[0], seed[1], width, height):
            _grow_city_feature(
                cells,
                width,
                height,
                [seed],
                display_budget // 2,
                SHOP_TERRAIN_DISPLAY,
                0.5,
                rng,
                source_code=1,
            )

    storage_seed = (max(1, width // 8), max(1, height // 8))
    _grow_city_feature(
        cells,
        width,
        height,
        [storage_seed],
        max(4, display_budget // 2),
        SHOP_TERRAIN_SHELF,
        0.65,
        rng,
        source_code=1,
    )


def generate_shop_hex_grid(
    profile: dict,
    layout_seed: int,
    detail_seed: int | None,
    *,
    mode: Literal["full", "layout", "details"] = "full",
    existing: dict | None = None,
    encode_rle: Callable[[list[int]], str],
    decode_rle: Callable[[str, int], list[int]],
) -> dict:
    """Return hex_grid dict with shop-floor terrain codes inside a rectangular footprint."""
    layout_seed = int(layout_seed) & 0x7FFFFFFF
    detail_seed = (
        (int(detail_seed) & 0x7FFFFFFF)
        if detail_seed is not None
        else (layout_seed ^ 0xDEADBEEF) & 0x7FFFFFFF
    )
    layout_rng = random.Random(layout_seed)
    detail_rng = random.Random(detail_seed)

    width, height, hex_size = _shop_hex_dims(profile, existing)
    ox, oy = hg.grid_origin(hex_size, width, height)
    footprint = _shop_footprint_polygon(layout_rng)
    if mode == "details" and existing and existing.get("city_wall_polygon"):
        stored = existing.get("city_wall_polygon")
        if isinstance(stored, list) and len(stored) >= 3:
            footprint = stored

    if mode == "details" and existing:
        cells = decode_rle(str(existing.get("cells", "")), width * height)
        for idx, code in enumerate(cells):
            if code >= 1:
                cells[idx] = 1
    else:
        cells = [0] * (width * height)
        _place_city_interior(cells, width, height, footprint, hex_size, (ox, oy), None)

    _build_shop_interior_layout(
        cells, width, height, profile, detail_rng, footprint, hex_size, (ox, oy)
    )

    return {
        "orientation": "flat",
        "coordinate_space": "world",
        "width": width,
        "height": height,
        "hex_size": round(hex_size, 5),
        "origin": [round(ox, 5), round(oy, 5)],
        "encoding": "rle",
        "cells": encode_rle(cells),
        "layout_seed": layout_seed,
        "detail_seed": detail_seed,
        "city_wall_polygon": footprint,
    }
