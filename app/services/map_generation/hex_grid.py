"""Axial hex grid utilities for world map authoring (schema v7)."""

from __future__ import annotations

import math
from typing import Callable

SQRT3 = math.sqrt(3)
DEFAULT_HEX_SIZE = 12.0  # world pixels (hex radius)
DEFAULT_HEX_WIDTH = 200
DEFAULT_HEX_HEIGHT = 125
MAX_HEX_WIDTH = 500
MAX_HEX_HEIGHT = 500
WORLD_ORIGIN_PADDING = 20.0
HEX_CELL_MAX = 6  # 0 water, 1 prairie, 2 mountain, 3 forest, 4 desert, 5 grassland, 6 hills


def map_pixel_size(
    width: int,
    height: int,
    hex_size: float,
    origin_x: float,
    origin_y: float,
) -> tuple[float, float]:
    """Total world pixel extent of the hex grid."""
    max_q = max(0, width - 1)
    max_r = max(0, height - 1)
    span_x = hex_size * 1.5 * max_q + hex_size * 0.75
    span_y = hex_size * SQRT3 * (max_r + max_q / 2.0)
    return (
        origin_x + span_x + origin_x,
        origin_y + span_y + origin_y,
    )


def axial_to_world(
    q: int,
    r: int,
    hex_size: float,
    origin_x: float,
    origin_y: float,
) -> tuple[float, float]:
    wx = origin_x + hex_size * 1.5 * q
    wy = origin_y + hex_size * SQRT3 * (r + q / 2.0)
    return wx, wy


def world_to_axial(
    wx: float,
    wy: float,
    hex_size: float,
    origin_x: float,
    origin_y: float,
) -> tuple[int, int]:
    x = wx - origin_x
    y = wy - origin_y
    qf = (2.0 / 3.0) * x / hex_size
    rf = ((-1.0 / 3.0) * x + (SQRT3 / 3.0) * y) / hex_size
    return hex_round(qf, rf)


def world_to_norm(
    wx: float,
    wy: float,
    map_w: float,
    map_h: float,
) -> tuple[float, float]:
    return (
        max(0.0, min(1.0, wx / map_w)),
        max(0.0, min(1.0, wy / map_h)),
    )


def grid_origin(hex_size: float, width: int, height: int) -> tuple[float, float]:
    """Top-left padding origin for world-pixel hex grids."""
    return (WORLD_ORIGIN_PADDING, WORLD_ORIGIN_PADDING)


def grid_origin_for_hex_grid(hex_grid: dict) -> tuple[float, float]:
    if hex_grid.get("coordinate_space") == "norm":
        size = float(hex_grid.get("hex_size", 0.026))
        return grid_origin_legacy_norm(size, int(hex_grid["width"]), int(hex_grid["height"]))
    origin = hex_grid.get("origin")
    if isinstance(origin, (list, tuple)) and len(origin) >= 2:
        return float(origin[0]), float(origin[1])
    return grid_origin(
        float(hex_grid.get("hex_size", DEFAULT_HEX_SIZE)),
        int(hex_grid.get("width", DEFAULT_HEX_WIDTH)),
        int(hex_grid.get("height", DEFAULT_HEX_HEIGHT)),
    )


def hex_grid_map_size(hex_grid: dict) -> tuple[float, float]:
    w = int(hex_grid.get("width", DEFAULT_HEX_WIDTH))
    h = int(hex_grid.get("height", DEFAULT_HEX_HEIGHT))
    size = float(hex_grid.get("hex_size", DEFAULT_HEX_SIZE))
    ox, oy = grid_origin_for_hex_grid(hex_grid)
    if hex_grid.get("coordinate_space") == "norm":
        return 1.0, 1.0
    return map_pixel_size(w, h, size, ox, oy)


def hex_key(q: int, r: int) -> str:
    return f"{q},{r}"


def parse_hex_key(key: str) -> tuple[int, int]:
    parts = str(key).split(",", 1)
    return int(parts[0]), int(parts[1])


def axial_to_norm(q: int, r: int, hex_size: float, origin_x: float, origin_y: float) -> tuple[float, float]:
    """Legacy normalized coords (small legacy maps)."""
    nx = origin_x + hex_size * 1.5 * q
    ny = origin_y + hex_size * SQRT3 * (r + q / 2.0)
    return nx, ny


def norm_to_axial(nx: float, ny: float, hex_size: float, origin_x: float, origin_y: float) -> tuple[int, int]:
    return world_to_axial(nx, ny, hex_size, origin_x, origin_y)


def norm_to_axial_legacy(nx: float, ny: float, hex_size: float, origin_x: float, origin_y: float) -> tuple[int, int]:
    x = nx - origin_x
    y = ny - origin_y
    qf = (2.0 / 3.0) * x / hex_size
    rf = ((-1.0 / 3.0) * x + (SQRT3 / 3.0) * y) / hex_size
    return hex_round(qf, rf)


def hex_round(qf: float, rf: float) -> tuple[int, int]:
    sq = -qf - rf
    rq = round(qf)
    rr = round(rf)
    rs = round(sq)
    dq = abs(rq - qf)
    dr = abs(rr - rf)
    ds = abs(rs - sq)
    if dq > dr and dq > ds:
        rq = -rr - rs
    elif dr > ds:
        rr = -rq - rs
    return int(rq), int(rr)


def grid_origin_legacy_norm(hex_size: float, width: int, height: int) -> tuple[float, float]:
    """Center the rectangular axial block in normalized 0–1 space (legacy)."""
    max_q = max(0, width - 1)
    max_r = max(0, height - 1)
    span_x = hex_size * 1.5 * max_q + hex_size * 0.75
    span_y = hex_size * SQRT3 * (max_r + max_q / 2.0)
    origin_x = 0.5 - span_x / 2.0
    origin_y = 0.5 - span_y / 2.0
    return origin_x, origin_y


def neighbors(q: int, r: int) -> list[tuple[int, int]]:
    """Flat-top axial neighbors."""
    return [
        (q + 1, r),
        (q - 1, r),
        (q, r + 1),
        (q, r - 1),
        (q + 1, r - 1),
        (q - 1, r + 1),
    ]


def in_bounds(q: int, r: int, width: int, height: int) -> bool:
    return 0 <= q < width and 0 <= r < height


def empty_hex_grid(
    width: int = DEFAULT_HEX_WIDTH,
    height: int = DEFAULT_HEX_HEIGHT,
    *,
    hex_size: float = DEFAULT_HEX_SIZE,
    encode_rle: Callable[[list[int]], str],
) -> dict:
    cells = [0] * (width * height)
    ox, oy = grid_origin(hex_size, width, height)
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


def decode_hex_cells(hex_grid: dict, decode_rle: Callable[[str, int], list[int]]) -> list[int]:
    w = int(hex_grid.get("width", DEFAULT_HEX_WIDTH))
    h = int(hex_grid.get("height", DEFAULT_HEX_HEIGHT))
    return decode_rle(str(hex_grid.get("cells", "")), w * h)


def encode_hex_cells(cells: list[int], hex_grid: dict, encode_rle: Callable[[list[int]], str]) -> dict:
    out = dict(hex_grid)
    out["cells"] = encode_rle(cells)
    return out


def cell_index(q: int, r: int, width: int) -> int:
    return r * width + q


def get_cell(cells: list[int], q: int, r: int, width: int, height: int) -> int:
    if not in_bounds(q, r, width, height):
        return 0
    return int(cells[cell_index(q, r, width)])


def set_cell(cells: list[int], q: int, r: int, width: int, height: int, code: int) -> None:
    if in_bounds(q, r, width, height):
        cells[cell_index(q, r, width)] = max(0, min(HEX_CELL_MAX, int(code)))


def iter_hexes(width: int, height: int):
    for r in range(height):
        for q in range(width):
            yield q, r


def hex_centroids(hex_grid: dict) -> list[tuple[int, int, float, float]]:
    w = int(hex_grid["width"])
    h = int(hex_grid["height"])
    size = float(hex_grid.get("hex_size", DEFAULT_HEX_SIZE))
    ox, oy = grid_origin_for_hex_grid(hex_grid)
    out: list[tuple[int, int, float, float]] = []
    for q, r in iter_hexes(w, h):
        if hex_grid.get("coordinate_space") == "norm":
            cx, cy = axial_to_norm(q, r, size, ox, oy)
        else:
            cx, cy = axial_to_world(q, r, size, ox, oy)
        out.append((q, r, round(cx, 5), round(cy, 5)))
    return out


def hex_corners_world(
    q: int,
    r: int,
    hex_size: float,
    origin_x: float,
    origin_y: float,
) -> list[list[float]]:
    cx, cy = axial_to_world(q, r, hex_size, origin_x, origin_y)
    pts: list[list[float]] = []
    for i in range(6):
        angle = math.radians(60 * i - 30)
        pts.append([
            round(cx + hex_size * math.cos(angle), 3),
            round(cy + hex_size * math.sin(angle), 3),
        ])
    return pts


def hex_corners_norm(
    q: int,
    r: int,
    hex_size: float,
    origin_x: float,
    origin_y: float,
) -> list[list[float]]:
    cx, cy = axial_to_norm(q, r, hex_size, origin_x, origin_y)
    pts: list[list[float]] = []
    for i in range(6):
        angle = math.radians(60 * i - 30)
        pts.append([
            round(cx + hex_size * math.cos(angle), 5),
            round(cy + hex_size * math.sin(angle), 5),
        ])
    return pts


def point_in_hex(nx: float, ny: float, q: int, r: int, hex_grid: dict) -> bool:
    size = float(hex_grid.get("hex_size", DEFAULT_HEX_SIZE))
    ox, oy = grid_origin_for_hex_grid(hex_grid)
    if hex_grid.get("coordinate_space") == "norm":
        corners = hex_corners_norm(q, r, size, ox, oy)
    else:
        corners = hex_corners_world(q, r, size, ox, oy)
    return _point_in_polygon(nx, ny, corners)


def _point_in_polygon(x: float, y: float, polygon: list[list[float]]) -> bool:
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


def nearest_hex(nx: float, ny: float, hex_grid: dict) -> tuple[int, int] | None:
    w = int(hex_grid["width"])
    h = int(hex_grid["height"])
    size = float(hex_grid.get("hex_size", DEFAULT_HEX_SIZE))
    ox, oy = grid_origin_for_hex_grid(hex_grid)
    if hex_grid.get("coordinate_space") == "norm":
        q, r = norm_to_axial_legacy(nx, ny, size, ox, oy)
    else:
        q, r = world_to_axial(nx, ny, size, ox, oy)
    if in_bounds(q, r, w, h):
        return q, r
    best = None
    best_d = float("inf")
    for hq, hr, cx, cy in hex_centroids(hex_grid):
        d = (cx - nx) ** 2 + (cy - ny) ** 2
        if d < best_d:
            best_d = d
            best = (hq, hr)
    return best


def land_code(code: int) -> bool:
    return code >= 1
