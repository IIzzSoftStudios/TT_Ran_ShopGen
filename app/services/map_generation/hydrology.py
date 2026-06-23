"""Downhill river tracing on cell adjacency graph."""

from __future__ import annotations

from typing import Any


def trace_rivers(
    cells: list[dict],
    adjacency: list[list[int]],
    water_cell_ids: set[int],
    *,
    max_rivers: int = 6,
    source_elev_min: float = 0.5,
) -> list[dict]:
    """Greedy downhill paths from mountain sources to water."""
    n = len(cells)
    if n == 0:
        return []

    elevations = [float(c.get("elevation", 0)) for c in cells]
    sources = [
        i for i in range(n)
        if i not in water_cell_ids and elevations[i] >= source_elev_min
    ]
    sources.sort(key=lambda i: elevations[i], reverse=True)
    sources = sources[: max_rivers * 2]

    rivers: list[dict] = []
    used_sources: set[int] = set()
    path_cells_global: set[int] = set()

    for src in sources:
        if len(rivers) >= max_rivers:
            break
        if src in used_sources:
            continue
        path = [src]
        current = src
        visited = {src}
        for _ in range(n * 2):
            if current in water_cell_ids:
                break
            neighbors = [
                nb for nb in adjacency[current]
                if nb not in visited
            ]
            if not neighbors:
                # Step to any lower neighbor even if visited tributary merge
                neighbors = list(adjacency[current])
            if not neighbors:
                break
            lowest = min(neighbors, key=lambda nb: elevations[nb])
            if elevations[lowest] >= elevations[current] and current not in water_cell_ids:
                # Allow equal step toward water
                water_nb = [nb for nb in neighbors if nb in water_cell_ids]
                if water_nb:
                    lowest = water_nb[0]
                elif elevations[lowest] >= elevations[current]:
                    break
            current = lowest
            if current in visited and current not in water_cell_ids:
                break
            visited.add(current)
            path.append(current)
            if current in water_cell_ids:
                break

        if len(path) < 2:
            continue
        if path[-1] not in water_cell_ids:
            continue
        used_sources.add(src)
        rivers.append({
            "id": f"r{len(rivers)}",
            "cell_path": path,
            "tributaries": [],
        })
        path_cells_global.update(path)

    return rivers


def shortest_path_cells(
    cells: list[dict],
    adjacency: list[list[int]],
    start_id: int,
    end_id: int,
) -> list[int]:
    """BFS shortest path on cell adjacency for trade routes."""
    if start_id == end_id:
        return [start_id]
    from collections import deque

    queue: deque[list[int]] = deque([[start_id]])
    visited = {start_id}
    while queue:
        path = queue.popleft()
        node = path[-1]
        for nb in adjacency[node]:
            if nb in visited:
                continue
            new_path = path + [nb]
            if nb == end_id:
                return new_path
            visited.add(nb)
            queue.append(new_path)
    return [start_id, end_id]
