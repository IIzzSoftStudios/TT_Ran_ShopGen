"""Voronoi sites, Lloyd relaxation, and cell polygon extraction (numpy-only)."""

from __future__ import annotations

import math
import random
from typing import Callable

import numpy as np

GRID_W = 128
GRID_H = 96


def _round_pt(x: float, y: float) -> list[float]:
    return [round(max(0.0, min(1.0, x)), 4), round(max(0.0, min(1.0, y)), 4)]


def point_in_polygon(x: float, y: float, polygon: list[list[float]]) -> bool:
    if len(polygon) < 3:
        return False
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


def land_mask_from_polygon(
    polygon: list[list[float]],
    width: int = GRID_W,
    height: int = GRID_H,
) -> np.ndarray:
    """Boolean mask True where normalized point lies inside polygon."""
    mask = np.zeros((height, width), dtype=bool)
    for gy in range(height):
        ny = (gy + 0.5) / height
        for gx in range(width):
            nx = (gx + 0.5) / width
            if point_in_polygon(nx, ny, polygon):
                mask[gy, gx] = True
    return mask


def land_mask_rect(
    width: int = GRID_W,
    height: int = GRID_H,
    margin: float = 0.06,
) -> np.ndarray:
    """Full interior rectangle mask for shop floors."""
    mask = np.zeros((height, width), dtype=bool)
    x0 = int(margin * width)
    x1 = int((1.0 - margin) * width)
    y0 = int(margin * height)
    y1 = int((1.0 - margin) * height)
    mask[y0:y1, x0:x1] = True
    return mask


def poisson_disk_sites(
    rng: random.Random,
    mask: np.ndarray,
    count: int,
    min_dist: float = 0.04,
) -> list[list[float]]:
    """Place sites with minimum separation inside mask (normalized coords)."""
    height, width = mask.shape
    sites: list[list[float]] = []
    attempts = 0
    max_attempts = count * 200
    while len(sites) < count and attempts < max_attempts:
        attempts += 1
        gx = rng.randint(0, width - 1)
        gy = rng.randint(0, height - 1)
        if not mask[gy, gx]:
            continue
        nx = (gx + 0.5) / width
        ny = (gy + 0.5) / height
        ok = True
        for sx, sy in sites:
            if (nx - sx) ** 2 + (ny - sy) ** 2 < min_dist * min_dist:
                ok = False
                break
        if ok:
            sites.append([nx, ny])
    # Fill remainder on mask centroids if Poisson under-filled
    while len(sites) < count:
        gx = rng.randint(0, width - 1)
        gy = rng.randint(0, height - 1)
        if mask[gy, gx]:
            sites.append([(gx + 0.5) / width, (gy + 0.5) / height])
        if len(sites) >= count or attempts > max_attempts * 2:
            break
        attempts += 1
    return sites[:count]


def assign_sites_to_grid(
    sites: list[list[float]],
    mask: np.ndarray,
) -> np.ndarray:
    """Return int grid of site index (-1 outside mask)."""
    height, width = mask.shape
    n = len(sites)
    if n == 0:
        return np.full((height, width), -1, dtype=np.int32)
    site_arr = np.array(sites, dtype=np.float64)
    grid = np.full((height, width), -1, dtype=np.int32)
    for gy in range(height):
        ny = (gy + 0.5) / height
        for gx in range(width):
            if not mask[gy, gx]:
                continue
            nx = (gx + 0.5) / width
            d2 = (site_arr[:, 0] - nx) ** 2 + (site_arr[:, 1] - ny) ** 2
            grid[gy, gx] = int(np.argmin(d2))
    return grid


def lloyd_relax(
    sites: list[list[float]],
    mask: np.ndarray,
    iterations: int = 4,
) -> list[list[float]]:
    """Lloyd relaxation: move sites to centroid of assigned Voronoi regions."""
    height, width = mask.shape
    current = [list(s) for s in sites]
    for _ in range(iterations):
        grid = assign_sites_to_grid(current, mask)
        new_sites: list[list[float]] = []
        for idx in range(len(current)):
            ys, xs = np.where(grid == idx)
            if len(xs) == 0:
                new_sites.append(current[idx])
                continue
            cx = float(np.mean((xs + 0.5) / width))
            cy = float(np.mean((ys + 0.5) / height))
            new_sites.append(_round_pt(cx, cy))
        current = new_sites
    return current


def extract_cell_polygon(
    grid: np.ndarray,
    cell_id: int,
    width: int,
    height: int,
) -> list[list[float]]:
    """Trace simplified boundary polygon for one cell from grid assignment."""
    # Collect boundary edge midpoints
    edges: list[tuple[float, float]] = []
    for gy in range(height):
        for gx in range(width):
            if grid[gy, gx] != cell_id:
                continue
            nx = (gx + 0.5) / width
            ny = (gy + 0.5) / height
            for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
                nx2, ny2 = gx + dx, gy + dy
                neighbor = -1
                if 0 <= nx2 < width and 0 <= ny2 < height:
                    neighbor = int(grid[ny2, nx2])
                if neighbor != cell_id:
                    edges.append((nx, ny))
    if not edges:
        return []
    # Convex hull-ish: sort by angle from centroid
    cx = sum(e[0] for e in edges) / len(edges)
    cy = sum(e[1] for e in edges) / len(edges)

    def angle_key(p: tuple[float, float]) -> float:
        return math.atan2(p[1] - cy, p[0] - cx)

    hull = sorted(set(edges), key=angle_key)
    # Simplify to max 8 vertices
    if len(hull) > 8:
        step = max(1, len(hull) // 8)
        hull = hull[::step][:8]
    return [_round_pt(x, y) for x, y in hull]


def build_adjacency(grid: np.ndarray, n_cells: int) -> list[list[int]]:
    """Adjacency from shared grid edges between cell ids."""
    height, width = grid.shape
    adj: list[set[int]] = [set() for _ in range(n_cells)]
    for gy in range(height):
        for gx in range(width):
            cid = int(grid[gy, gx])
            if cid < 0:
                continue
            for dx, dy in ((1, 0), (0, 1)):
                nx2, ny2 = gx + dx, gy + dy
                if nx2 >= width or ny2 >= height:
                    continue
                nid = int(grid[ny2, nx2])
                if nid >= 0 and nid != cid:
                    adj[cid].add(nid)
                    adj[nid].add(cid)
    return [sorted(s) for s in adj]


def build_voronoi_cells(
    sites: list[list[float]],
    mask: np.ndarray,
    lloyd_iterations: int = 4,
) -> tuple[list[dict], list[list[int]], np.ndarray]:
    """Run Lloyd relaxation and build cell records + adjacency + assignment grid."""
    height, width = mask.shape
    relaxed = lloyd_relax(sites, mask, lloyd_iterations)
    grid = assign_sites_to_grid(relaxed, mask)
    n = len(relaxed)
    adjacency = build_adjacency(grid, n)
    cells: list[dict] = []
    for idx in range(n):
        polygon = extract_cell_polygon(grid, idx, width, height)
        if len(polygon) < 3:
            polygon = [
                _round_pt(relaxed[idx][0] - 0.02, relaxed[idx][1] - 0.02),
                _round_pt(relaxed[idx][0] + 0.02, relaxed[idx][1] - 0.02),
                _round_pt(relaxed[idx][0] + 0.02, relaxed[idx][1] + 0.02),
                _round_pt(relaxed[idx][0] - 0.02, relaxed[idx][1] + 0.02),
            ]
        cells.append(
            {
                "id": idx,
                "polygon": polygon,
                "centroid": list(relaxed[idx]),
                "elevation": 0.0,
                "moisture": 0.5,
                "biome": "land",
                "terrain_code": 1,
                "label": "",
            }
        )
    return cells, adjacency, grid


def sites_from_terrain_grid(
    cells_rle: list[int],
    grid_width: int,
    grid_height: int,
    rng: random.Random,
    target_count: int,
) -> list[list[float]]:
    """Sample Voronoi sites from land cells in an existing terrain grid."""
    land_pts: list[tuple[float, float]] = []
    for gy in range(grid_height):
        ny = (gy + 0.5) / grid_height
        for gx in range(grid_width):
            code = cells_rle[gy * grid_width + gx]
            if code in (1, 2, 3, 4):
                land_pts.append(((gx + 0.5) / grid_width, (gy + 0.5) / grid_height))
    if not land_pts:
        return poisson_disk_sites(
            rng,
            land_mask_rect(grid_width, grid_height, 0.1),
            target_count,
        )
    rng.shuffle(land_pts)
    step = max(1, len(land_pts) // target_count)
    sampled = land_pts[::step][:target_count]
    while len(sampled) < target_count:
        sampled.append(rng.choice(land_pts))
    return [_round_pt(x, y) for x, y in sampled[:target_count]]
