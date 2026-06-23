"""Derive features[] and terrain_grid from cell_graph."""

from __future__ import annotations

from typing import Any, Callable

import numpy as np


def derive_features(
    cell_graph: dict,
    scope: str,
    *,
    landmass_polygon: list[list[float]] | None = None,
    island_polygons: list[list[list[float]]] | None = None,
    extra_features: list[dict] | None = None,
) -> list[dict]:
    """Build render-cache feature list from cell graph."""
    features: list[dict] = []
    cells = cell_graph.get("cells") or []
    rivers = cell_graph.get("rivers") or []
    tectonic = cell_graph.get("tectonic_lines") or []
    trade_paths = cell_graph.get("trade_route_paths") or []

    if landmass_polygon and scope == "world":
        features.append({"type": "landmass", "points": landmass_polygon})
    for island in island_polygons or []:
        features.append({"type": "island", "points": island})

    for line in tectonic:
        pts = line.get("points") or []
        if len(pts) >= 2:
            peak_scales = [round(0.75 + i * 0.1, 3) for i in range(len(pts))]
            features.append({
                "type": "mountain_range",
                "points": pts,
                "peak_scale": peak_scales,
            })

    for river in rivers:
        path = river.get("cell_path") or []
        pts = _river_polyline_from_path(cells, path)
        if len(pts) >= 2:
            features.append({"type": "river", "points": pts})

    for idx, route in enumerate(trade_paths):
        pts = route.get("points") or []
        if len(pts) >= 2:
            ftype = "road" if scope in ("city", "shop") else "trade_route"
            features.append({"type": ftype, "points": pts})

    # Region tints from labeled cells
    for cell in cells:
        label = cell.get("label") or ""
        poly = cell.get("polygon")
        if not poly or len(poly) < 3:
            continue
        if scope == "world" and label.startswith("Region"):
            features.append({
                "type": "region_tint",
                "label": label,
                "points": poly,
            })
        elif scope == "city" and label.startswith("District"):
            features.append({
                "type": "district",
                "label": label,
                "points": poly,
            })

    if scope == "city" and landmass_polygon:
        features.insert(0, {"type": "city_wall", "points": landmass_polygon})

    # Forest blobs on forest cells (world)
    if scope == "world":
        for cell in cells:
            if cell.get("biome") == "forest":
                poly = cell.get("polygon")
                if poly and len(poly) >= 3:
                    features.append({"type": "forest", "points": poly})

    for feat in extra_features or []:
        features.append(feat)

    return features


def _river_polyline_from_path(cells: list[dict], path: list[int]) -> list[list[float]]:
    pts: list[list[float]] = []
    for cid in path:
        if 0 <= cid < len(cells):
            c = cells[cid].get("centroid")
            if c:
                pts.append([float(c[0]), float(c[1])])
    return pts


def derive_terrain_grid(
    cell_graph: dict,
    grid_width: int,
    grid_height: int,
    encode_rle: Callable[[list[int]], str],
    point_in_polygon: Callable[[float, float, list], bool],
    landmask_polygon: list[list[float]] | None = None,
    scope: str = "world",
) -> dict:
    """Rasterize cell terrain codes via nearest-centroid Voronoi (gapless tiling)."""
    cells = cell_graph.get("cells") or []
    out = [0] * (grid_width * grid_height)
    if not cells:
        return {
            "width": grid_width,
            "height": grid_height,
            "encoding": "rle",
            "cells": encode_rle(out),
            "derived_from": "cell_graph",
        }

    centroids = np.array(
        [[float(c["centroid"][0]), float(c["centroid"][1])] for c in cells],
        dtype=np.float64,
    )
    codes = np.array([int(c.get("terrain_code", 1)) for c in cells], dtype=np.int32)
    islands = cell_graph.get("island_polygons") or []

    def in_land_area(nx: float, ny: float) -> bool:
        if landmask_polygon and point_in_polygon(nx, ny, landmask_polygon):
            return True
        for island in islands:
            if island and point_in_polygon(nx, ny, island):
                return True
        return landmask_polygon is None and scope != "world"

    for gy in range(grid_height):
        ny = (gy + 0.5) / grid_height
        for gx in range(grid_width):
            nx = (gx + 0.5) / grid_width
            if scope == "world" and landmask_polygon and not in_land_area(nx, ny):
                out[gy * grid_width + gx] = 0
                continue
            if scope == "city" and landmask_polygon and not point_in_polygon(nx, ny, landmask_polygon):
                out[gy * grid_width + gx] = 0
                continue
            d2 = (centroids[:, 0] - nx) ** 2 + (centroids[:, 1] - ny) ** 2
            out[gy * grid_width + gx] = int(codes[int(np.argmin(d2))])

    return {
        "width": grid_width,
        "height": grid_height,
        "encoding": "rle",
        "cells": encode_rle(out),
        "derived_from": "cell_graph",
    }
