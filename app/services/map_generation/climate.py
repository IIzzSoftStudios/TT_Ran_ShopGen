"""Wind-driven moisture and rain-shadow biome assignment."""

from __future__ import annotations

import math
from typing import Any


MOUNTAIN_ELEV_THRESHOLD = 0.55
PRECIP_BOOST = 0.35
RAIN_SHADOW_DRY = 0.25


def wind_vector_from_profile(profile: dict) -> list[float]:
    """West=0, East=1 on 0-10 wind_direction slider; default W→E."""
    wd = float(profile.get("wind_direction", 2.5))
    # 0 = west wind (blows +x), 5 = north, 10 = east (-x) — use simple axis
    angle = math.pi * (1.0 - wd / 10.0)  # 0→π (W to E reversed for blow direction)
    return [round(math.cos(angle), 4), round(math.sin(angle), 4)]


def apply_climate(
    cells: list[dict],
    adjacency: list[list[int]],
    wind_vector: list[float],
    *,
    moisture_strength: float = 0.85,
    scope: str = "world",
    water_cell_ids: set[int] | None = None,
) -> None:
    """Mutates cells: moisture transport + rain shadow + biome/terrain_code."""
    water_cell_ids = water_cell_ids or set()
    n = len(cells)
    if n == 0:
        return

    wx, wy = float(wind_vector[0]), float(wind_vector[1])
    wind_len = math.hypot(wx, wy) or 1.0
    wx, wy = wx / wind_len, wy / wind_len

    # Sort cells upwind to downwind
    order = sorted(
        range(n),
        key=lambda i: float(cells[i]["centroid"][0]) * wx + float(cells[i]["centroid"][1]) * wy,
    )

    moisture = [0.3] * n
    for i in order:
        if i in water_cell_ids:
            moisture[i] = 1.0
            continue
        # Seed from coastal adjacency to water
        for nb in adjacency[i]:
            if nb in water_cell_ids:
                moisture[i] = max(moisture[i], 0.9)
        # Inherit from upwind neighbors
        for nb in adjacency[i]:
            nb_proj = (
                float(cells[nb]["centroid"][0]) * wx + float(cells[nb]["centroid"][1]) * wy
            )
            my_proj = (
                float(cells[i]["centroid"][0]) * wx + float(cells[i]["centroid"][1]) * wy
            )
            if nb_proj < my_proj - 1e-6:
                moisture[i] = max(moisture[i], moisture[nb] * moisture_strength)

    # Rain shadow on mountain cells
    for i in order:
        elev = float(cells[i].get("elevation", 0))
        if elev < MOUNTAIN_ELEV_THRESHOLD:
            continue
        for nb in adjacency[i]:
            nb_proj = (
                float(cells[nb]["centroid"][0]) * wx + float(cells[nb]["centroid"][1]) * wy
            )
            my_proj = (
                float(cells[i]["centroid"][0]) * wx + float(cells[i]["centroid"][1]) * wy
            )
            if nb_proj < my_proj:
                moisture[nb] = min(1.0, moisture[nb] + PRECIP_BOOST)
            else:
                moisture[nb] = max(0.0, moisture[nb] - RAIN_SHADOW_DRY)

    for i, cell in enumerate(cells):
        if i in water_cell_ids:
            cell["moisture"] = 1.0
            cell["biome"] = "water"
            cell["terrain_code"] = 0
            continue
        cell["moisture"] = round(min(1.0, moisture[i]), 4)
        elev = float(cell.get("elevation", 0))
        m = cell["moisture"]
        biome, code = _biome_for_cell(elev, m, scope)
        cell["biome"] = biome
        cell["terrain_code"] = code


def _biome_for_cell(elevation: float, moisture: float, scope: str) -> tuple[str, int]:
    if scope == "world":
        if elevation >= MOUNTAIN_ELEV_THRESHOLD:
            return "mountain", 2
        if moisture >= 0.55:
            return "forest", 3
        if moisture < 0.28:
            return "desert", 4
        return "land", 1
    if scope == "city":
        if moisture >= 0.7:
            return "canal", 2
        if moisture >= 0.45:
            return "park", 3
        if elevation >= 0.5:
            return "road", 4
        return "district", 1
    # shop
    if moisture >= 0.6:
        return "storage", 3
    if elevation >= 0.5:
        return "counter", 4
    return "floor", 1
