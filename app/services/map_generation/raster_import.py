"""Raster upload classification and Voronoi site seeding."""

from __future__ import annotations

import random
from typing import Any

import numpy as np
from PIL import Image

from app.services.map_generation import voronoi
from app.services.map_generation.pipeline import site_count_for_scope

GRID_W = 256
GRID_H = 192


def classify_image_to_grid(
    img: Image.Image,
    scope: str = "world",
) -> tuple[list[int], list[list[float]] | None]:
    """Classify raster into terrain cell codes and optional landmass polygon."""
    img = img.convert("RGB").resize((GRID_W, GRID_H), Image.Resampling.LANCZOS)
    arr = np.array(img, dtype=np.float32)
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    brightness = (r + g + b) / 3.0
    blue_dom = (b > r + 15) & (b > g + 10)
    green_dom = (g > r + 10) & (g > b) & (brightness > 60)
    dark = brightness < 70
    warm = (r > g + 15) & (brightness > 80)

    cells: list[int] = []
    for gy in range(GRID_H):
        for gx in range(GRID_W):
            if blue_dom[gy, gx]:
                cells.append(0)
            elif dark[gy, gx]:
                cells.append(2)
            elif green_dom[gy, gx]:
                cells.append(3)
            elif warm[gy, gx]:
                cells.append(4)
            elif brightness[gy, gx] > 40:
                cells.append(1)
            else:
                cells.append(0)

    land_poly = _coastline_polygon_from_grid(cells, GRID_W, GRID_H)
    return cells, land_poly


def _coastline_polygon_from_grid(
    cells: list[int],
    width: int,
    height: int,
) -> list[list[float]] | None:
    """Extract rough land/water boundary as polygon."""
    boundary_pts: list[tuple[float, float]] = []
    for gy in range(height):
        for gx in range(width):
            code = cells[gy * width + gx]
            if code == 0:
                continue
            for dx, dy in ((1, 0), (0, 1)):
                nx, ny = gx + dx, gy + dy
                ncode = 0
                if 0 <= nx < width and 0 <= ny < height:
                    ncode = cells[ny * width + nx]
                if ncode == 0:
                    boundary_pts.append(((gx + 0.5) / width, (gy + 0.5) / height))
    if len(boundary_pts) < 8:
        return None
    import math

    cx = sum(p[0] for p in boundary_pts) / len(boundary_pts)
    cy = sum(p[1] for p in boundary_pts) / len(boundary_pts)

    def angle_key(p: tuple[float, float]) -> float:
        return math.atan2(p[1] - cy, p[0] - cx)

    hull = sorted(set(boundary_pts), key=angle_key)
    step = max(1, len(hull) // 16)
    simplified = hull[::step][:16]
    return [[round(x, 4), round(y, 4)] for x, y in simplified]


def sites_from_classified_grid(
    cells: list[int],
    width: int,
    height: int,
    rng: random.Random,
    profile: dict,
    scope: str,
) -> list[list[float]]:
    target = site_count_for_scope(scope, profile)
    return voronoi.sites_from_terrain_grid(cells, width, height, rng, target)


def import_raster_to_sites(
    img: Image.Image,
    scope: str,
    profile: dict,
    layout_seed: int,
) -> tuple[list[list[float]], list[list[float]] | None, list[int]]:
    """Full raster import: grid classification + site seeding."""
    rng = random.Random(int(layout_seed) & 0x7FFFFFFF)
    cells, land_poly = classify_image_to_grid(img, scope)
    sites = sites_from_classified_grid(cells, GRID_W, GRID_H, rng, profile, scope)
    return sites, land_poly, cells
