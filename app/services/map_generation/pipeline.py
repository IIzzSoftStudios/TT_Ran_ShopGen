"""Orchestrate full procedural map generation pipeline."""

from __future__ import annotations

import math
import random
from typing import Any, Literal

from app.services.map_generation import climate, hydrology, tectonics, voronoi
from app.services.map_generation.derive import derive_features, derive_terrain_grid

WORLD_SCOPE = "world"
CITY_SCOPE = "city"
SHOP_SCOPE = "shop"

TERRAIN_GRID_WIDTH = 256
TERRAIN_GRID_HEIGHT = 192


def site_count_for_scope(scope: str, profile: dict) -> int:
    if scope == WORLD_SCOPE:
        region = float(profile.get("region_density", 3))
        rough = float(profile.get("terrain_roughness", 5))
        return max(120, min(220, int(100 + region * 8 + rough * 4)))
    if scope == CITY_SCOPE:
        complexity = float(profile.get("city_complexity", 5))
        return max(40, min(80, int(35 + complexity * 2)))
    # shop
    return max(15, min(35, int(15 + float(profile.get("economy_density", 5)))))


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
    points = []
    for idx in range(count):
        angle = (math.tau * idx / count) + wobble_rng.uniform(-0.16, 0.16)
        wobble = wobble_rng.uniform(0.72, 1.22)
        x = cx + math.cos(angle) * radius_x * wobble
        y = cy + math.sin(angle) * radius_y * wobble
        points.append([round(max(0.0, min(1.0, x)), 4), round(max(0.0, min(1.0, y)), 4)])
    return points


def _landmass_polygon(
    rng: random.Random,
    profile: dict,
    detail_rng: random.Random,
) -> list[list[float]]:
    land = float(profile.get("landmass_scale", 6))
    rough = float(profile.get("terrain_roughness", 5))
    coast = float(profile.get("coast_detail", 5))
    land_rx = 0.24 + (land / 10.0) * 0.2
    land_ry = 0.22 + (land / 10.0) * 0.18
    wobble_points = int(14 + coast + rough * 0.5)
    return _blob_points(rng, 0.48, 0.52, land_rx, land_ry, wobble_points, detail_rng)


def _city_wall_polygon(
    rng: random.Random,
    profile: dict,
    detail_rng: random.Random,
) -> list[list[float]]:
    economy = float(profile.get("economy_density", 5))
    complexity = float(profile.get("city_complexity", 5))
    wall_radius = 0.28 + min(0.12, complexity / 100.0 + economy / 100.0)
    return _blob_points(rng, 0.5, 0.52, wall_radius, wall_radius * 0.9, 18, detail_rng)


def _island_count_for_profile(profile: dict, land: float, rough: float) -> int:
    explicit = profile.get("island_count", 0)
    if explicit and float(explicit) >= 1:
        return max(1, int(round(float(explicit))))
    return max(1, int(1 + rough / 2 + (10 - land) / 4))


def _island_polygons(
    layout_rng: random.Random,
    detail_rng: random.Random,
    profile: dict,
    land_poly: list[list[float]],
) -> list[list[list[float]]]:
    land = float(profile.get("landmass_scale", 6))
    rough = float(profile.get("terrain_roughness", 5))
    land_rx = 0.24 + (land / 10.0) * 0.2
    land_ry = 0.22 + (land / 10.0) * 0.18
    island_total = _island_count_for_profile(profile, land, rough)
    polys: list[list[list[float]]] = []
    for _ in range(island_total):
        angle = layout_rng.uniform(0, math.tau)
        cx = 0.5 + math.cos(angle) * layout_rng.uniform(land_rx + 0.04, 0.48)
        cy = 0.52 + math.sin(angle) * layout_rng.uniform(land_ry + 0.04, 0.42)
        irx = layout_rng.uniform(0.04, 0.09)
        iry = layout_rng.uniform(0.035, 0.08)
        polys.append(_blob_points(layout_rng, cx, cy, irx, iry, layout_rng.randint(8, 13), detail_rng))
    return polys


def _settlement_hubs(rng: random.Random, count: int) -> list[tuple[float, float]]:
    hubs: list[tuple[float, float]] = []
    for idx in range(count):
        angle = (math.tau * idx / max(1, count)) + rng.uniform(-0.2, 0.2)
        radius = rng.uniform(0.18, 0.38)
        hubs.append((
            round(0.5 + math.cos(angle) * radius, 4),
            round(0.52 + math.sin(angle) * radius, 4),
        ))
    return hubs


def _nearest_cell(cells: list[dict], x: float, y: float) -> int:
    best = 0
    best_d = float("inf")
    for cell in cells:
        cx, cy = float(cell["centroid"][0]), float(cell["centroid"][1])
        d = (cx - x) ** 2 + (cy - y) ** 2
        if d < best_d:
            best_d = d
            best = int(cell["id"])
    return best


def _water_cells_outside_land(
    cells: list[dict],
    land_polygon: list[list[float]] | None,
) -> set[int]:
    water: set[int] = set()
    if not land_polygon:
        return water
    for cell in cells:
        cx, cy = float(cell["centroid"][0]), float(cell["centroid"][1])
        if not voronoi.point_in_polygon(cx, cy, land_polygon):
            water.add(int(cell["id"]))
            cell["terrain_code"] = 0
            cell["biome"] = "water"
            cell["elevation"] = 0.0
    return water


def _label_regions(cells: list[dict], profile: dict, scope: str) -> None:
    region_count = max(1, int(round(float(profile.get("region_density", 3)))))
    if scope == WORLD_SCOPE:
        land_cells = [c for c in cells if c.get("biome") != "water"]
        land_cells.sort(key=lambda c: (float(c["centroid"][0]), float(c["centroid"][1])))
        for idx, cell in enumerate(land_cells):
            cell["label"] = f"Region {(idx % region_count) + 1}"
    elif scope == CITY_SCOPE:
        labels = ["Market", "Docks", "Guilds", "Temple", "Commons", "Old Town"]
        land_cells = [c for c in cells if c.get("terrain_code") != 0]
        for idx, cell in enumerate(land_cells):
            cell["label"] = f"District {labels[idx % len(labels)]}"
    else:
        for idx, cell in enumerate(cells):
            cell["label"] = f"Room {idx + 1}"


def _trade_routes(
    cells: list[dict],
    adjacency: list[list[int]],
    hubs: list[tuple[float, float]],
    economy: float,
) -> tuple[list[dict], list[dict]]:
    """Return trade_route_paths metadata and point lists for features."""
    if len(hubs) < 2:
        return [], []
    route_count = min(len(hubs) - 1, max(1, int(1 + economy / 3)))
    paths_meta: list[dict] = []
    for idx in range(route_count):
        start = hubs[idx]
        end = hubs[idx + 1]
        sid = _nearest_cell(cells, start[0], start[1])
        eid = _nearest_cell(cells, end[0], end[1])
        cell_path = hydrology.shortest_path_cells(cells, adjacency, sid, eid)
        pts = [
            [float(cells[c]["centroid"][0]), float(cells[c]["centroid"][1])]
            for c in cell_path
        ]
        paths_meta.append({"points": pts, "cell_path": cell_path})
    return paths_meta, paths_meta


def generate_map(
    scope: str,
    layout_seed: int,
    profile: dict,
    *,
    detail_seed: int | None = None,
    mode: Literal["full", "layout", "details"] = "full",
    existing_cell_graph: dict | None = None,
    encode_rle: Any = None,
    initial_sites: list[list[float]] | None = None,
    landmask_polygon: list[list[float]] | None = None,
) -> dict:
    """Return cell_graph dict ready to embed in generation_json."""
    layout_seed = int(layout_seed) & 0x7FFFFFFF
    detail_seed = (
        (int(detail_seed) & 0x7FFFFFFF)
        if detail_seed is not None
        else (layout_seed ^ 0xDEADBEEF) & 0x7FFFFFFF
    )
    layout_rng = random.Random(layout_seed)
    detail_rng = random.Random(detail_seed)

    site_count = site_count_for_scope(scope, profile)
    land_poly = landmask_polygon
    island_polys: list[list[list[float]]] = []

    if scope == WORLD_SCOPE:
        if land_poly is None:
            land_poly = _landmass_polygon(layout_rng, profile, detail_rng)
        island_polys = _island_polygons(layout_rng, detail_rng, profile, land_poly)
        mask = voronoi.land_mask_rect(margin=0.02)
        rough = float(profile.get("terrain_roughness", 5))
        water = float(profile.get("waterways", 4))
    elif scope == CITY_SCOPE:
        if land_poly is None:
            land_poly = _city_wall_polygon(layout_rng, profile, detail_rng)
        mask = voronoi.land_mask_from_polygon(land_poly)
        rough = float(profile.get("city_complexity", 5)) / 2
        water = float(profile.get("waterways", 4))
    else:
        mask = voronoi.land_mask_rect()
        land_poly = None
        rough = 3.0
        water = 2.0

    if mode == "details" and existing_cell_graph:
        sites = existing_cell_graph.get("sites") or []
        tectonic_lines = existing_cell_graph.get("tectonic_lines") or []
    elif mode == "layout" or not existing_cell_graph:
        if initial_sites:
            sites = initial_sites[:site_count]
        else:
            sites = voronoi.poisson_disk_sites(layout_rng, mask, site_count)
        tectonic_lines = (
            existing_cell_graph.get("tectonic_lines")
            if existing_cell_graph and mode != "full"
            else None
        )
        if tectonic_lines is None and scope == WORLD_SCOPE:
            tectonic_lines = tectonics.default_tectonic_lines(detail_rng, rough)
        elif tectonic_lines is None:
            tectonic_lines = []
    else:
        sites = existing_cell_graph.get("sites") or voronoi.poisson_disk_sites(
            layout_rng, mask, site_count
        )
        tectonic_lines = existing_cell_graph.get("tectonic_lines") or []

    cells, adjacency, _grid = voronoi.build_voronoi_cells(sites, mask)

    water_ids: set[int] = set()
    if scope == WORLD_SCOPE and land_poly:
        water_ids = _water_cells_outside_land(cells, land_poly)

    tectonics.apply_tectonic_elevation(cells, tectonic_lines, water_cell_ids=water_ids)

    wind = existing_cell_graph.get("wind_vector") if existing_cell_graph else None
    if wind is None:
        wind = climate.wind_vector_from_profile(profile)
    moisture_strength = float(profile.get("moisture_strength", 8.5)) / 10.0
    climate.apply_climate(
        cells, adjacency, wind,
        moisture_strength=moisture_strength,
        scope=scope,
        water_cell_ids=water_ids,
    )

    max_rivers = max(0, int(1 + water / 2)) if scope == WORLD_SCOPE else 0
    rivers = hydrology.trace_rivers(
        cells, adjacency, water_ids, max_rivers=max_rivers,
    )

    economy = float(profile.get("economy_density", 5))
    hubs = _settlement_hubs(layout_rng, max(3, int(2 + float(profile.get("city_density", 6)) / 5)))
    trade_paths, _ = _trade_routes(cells, adjacency, hubs, economy)

    _label_regions(cells, profile, scope)

    extra_features: list[dict] = []
    if scope == CITY_SCOPE:
        extra_features.append({
            "type": "plaza",
            "x": 0.5,
            "y": 0.52,
            "size": 0.08,
        })

    cell_graph = {
        "site_count": len(sites),
        "sites": [[round(s[0], 4), round(s[1], 4)] for s in sites],
        "cells": cells,
        "adjacency": adjacency,
        "tectonic_lines": tectonic_lines,
        "wind_vector": wind,
        "rivers": rivers,
        "trade_route_paths": trade_paths,
        "landmass_polygon": land_poly,
        "island_polygons": island_polys,
        "extra_features": extra_features,
    }
    return cell_graph


def partial_regen(
    scope: str,
    generation: dict,
    mode: Literal["tectonics", "climate", "hydrology", "layout", "details", "full"],
    profile: dict,
    layout_seed: int,
    detail_seed: int | None = None,
) -> dict:
    """Re-run pipeline subset preserving user vector edits where possible."""
    existing = generation.get("cell_graph") or {}
    pipeline_mode: Literal["full", "layout", "details"] = "full"
    if mode in ("climate", "hydrology", "tectonics"):
        pipeline_mode = "details"
    elif mode == "layout":
        pipeline_mode = "layout"
    elif mode == "details":
        pipeline_mode = "details"

    land_poly = existing.get("landmass_polygon")
    return generate_map(
        scope,
        layout_seed,
        profile,
        detail_seed=detail_seed,
        mode=pipeline_mode,
        existing_cell_graph=existing,
        landmask_polygon=land_poly,
    )


def migrate_v5_to_v6(
    generation: dict,
    scope: str,
    profile: dict,
    layout_seed: int,
    detail_seed: int | None,
    decode_rle: Any,
    encode_rle: Any,
) -> dict:
    """Upgrade v5 generation to v6 with cell_graph from terrain_grid + features."""
    layout_rng = random.Random(int(layout_seed) & 0x7FFFFFFF)
    site_count = site_count_for_scope(scope, profile)

    sites: list[list[float]] = []
    grid = generation.get("terrain_grid")
    if grid and grid.get("encoding") == "rle":
        w = int(grid.get("width", TERRAIN_GRID_WIDTH))
        h = int(grid.get("height", TERRAIN_GRID_HEIGHT))
        cells_flat = decode_rle(str(grid.get("cells", "")), w * h)
        sites = voronoi.sites_from_terrain_grid(cells_flat, w, h, layout_rng, site_count)

    # Also pull centroids from feature blobs
    for feat in generation.get("features") or []:
        pts = feat.get("points")
        if pts and len(pts) >= 3:
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            if len(sites) < site_count:
                sites.append([round(cx, 4), round(cy, 4)])

    while len(sites) < min(site_count, 20):
        sites.append([
            round(layout_rng.uniform(0.2, 0.8), 4),
            round(layout_rng.uniform(0.2, 0.8), 4),
        ])

    land_poly = None
    for feat in generation.get("features") or []:
        if feat.get("type") == "landmass":
            land_poly = feat.get("points")
            break
        if feat.get("type") == "city_wall":
            land_poly = feat.get("points")
            break

    cell_graph = generate_map(
        scope,
        layout_seed,
        profile,
        detail_seed=detail_seed,
        initial_sites=sites,
        landmask_polygon=land_poly,
    )
    return cell_graph


def build_generation_from_cell_graph(
    cell_graph: dict,
    scope: str,
    layout_seed: int,
    detail_seed: int,
    profile: dict,
    style_preset: str,
    render_palette: dict,
    encode_rle: Any,
) -> dict:
    """Assemble full generation_json v6 from solved cell_graph."""
    land_poly = cell_graph.get("landmass_polygon")
    features = derive_features(
        cell_graph,
        scope,
        landmass_polygon=land_poly,
        island_polygons=cell_graph.get("island_polygons"),
        extra_features=cell_graph.get("extra_features"),
    )
    terrain_grid = derive_terrain_grid(
        cell_graph,
        TERRAIN_GRID_WIDTH,
        TERRAIN_GRID_HEIGHT,
        encode_rle,
        voronoi.point_in_polygon,
        landmask_polygon=land_poly,
        scope=scope,
    )
    # Strip internal keys from persisted cell_graph
    persist_graph = {
        k: v for k, v in cell_graph.items()
        if k not in ("landmass_polygon", "island_polygons", "extra_features")
    }
    if land_poly:
        persist_graph["landmass_polygon"] = land_poly

    return {
        "schema_version": 6,
        "seed": layout_seed,
        "layout_seed": layout_seed,
        "detail_seed": detail_seed,
        "scope": scope,
        "style_preset": style_preset,
        "palette": style_preset,
        "render_palette": render_palette,
        "profile": profile,
        "cell_graph": persist_graph,
        "features": features,
        "terrain_grid": terrain_grid,
    }
