"""Deterministic, rules-aware world generator for GM campaigns.

This package turns a `CampaignWorldConfig.settings_json` blob into a
populated world (regions, cities, shops, items, inventory, markets,
simulation state) atomically under a single handler
transaction. The public entry point is `generator.generate`.

See `.cursor/plans/gm_world_generation_flow_72393a80.plan.md`.
"""

from app.services.world_generator import (  # noqa: F401
    defaults,
    validator,
    generator,
    naming_logic,
    stat_factory,
    pricing,
    wiper,
)
from app.services.world_generator.validator import ValidationError  # noqa: F401
from app.services.world_generator.generator import (  # noqa: F401
    GenerationTimeoutError,
    generate,
    generate_cities_for_empty_region,
    generate_shops_onward,
)
