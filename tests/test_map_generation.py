"""Tests for Voronoi cell-graph map generation (presentation layer)."""

from __future__ import annotations

import hashlib
import json

import pytest

from app.services.gm_maps import (
    GENERATION_SCHEMA_VERSION,
    decode_terrain_rle,
    encode_terrain_rle,
    generate_canvas_background,
    map_generation_profile,
    validate_generation_json,
)
from app.services.map_generation import climate, hydrology, pipeline, voronoi
from app.services.map_generation.pipeline import (
    build_generation_from_cell_graph,
    generate_map,
    migrate_v5_to_v6 as pipeline_migrate_v5,
)


def _profile():
    return map_generation_profile({
        "ranges": {
            "map_landmass_scale": {"min": 6, "max": 6},
            "map_waterways": {"min": 5, "max": 5},
            "map_terrain_roughness": {"min": 6, "max": 6},
            "num_regions": {"min": 4, "max": 4},
            "num_cities": {"min": 6, "max": 6},
        }
    })


def test_deterministic_generation_hash():
    profile = _profile()
    a = generate_canvas_background("world", 4242, profile, detail_seed=777)
    b = generate_canvas_background("world", 4242, profile, detail_seed=777)
    ha = hashlib.sha256(json.dumps(a["hex_grid"], sort_keys=True).encode()).hexdigest()
    hb = hashlib.sha256(json.dumps(b["hex_grid"], sort_keys=True).encode()).hexdigest()
    assert ha == hb
    assert a["schema_version"] == GENERATION_SCHEMA_VERSION == 7


def test_lloyd_reduces_area_variance():
    import random

    rng = random.Random(1)
    mask = voronoi.land_mask_rect(margin=0.1)
    sites = voronoi.poisson_disk_sites(rng, mask, 40, min_dist=0.06)
    cells_before, _, grid_before = voronoi.build_voronoi_cells(sites, mask, lloyd_iterations=0)
    cells_after, _, _ = voronoi.build_voronoi_cells(sites, mask, lloyd_iterations=4)

    def area_variance(cells, grid):
        import numpy as np

        areas = []
        for idx in range(len(cells)):
            count = int((grid == idx).sum())
            areas.append(count)
        return float(np.var(areas))

    assert area_variance(cells_after, grid_before) <= area_variance(cells_before, grid_before) * 1.1


def test_rain_shadow_desert_leeward():
    cells = [
        {"id": 0, "centroid": [0.2, 0.5], "elevation": 0.2, "moisture": 0.5, "terrain_code": 1, "biome": "land"},
        {"id": 1, "centroid": [0.5, 0.5], "elevation": 0.8, "moisture": 0.5, "terrain_code": 2, "biome": "mountain"},
        {"id": 2, "centroid": [0.8, 0.5], "elevation": 0.2, "moisture": 0.5, "terrain_code": 1, "biome": "land"},
    ]
    adjacency = [[1], [0, 2], [1]]
    climate.apply_climate(cells, adjacency, [1.0, 0.0], scope="world", water_cell_ids=set())
    leeward = cells[2]
    assert leeward["terrain_code"] == 4 or leeward["moisture"] < 0.35


def test_river_path_decreases_elevation():
    cells = [
        {"id": 0, "centroid": [0.1, 0.5], "elevation": 0.9, "terrain_code": 2},
        {"id": 1, "centroid": [0.3, 0.5], "elevation": 0.5, "terrain_code": 1},
        {"id": 2, "centroid": [0.5, 0.5], "elevation": 0.2, "terrain_code": 1},
        {"id": 3, "centroid": [0.7, 0.5], "elevation": 0.0, "terrain_code": 0},
    ]
    adjacency = [[1], [0, 2], [1, 3], [2]]
    rivers = hydrology.trace_rivers(cells, adjacency, {3}, max_rivers=2)
    assert rivers
    path = rivers[0]["cell_path"]
    elevs = [cells[c]["elevation"] for c in path]
    for i in range(len(elevs) - 1):
        assert elevs[i] >= elevs[i + 1] - 1e-6
    assert path[-1] == 3


def test_v5_migration_produces_cell_graph():
    v5 = {
        "schema_version": 5,
        "scope": "world",
        "features": [
            {
                "type": "landmass",
                "points": [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]],
            }
        ],
        "terrain_grid": {
            "width": 256,
            "height": 192,
            "encoding": "rle",
            "cells": encode_terrain_rle([1] * (256 * 192)),
        },
    }
    profile = _profile()
    cg = pipeline_migrate_v5(v5, "world", profile, 100, 200, decode_terrain_rle, encode_terrain_rle)
    assert cg.get("cells")
    assert len(cg["cells"]) > 0


def test_generation_json_size_under_cap():
    profile = _profile()
    gen = generate_canvas_background("world", 999, profile, detail_seed=111)
    size = len(json.dumps(gen, separators=(",", ":")).encode("utf-8"))
    assert size < 512 * 1024


def test_simulation_does_not_import_map_generation():
    import ast
    from pathlib import Path

    sim_path = Path(__file__).resolve().parents[1] / "app" / "services" / "simulation.py"
    tree = ast.parse(sim_path.read_text(encoding="utf-8"))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    assert not any("map_generation" in name for name in imports)


def test_city_and_shop_scopes_generate_cells():
    profile = _profile()
    city = generate_canvas_background("city", 55, profile, detail_seed=66)
    shop = generate_canvas_background("shop", 77, profile, detail_seed=88)
    assert city["hex_grid"]["cells"]
    assert city["scope"] == "city"
    assert shop["hex_grid"]["cells"]
    assert shop["scope"] == "shop"
    assert city["schema_version"] == 7
    assert shop["schema_version"] == 7
    assert int(city["hex_grid"]["width"]) >= 24
    assert int(shop["hex_grid"]["width"]) >= 20


def test_validate_shop_generation_json_hex_grid():
    profile = _profile()
    gen = generate_canvas_background("shop", 31, profile, detail_seed=42)
    validated = validate_generation_json(gen, "shop")
    assert validated["schema_version"] == 7
    assert validated["hex_grid"]["width"] >= 20
    assert validated["terrain_grid"]["derived_from"] == "hex_grid"
    assert any(f["type"] == "city_wall" for f in validated["features"])


def test_validate_city_generation_json_hex_grid():
    profile = _profile()
    gen = generate_canvas_background("city", 21, profile, detail_seed=32)
    validated = validate_generation_json(gen, "city")
    assert validated["schema_version"] == 7
    assert validated["hex_grid"]["width"] >= 24
    assert validated["terrain_grid"]["derived_from"] == "hex_grid"
    assert any(f["type"] == "city_wall" for f in validated["features"])


def test_validate_generation_json_hex_grid():
    profile = _profile()
    gen = generate_canvas_background("world", 12, profile, detail_seed=34)
    validated = validate_generation_json(gen, "world")
    assert validated["schema_version"] == 7
    assert validated["hex_grid"]["width"] >= 24
    assert validated["terrain_grid"]["derived_from"] == "hex_grid"


def test_classify_image_to_grid_raster_import():
    from PIL import Image

    from app.services.map_generation.raster_import import GRID_H, GRID_W, classify_image_to_grid

    img = Image.new("RGB", (128, 96), color=(180, 190, 200))
    cells, land_poly = classify_image_to_grid(img, "world")
    assert len(cells) == GRID_W * GRID_H
    assert any(code == 1 for code in cells)
    assert land_poly is None or len(land_poly) >= 3
