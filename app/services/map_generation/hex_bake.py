"""Bake hex_grid into gapless terrain_grid for seamless display."""

from __future__ import annotations

import math
from typing import Callable

from app.services.map_generation import hex_grid as hg

BAKE_MIN_WIDTH = 256
BAKE_MIN_HEIGHT = 192
BAKE_MAX_WIDTH = 1024
BAKE_MAX_HEIGHT = 768
BAKE_TARGET_PIXELS = 512 * 384


def bake_dimensions(hex_grid: dict) -> tuple[int, int]:
    map_w, map_h = hg.hex_grid_map_size(hex_grid)
    if hex_grid.get("coordinate_space") == "norm":
        return 256, 192
    aspect = map_w / max(map_h, 1.0)
    bh = int(math.sqrt(BAKE_TARGET_PIXELS / aspect))
    bw = int(bh * aspect)
    bw = min(BAKE_MAX_WIDTH, max(BAKE_MIN_WIDTH, bw))
    bh = min(BAKE_MAX_HEIGHT, max(BAKE_MIN_HEIGHT, bh))
    return bw, bh


def _point_in_polygon(px: float, py: float, polygon: list[list[float]]) -> bool:
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if ((y1 > py) != (y2 > py)) and (
            px < (x2 - x1) * (py - y1) / ((y2 - y1) or 1e-9) + x1
        ):
            inside = not inside
    return inside


def _stamp_hex(
    out: list[int],
    grid_width: int,
    grid_height: int,
    map_w: float,
    map_h: float,
    corners: list[list[float]],
    code: int,
) -> None:
    xs = [p[0] for p in corners]
    ys = [p[1] for p in corners]
    gx0 = max(0, int((min(xs) / map_w) * grid_width))
    gx1 = min(grid_width - 1, int(math.ceil((max(xs) / map_w) * grid_width)))
    gy0 = max(0, int((min(ys) / map_h) * grid_height))
    gy1 = min(grid_height - 1, int(math.ceil((max(ys) / map_h) * grid_height)))
    for gy in range(gy0, gy1 + 1):
        py = (gy + 0.5) / grid_height * map_h
        row = gy * grid_width
        for gx in range(gx0, gx1 + 1):
            px = (gx + 0.5) / grid_width * map_w
            if _point_in_polygon(px, py, corners):
                out[row + gx] = code


def bake_terrain_grid(
    hex_grid: dict,
    grid_width: int,
    grid_height: int,
    encode_rle: Callable[[list[int]], str],
    decode_rle: Callable[[str, int], list[int]],
    *,
    smooth_coast: bool = True,
    city_scope: bool = False,
) -> dict:
    """Rasterize hex polygons into a terrain grid (fast stamp per hex)."""
    w = int(hex_grid["width"])
    h = int(hex_grid["height"])
    cells = decode_rle(str(hex_grid.get("cells", "")), w * h)
    size = float(hex_grid.get("hex_size", hg.DEFAULT_HEX_SIZE))
    if hex_grid.get("coordinate_space") != "norm" and size < 1.0:
        size = hg.DEFAULT_HEX_SIZE
    ox, oy = hg.grid_origin_for_hex_grid(hex_grid)
    map_w, map_h = hg.hex_grid_map_size(hex_grid)
    use_norm = hex_grid.get("coordinate_space") == "norm"
    if use_norm:
        map_w, map_h = 1.0, 1.0

    out = [0] * (grid_width * grid_height)
    corner_fn = hg.hex_corners_norm if use_norm else hg.hex_corners_world
    for q, r in hg.iter_hexes(w, h):
        idx = hg.cell_index(q, r, w)
        code = int(cells[idx])
        corners = corner_fn(q, r, size, ox, oy)
        _stamp_hex(out, grid_width, grid_height, map_w, map_h, corners, code)

    if smooth_coast and not city_scope:
        out = _smooth_coast(out, grid_width, grid_height)

    return {
        "width": grid_width,
        "height": grid_height,
        "encoding": "rle",
        "cells": encode_rle(out),
        "derived_from": "hex_grid",
    }


def _smooth_coast(cells: list[int], width: int, height: int) -> list[int]:
    """One pass: trim lonely land pixels and fill narrow water gaps."""
    result = cells[:]
    for gy in range(1, height - 1):
        for gx in range(1, width - 1):
            idx = gy * width + gx
            neighbors = [
                cells[idx - 1],
                cells[idx + 1],
                cells[idx - width],
                cells[idx + width],
            ]
            land_n = sum(1 for n in neighbors if hg.land_code(n))
            if hg.land_code(cells[idx]) and land_n <= 1:
                result[idx] = 0
            elif not hg.land_code(cells[idx]) and land_n >= 3:
                result[idx] = 1
    return result


def hex_grid_from_terrain_grid(
    terrain_grid: dict,
    encode_rle: Callable[[list[int]], str],
    decode_rle: Callable[[str, int], list[int]],
    *,
    width: int = hg.DEFAULT_HEX_WIDTH,
    height: int = hg.DEFAULT_HEX_HEIGHT,
    hex_size: float = hg.DEFAULT_HEX_SIZE,
) -> dict:
    """Bootstrap hex_grid by sampling an existing raster (v6 migration)."""
    tw = int(terrain_grid.get("width", 256))
    th = int(terrain_grid.get("height", 192))
    raster = decode_rle(str(terrain_grid.get("cells", "")), tw * th)
    ox, oy = hg.grid_origin(hex_size, width, height)
    map_w, map_h = hg.map_pixel_size(width, height, hex_size, ox, oy)
    cells = [0] * (width * height)
    for q, r in hg.iter_hexes(width, height):
        wx, wy = hg.axial_to_world(q, r, hex_size, ox, oy)
        gx = min(tw - 1, max(0, int((wx / map_w) * tw)))
        gy = min(th - 1, max(0, int((wy / map_h) * th)))
        cells[hg.cell_index(q, r, width)] = int(raster[gy * tw + gx])
    return {
        "orientation": "flat",
        "coordinate_space": "world",
        "width": width,
        "height": height,
        "hex_size": round(hex_size, 5),
        "origin": [round(ox, 5), round(oy, 5)],
        "encoding": "rle",
        "cells": encode_rle(cells),
    }
