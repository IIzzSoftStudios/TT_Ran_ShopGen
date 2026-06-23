"""Hex grid world generation tests."""

from __future__ import annotations

import pytest

from app.services.gm_maps import decode_terrain_rle, encode_terrain_rle, map_generation_profile
from app.services.map_generation import hex_grid as hg
from app.services.map_generation.hex_bake import bake_terrain_grid
from app.services.map_generation.hex_generate import generate_city_hex_grid, generate_world_hex_grid


def test_hex_generation_respects_land_frequency():
    profile = map_generation_profile(None, overrides={"land_frequency": 80, "cluster_percent": 80})
    grid = generate_world_hex_grid(
        profile, 42, 99, encode_rle=encode_terrain_rle, decode_rle=decode_terrain_rle
    )
    cells = decode_terrain_rle(grid["cells"], int(grid["width"]) * int(grid["height"]))
    land = sum(1 for c in cells if hg.land_code(c))
    total = len(cells)
    assert land / total >= 0.5


def test_hex_generation_includes_grassland_and_hills():
    profile = map_generation_profile(
        None,
        overrides={
            "land_frequency": 80,
            "grassland_frequency": 60,
            "hills_frequency": 40,
            "vegetation_frequency": 40,
            "cluster_percent": 80,
        },
    )
    grid = generate_world_hex_grid(
        profile, 42, 99, encode_rle=encode_terrain_rle, decode_rle=decode_terrain_rle
    )
    cells = decode_terrain_rle(grid["cells"], int(grid["width"]) * int(grid["height"]))
    grassland = sum(1 for c in cells if c == 5)
    hills = sum(1 for c in cells if c == 6)
    assert grassland > 0
    assert hills > 0


def test_bake_produces_gapless_terrain():
    profile = map_generation_profile(None)
    hex_g = generate_world_hex_grid(
        profile, 1, 2, encode_rle=encode_terrain_rle, decode_rle=decode_terrain_rle
    )
    baked = bake_terrain_grid(hex_g, 256, 192, encode_terrain_rle, decode_terrain_rle)
    raster = decode_terrain_rle(baked["cells"], 256 * 192)
    assert len(raster) == 256 * 192
    assert baked["derived_from"] == "hex_grid"


def test_city_hex_generation_has_walled_interior():
    profile = map_generation_profile(
        None,
        overrides={"hex_width": 80, "hex_height": 60, "city_complexity": 8},
    )
    grid = generate_city_hex_grid(
        profile, 7, 8, encode_rle=encode_terrain_rle, decode_rle=decode_terrain_rle
    )
    cells = decode_terrain_rle(grid["cells"], int(grid["width"]) * int(grid["height"]))
    inside = sum(1 for c in cells if c >= 1)
    buildings = sum(1 for c in cells if c == 5)
    roads = sum(1 for c in cells if c == 4)
    walls = sum(1 for c in cells if c == 6)
    assert inside > 100
    assert buildings > 50
    assert roads > 10
    assert walls > 5
    assert grid.get("city_wall_polygon")
