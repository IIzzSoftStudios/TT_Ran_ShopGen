"""Pure-Python validator for GM world-gen form submissions.

Produces a normalized `settings_json` dict stamped with `schema_version: 1`,
or raises `ValidationError(field, message)` on the first problem.

The handler is expected to catch `ValidationError` and re-render the form
with the flagged field + flash message.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional

from app.services.world_generator.defaults import (
    RANGE_SETTINGS,
    RESOURCE_NODE_CAP,
    SCHEMA_VERSION,
    SEED_MAX,
    SEED_MIN,
    SHOP_INVENTORY_CAP,
    SYSTEM_TYPES,
    TOTAL_ENTITY_CAP,
)


class ValidationError(Exception):
    """Raised with (field, message) for UI-friendly feedback."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field
        self.message = message


# -----------------------------------------------------------------------------
# Range parsing
# -----------------------------------------------------------------------------
def _coerce_int(raw: Any, field: str) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValidationError(field, "must be an integer")


def _parse_range(
    form: Mapping[str, Any], key: str, floor: int, ceiling: int
) -> Dict[str, int]:
    """Accept either `<key>_min`/`<key>_max` form fields, a `<key>` dict,
    or a single scalar (treated as both min and max)."""
    if isinstance(form.get(key), dict):
        raw = form[key]
        lo = _coerce_int(raw.get("min"), f"{key}.min")
        hi = _coerce_int(raw.get("max"), f"{key}.max")
    elif f"{key}_min" in form or f"{key}_max" in form:
        lo = _coerce_int(form.get(f"{key}_min"), f"{key}_min")
        hi = _coerce_int(form.get(f"{key}_max"), f"{key}_max")
    elif key in form:
        val = _coerce_int(form.get(key), key)
        lo = hi = val
    else:
        raise ValidationError(key, "is required")

    if lo < floor or lo > ceiling:
        raise ValidationError(
            f"{key}.min", f"must be between {floor} and {ceiling} (got {lo})"
        )
    if hi < floor or hi > ceiling:
        raise ValidationError(
            f"{key}.max", f"must be between {floor} and {ceiling} (got {hi})"
        )
    if lo > hi:
        raise ValidationError(
            key, f"minimum ({lo}) must be <= maximum ({hi})"
        )
    return {"min": lo, "max": hi}


def _parse_enum(form: Mapping[str, Any], key: str, choices: Iterable[str]) -> str:
    raw = form.get(key)
    if raw is None:
        raise ValidationError(key, "is required")
    val = str(raw).strip()
    if val not in choices:
        raise ValidationError(
            key, f"must be one of {', '.join(choices)} (got '{val}')"
        )
    return val


def _parse_seed(form: Mapping[str, Any]) -> Optional[int]:
    raw = form.get("world_seed")
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = raw.strip()
        if raw == "":
            return None
    try:
        seed = int(raw)
    except (TypeError, ValueError):
        raise ValidationError(
            "world_seed",
            f"must be an integer between {SEED_MIN} and {SEED_MAX}",
        )
    if seed < SEED_MIN or seed > SEED_MAX:
        raise ValidationError(
            "world_seed",
            f"must be between {SEED_MIN} and {SEED_MAX} (got {seed})",
        )
    return seed


def _parse_name(form: Mapping[str, Any]) -> str:
    raw = form.get("campaign_name") or form.get("name") or ""
    name = str(raw).strip()
    if not name:
        raise ValidationError("campaign_name", "is required")
    if len(name) > 120:
        raise ValidationError("campaign_name", "must be 120 characters or fewer")
    return name


# -----------------------------------------------------------------------------
# Composite caps
# -----------------------------------------------------------------------------
def _enforce_caps(ranges: Dict[str, Dict[str, int]]) -> None:
    """Check ShopInventory cap, total entity cap, resource node cap, and
    item-pool density rule."""
    cities_max = ranges["num_cities"]["max"]
    shops_max = ranges["shops_per_city"]["max"]
    items_per_shop_max = ranges["items_per_shop"]["max"]
    pool_min = ranges["global_item_pool_size"]["min"]
    pool_max = ranges["global_item_pool_size"]["max"]
    regions_max = ranges["num_regions"]["max"]
    nodes_max = ranges["resource_nodes_per_city"]["max"]
    axis_min = ranges["tech_magic_balance"]["min"]
    axis_max = ranges["tech_magic_balance"]["max"]

    inv_worst = cities_max * shops_max * items_per_shop_max
    if inv_worst > SHOP_INVENTORY_CAP:
        raise ValidationError(
            "composite_cap",
            (
                f"Your maximum world size (cities x shops x items per shop "
                f"= {inv_worst}) would exceed {SHOP_INVENTORY_CAP} "
                "ShopInventory rows. Reduce cities, shops per city, or items "
                "per shop."
            ),
        )

    # Regions + cities + shops + inventory + items + nodes + markets + misc
    # Rough worst-case upper bound for the "total entity" ceiling.
    total_worst = (
        regions_max
        + cities_max
        + (cities_max * shops_max)
        + pool_max
        + (cities_max * nodes_max)
        + inv_worst
        + 13  # campaign, config, sim_state, audit headroom
    )
    if total_worst > TOTAL_ENTITY_CAP:
        raise ValidationError(
            "composite_cap",
            (
                f"Your maximum world size would create ~{total_worst} total "
                f"entities (ceiling {TOTAL_ENTITY_CAP}). Reduce one of: "
                "cities, shops per city, items per shop, or items pool."
            ),
        )

    if cities_max * nodes_max > RESOURCE_NODE_CAP:
        raise ValidationError(
            "resource_nodes_per_city",
            (
                f"cities.max x resource_nodes_per_city.max = "
                f"{cities_max * nodes_max} exceeds cap {RESOURCE_NODE_CAP}"
            ),
        )

    axis_span = axis_max - axis_min + 1
    required_pool_min = axis_span * 3
    if pool_min < required_pool_min:
        raise ValidationError(
            "global_item_pool_size",
            (
                f"Minimum item pool ({pool_min}) is too small for the chosen "
                f"axis span ({axis_span}). Need at least "
                f"{required_pool_min} so every axis position has enough "
                "items to stock shops. Raise the minimum item pool or narrow "
                "Magic <-> Tech Balance."
            ),
        )


# -----------------------------------------------------------------------------
# Public entry point
# -----------------------------------------------------------------------------
def validate(form: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a normalized settings dict ready for persistence.

    Shape:
        {
            "schema_version": 1,
            "campaign_name": str,
            "system_type": str,
            "world_seed": int | None,
            "ranges": {
                "num_cities":             {"min": int, "max": int},
                ...
                "tech_magic_balance":     {"min": int, "max": int},
            },
        }
    """
    campaign_name = _parse_name(form)
    system_type = _parse_enum(form, "system_type", SYSTEM_TYPES)

    ranges: Dict[str, Dict[str, int]] = {}
    for key, (floor, ceiling, _default_min, _default_max) in RANGE_SETTINGS.items():
        ranges[key] = _parse_range(form, key, floor, ceiling)

    _enforce_caps(ranges)

    world_seed = _parse_seed(form)

    return {
        "schema_version": SCHEMA_VERSION,
        "campaign_name": campaign_name,
        "system_type": system_type,
        "world_seed": world_seed,
        "ranges": ranges,
    }
