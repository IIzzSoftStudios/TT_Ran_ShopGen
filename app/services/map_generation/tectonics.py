"""Tectonic spline elevation model."""

from __future__ import annotations

import math
from typing import Any


def _dist_point_to_segment(
    px: float, py: float,
    x1: float, y1: float,
    x2: float, y2: float,
) -> float:
    dx, dy = x2 - x1, y2 - y1
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-12:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / len_sq))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def dist_point_to_polyline(px: float, py: float, points: list[list[float]]) -> float:
    if len(points) < 2:
        if points:
            return math.hypot(px - points[0][0], py - points[0][1])
        return 1.0
    best = float("inf")
    for i in range(len(points) - 1):
        d = _dist_point_to_segment(
            px, py,
            float(points[i][0]), float(points[i][1]),
            float(points[i + 1][0]), float(points[i + 1][1]),
        )
        best = min(best, d)
    return best


def apply_tectonic_elevation(
    cells: list[dict],
    tectonic_lines: list[dict],
    *,
    sigma: float = 0.08,
    water_cell_ids: set[int] | None = None,
) -> None:
    """Mutates cells in place with elevation from distance to tectonic splines."""
    water_cell_ids = water_cell_ids or set()
    for cell in cells:
        cid = int(cell["id"])
        if cid in water_cell_ids:
            cell["elevation"] = 0.0
            continue
        cx, cy = float(cell["centroid"][0]), float(cell["centroid"][1])
        elev = 0.0
        for line in tectonic_lines:
            pts = line.get("points") or []
            strength = float(line.get("strength", 1.0))
            dist = dist_point_to_polyline(cx, cy, pts)
            elev = max(elev, strength * math.exp(-dist / sigma))
        cell["elevation"] = round(min(1.0, elev), 4)


def default_tectonic_lines(
    rng: Any,
    rough: float,
    land_center: tuple[float, float] = (0.48, 0.52),
) -> list[dict]:
    """Generate 1-3 mountain spine polylines like legacy generate_canvas_background."""
    import random

    if not isinstance(rng, random.Random):
        rng = random.Random(int(rng) & 0x7FFFFFFF)
    count = max(1, int(1 + rough / 2))
    lines: list[dict] = []
    for i in range(count):
        start = (rng.uniform(0.16, 0.34), rng.uniform(0.16, 0.78))
        end = (rng.uniform(0.58, 0.86), rng.uniform(0.18, 0.76))
        bends = rng.randint(3, 5)
        points = [list(start)]
        for b in range(1, bends + 1):
            t = b / (bends + 1)
            mx = start[0] + (end[0] - start[0]) * t + rng.uniform(-0.04, 0.04)
            my = start[1] + (end[1] - start[1]) * t + rng.uniform(-0.04, 0.04)
            points.append([round(max(0, min(1, mx)), 4), round(max(0, min(1, my)), 4)])
        points.append(list(end))
        lines.append({"id": f"t{i}", "points": points, "strength": 1.0})
    return lines
