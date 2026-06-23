"""Assemble schema v7 world generation from hex_grid."""

from __future__ import annotations

from typing import Any, Callable

from app.services.map_generation.hex_bake import bake_terrain_grid, bake_dimensions
from app.services.map_generation.hex_features import (
    derive_city_features_from_hex_grid,
    derive_features_from_hex_grid,
    derive_shop_features_from_hex_grid,
)

TERRAIN_GRID_WIDTH = 256
TERRAIN_GRID_HEIGHT = 192


def build_generation_from_hex_grid(
    hex_grid: dict,
    layout_seed: int,
    detail_seed: int,
    profile: dict,
    style_preset: str,
    render_palette: dict,
    encode_rle: Callable[[list[int]], str],
    decode_rle: Callable[[str, int], list[int]],
    *,
    scope: str = "world",
) -> dict:
    terrain_grid = bake_terrain_grid(
        hex_grid,
        *bake_dimensions(hex_grid),
        encode_rle,
        decode_rle,
        city_scope=(scope in ("city", "shop")),
    )
    if scope == "city":
        features = derive_city_features_from_hex_grid(hex_grid, profile, decode_rle)
    elif scope == "shop":
        features = derive_shop_features_from_hex_grid(hex_grid, profile, decode_rle)
    else:
        features = derive_features_from_hex_grid(hex_grid, profile, decode_rle)
    return {
        "schema_version": 7,
        "seed": layout_seed,
        "layout_seed": layout_seed,
        "detail_seed": detail_seed,
        "scope": scope,
        "style_preset": style_preset,
        "palette": style_preset,
        "render_palette": render_palette,
        "profile": profile,
        "hex_grid": hex_grid,
        "features": features,
        "terrain_grid": terrain_grid,
    }
