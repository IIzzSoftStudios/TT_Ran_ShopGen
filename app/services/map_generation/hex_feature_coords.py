"""Feature point helpers for world-space hex grids."""

from __future__ import annotations

from app.services.map_generation import hex_grid as hg


def _clamp_pt(x: float, y: float) -> list[float]:
    return [round(max(0.0, min(1.0, x)), 4), round(max(0.0, min(1.0, y)), 4)]


def hex_corners_for_feature(hex_grid: dict, q: int, r: int) -> list[list[float]]:
    size = float(hex_grid.get("hex_size", hg.DEFAULT_HEX_SIZE))
    ox, oy = hg.grid_origin_for_hex_grid(hex_grid)
    if hex_grid.get("coordinate_space") == "norm":
        return hg.hex_corners_norm(q, r, size, ox, oy)
    return hg.hex_corners_world(q, r, size, ox, oy)


def axial_feature_point(hex_grid: dict, q: int, r: int) -> list[float]:
    size = float(hex_grid.get("hex_size", hg.DEFAULT_HEX_SIZE))
    ox, oy = hg.grid_origin_for_hex_grid(hex_grid)
    if hex_grid.get("coordinate_space") == "norm":
        return _clamp_pt(*hg.axial_to_norm(q, r, size, ox, oy))
    wx, wy = hg.axial_to_world(q, r, size, ox, oy)
    mw, mh = hg.hex_grid_map_size(hex_grid)
    return _clamp_pt(wx / mw, wy / mh)


def normalize_corner_points(hex_grid: dict, corners: list[list[float]]) -> list[list[float]]:
    if hex_grid.get("coordinate_space") == "norm":
        return [_clamp_pt(p[0], p[1]) for p in corners]
    mw, mh = hg.hex_grid_map_size(hex_grid)
    return [_clamp_pt(p[0] / mw, p[1] / mh) for p in corners]
