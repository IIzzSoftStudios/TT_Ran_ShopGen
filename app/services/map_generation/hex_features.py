"""Derive vector features from a hex_grid for overlay rendering."""

from __future__ import annotations

from typing import Callable

from app.services.map_generation import hex_grid as hg
from app.services.map_generation.hex_feature_coords import (
    axial_feature_point,
    hex_corners_for_feature,
    normalize_corner_points,
    _clamp_pt,
)


def _convex_hull(points: list[list[float]]) -> list[list[float]]:
    if len(points) < 3:
        return points
    pts = sorted(set((round(p[0], 4), round(p[1], 4)) for p in points))

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    return [[p[0], p[1]] for p in hull]


def _connected_components(
    cells: list[int],
    width: int,
    height: int,
    predicate,
) -> list[list[tuple[int, int]]]:
    seen: set[tuple[int, int]] = set()
    comps: list[list[tuple[int, int]]] = []
    for q, r in hg.iter_hexes(width, height):
        if (q, r) in seen:
            continue
        idx = hg.cell_index(q, r, width)
        if not predicate(cells[idx]):
            continue
        comp: list[tuple[int, int]] = []
        stack = [(q, r)]
        while stack:
            cq, cr = stack.pop()
            if (cq, cr) in seen:
                continue
            cidx = hg.cell_index(cq, cr, width)
            if not predicate(cells[cidx]):
                continue
            seen.add((cq, cr))
            comp.append((cq, cr))
            for nq, nr in hg.neighbors(cq, cr):
                if hg.in_bounds(nq, nr, width, height) and (nq, nr) not in seen:
                    stack.append((nq, nr))
        if comp:
            comps.append(comp)
    return comps


def _component_hull(
    comp: list[tuple[int, int]],
    hex_grid: dict,
) -> list[list[float]]:
    size = float(hex_grid.get("hex_size", hg.DEFAULT_HEX_SIZE))
    pts: list[list[float]] = []
    for q, r in comp:
        corners = hex_corners_for_feature(hex_grid, q, r)
        pts.extend(normalize_corner_points(hex_grid, corners))
    hull = _convex_hull(pts)
    return [_clamp_pt(p[0], p[1]) for p in hull] if len(hull) >= 3 else []


def _mountain_chains(
    cells: list[int],
    width: int,
    height: int,
    hex_grid: dict,
) -> list[dict]:
    mountains = [(q, r) for q, r in hg.iter_hexes(width, height) if cells[hg.cell_index(q, r, width)] == 2]
    if len(mountains) < 3:
        return []
    mountains.sort(key=lambda t: t[0])
    step = max(1, len(mountains) // 4)
    chain = mountains[::step][:5]
    if len(chain) < 2:
        return []
    pts = [axial_feature_point(hex_grid, q, r) for q, r in chain]
    return [{
        "type": "mountain_range",
        "points": pts,
        "peak_scale": [round(0.8 + i * 0.12, 3) for i in range(len(pts))],
    }]


def _rivers(
    cells: list[int],
    width: int,
    height: int,
    hex_grid: dict,
    max_rivers: int,
) -> list[dict]:
    rivers: list[dict] = []
    candidates = [
        (q, r)
        for q, r in hg.iter_hexes(width, height)
        if cells[hg.cell_index(q, r, width)] == 2
    ]
    candidates.sort(key=lambda t: t[0])
    for q, r in candidates[:max_rivers]:
        path: list[list[float]] = []
        cq, cr = q, r
        for _ in range(width + height):
            path.append(axial_feature_point(hex_grid, cq, cr))
            if not hg.in_bounds(cq, cr, width, height):
                break
            if cells[hg.cell_index(cq, cr, width)] == 0:
                break
            best = None
            best_e = float("inf")
            for nq, nr in hg.neighbors(cq, cr):
                if not hg.in_bounds(nq, nr, width, height):
                    best = (nq, nr)
                    best_e = -1.0
                    continue
                code = cells[hg.cell_index(nq, nr, width)]
                elev = 0.0 if code == 0 else (0.9 if code == 2 else 0.3)
                if elev < best_e:
                    best_e = elev
                    best = (nq, nr)
            if best is None:
                break
            cq, cr = best
            if not hg.in_bounds(cq, cr, width, height) or cells[hg.cell_index(cq, cr, width)] == 0:
                path.append(axial_feature_point(hex_grid, cq, cr))
                break
        if len(path) >= 2:
            rivers.append({"type": "river", "points": path})
    return rivers


def _trade_routes(
    cells: list[int],
    width: int,
    height: int,
    hex_grid: dict,
    profile: dict,
) -> list[dict]:
    land = [
        (q, r)
        for q, r in hg.iter_hexes(width, height)
        if hg.land_code(cells[hg.cell_index(q, r, width)])
    ]
    if len(land) < 2:
        return []
    economy = float(profile.get("economy_density", 5))
    route_count = max(1, min(4, int(1 + economy / 3)))
    land.sort(key=lambda t: (t[0], t[1]))
    step = max(1, len(land) // (route_count + 1))
    hubs = land[step::step][: route_count + 1]
    routes: list[dict] = []
    for i in range(len(hubs) - 1):
        q0, r0 = hubs[i]
        q1, r1 = hubs[i + 1]
        routes.append({
            "type": "trade_route",
            "points": [
                axial_feature_point(hex_grid, q0, r0),
                axial_feature_point(hex_grid, q1, r1),
            ],
        })
    return routes


def derive_features_from_hex_grid(
    hex_grid: dict,
    profile: dict,
    decode_rle: Callable[[str, int], list[int]],
) -> list[dict]:
    width = int(hex_grid["width"])
    height = int(hex_grid["height"])
    cells = decode_rle(str(hex_grid.get("cells", "")), width * height)
    features: list[dict] = []

    land_comps = _connected_components(cells, width, height, hg.land_code)
    land_comps.sort(key=len, reverse=True)
    if land_comps:
        main_hull = _component_hull(land_comps[0], hex_grid)
        if main_hull:
            features.append({"type": "landmass", "points": main_hull})
        for comp in land_comps[1:]:
            if len(comp) < 2:
                continue
            hull = _component_hull(comp, hex_grid)
            if hull:
                features.append({"type": "island", "points": hull})

    return features


DISTRICT_LABELS = ("Market", "Docks", "Guilds", "Temple", "Commons", "Old Town")


def _road_paths(
    cells: list[int],
    width: int,
    height: int,
    hex_grid: dict,
    profile: dict,
) -> list[dict]:
    road_hexes = [
        (q, r)
        for q, r in hg.iter_hexes(width, height)
        if cells[hg.cell_index(q, r, width)] == 4
    ]
    if len(road_hexes) < 2:
        return []
    economy = float(profile.get("economy_density", 5))
    route_count = max(1, min(4, int(1 + economy / 3)))
    road_hexes.sort(key=lambda t: (t[0], t[1]))
    step = max(1, len(road_hexes) // (route_count + 1))
    hubs = road_hexes[step::step][: route_count + 1]
    routes: list[dict] = []
    for i in range(len(hubs) - 1):
        q0, r0 = hubs[i]
        q1, r1 = hubs[i + 1]
        routes.append({
            "type": "road",
            "points": [
                axial_feature_point(hex_grid, q0, r0),
                axial_feature_point(hex_grid, q1, r1),
            ],
        })
    return routes


def derive_city_features_from_hex_grid(
    hex_grid: dict,
    profile: dict,
    decode_rle: Callable[[str, int], list[int]],
) -> list[dict]:
    width = int(hex_grid["width"])
    height = int(hex_grid["height"])
    cells = decode_rle(str(hex_grid.get("cells", "")), width * height)
    features: list[dict] = []

    city_comps = _connected_components(cells, width, height, lambda c: c >= 1)
    city_comps.sort(key=len, reverse=True)

    stored_wall = hex_grid.get("city_wall_polygon")
    if isinstance(stored_wall, list) and len(stored_wall) >= 3:
        features.append({"type": "city_wall", "points": stored_wall})
    elif city_comps:
        wall_hull = _component_hull(city_comps[0], hex_grid)
        if wall_hull:
            features.append({"type": "city_wall", "points": wall_hull})

    district_comps = _connected_components(cells, width, height, lambda c: c in (1, 5))
    for idx, comp in enumerate(district_comps[:12]):
        if len(comp) < 2:
            continue
        hull = _component_hull(comp, hex_grid)
        if hull:
            features.append({
                "type": "district",
                "label": f"District {DISTRICT_LABELS[idx % len(DISTRICT_LABELS)]}",
                "points": hull,
            })

    canal_comps = _connected_components(cells, width, height, lambda c: c == 2)
    for comp in canal_comps[:8]:
        if len(comp) < 2:
            continue
        hull = _component_hull(comp, hex_grid)
        if hull:
            features.append({"type": "canal", "points": hull})

    park_comps = _connected_components(cells, width, height, lambda c: c == 3)
    for comp in park_comps[:10]:
        if len(comp) < 2:
            continue
        hull = _component_hull(comp, hex_grid)
        if hull:
            features.append({"type": "park", "points": hull})

    features.extend(_road_paths(cells, width, height, hex_grid, profile))

    return features


SHOP_ROOM_LABELS = ("Sales floor", "Counter", "Display", "Storage", "Back room")


def derive_shop_features_from_hex_grid(
    hex_grid: dict,
    profile: dict,
    decode_rle: Callable[[str, int], list[int]],
) -> list[dict]:
    width = int(hex_grid["width"])
    height = int(hex_grid["height"])
    cells = decode_rle(str(hex_grid.get("cells", "")), width * height)
    features: list[dict] = []

    stored_wall = hex_grid.get("city_wall_polygon")
    if isinstance(stored_wall, list) and len(stored_wall) >= 3:
        features.append({"type": "city_wall", "points": stored_wall})

    room_specs = (
        (2, "Counter"),
        (3, "Display"),
        (5, "Shelves"),
        (4, "Aisles"),
        (1, "Floor"),
    )
    for code, label in room_specs:
        comps = _connected_components(cells, width, height, lambda c, tc=code: c == tc)
        for idx, comp in enumerate(comps[:6]):
            if len(comp) < 2:
                continue
            hull = _component_hull(comp, hex_grid)
            if hull:
                features.append({
                    "type": "district",
                    "label": label if idx == 0 else f"{label} {idx + 1}",
                    "points": hull,
                })

    features.extend(_road_paths(cells, width, height, hex_grid, profile))

    return features
