"""Procedural Voronoi cell-graph map generation (presentation layer only).

Never imported by SimulationEngine.run_tick or economy modules.
"""

from app.services.map_generation.pipeline import (
    generate_map,
    migrate_v5_to_v6,
    partial_regen,
    site_count_for_scope,
)

__all__ = [
    "generate_map",
    "migrate_v5_to_v6",
    "partial_regen",
    "site_count_for_scope",
]
