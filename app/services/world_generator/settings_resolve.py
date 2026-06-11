"""Resolve world-gen settings with backward compatibility."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Tuple

from app.services.shop_roll.catalog import ShopRollCatalog, get_catalog


def city_size_variation_range(settings: Mapping[str, Any]) -> Dict[str, int]:
    ranges = settings.get("ranges") or {}
    if "city_size_variation" in ranges:
        return dict(ranges["city_size_variation"])
    return {"min": 3, "max": 8}


def population_scale_range(settings: Mapping[str, Any]) -> Dict[str, int]:
    ranges = settings.get("ranges") or {}
    if "population_scale" in ranges:
        return dict(ranges["population_scale"])
    return {"min": 8, "max": 12}


def shops_per_city_range(
    settings: Mapping[str, Any],
    catalog: ShopRollCatalog | None = None,
) -> Dict[str, int]:
    ranges = settings.get("ranges") or {}
    if "shops_per_city" in ranges:
        return dict(ranges["shops_per_city"])
    catalog = catalog or get_catalog()
    mx = catalog.max_shops_per_city()
    return {"min": 1, "max": mx}


def inventory_mode(settings: Mapping[str, Any]) -> str:
    """Always procedural random items (names, stats, rarity) from the axis pool."""
    return "axis"


def supply_demand_enabled(settings: Mapping[str, Any]) -> bool:
    """Parse ``supply_demand_enabled`` from world config (defaults to on)."""
    if "supply_demand_enabled" not in settings:
        return True
    raw = settings.get("supply_demand_enabled")
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(raw, (int, float)):
        return raw != 0
    return bool(raw)


def shops_count_for_city(
    city_size: str,
    rng,
    settings: Mapping[str, Any],
    catalog: ShopRollCatalog | None = None,
) -> int:
    """Shop count for a city: catalog tiers when using variation, else legacy range."""
    ranges = settings.get("ranges") or {}
    catalog = catalog or get_catalog()
    if "city_size_variation" in ranges:
        lo, hi = catalog.shops_count_range(city_size)
        if hi <= 0:
            return 0
        return rng.randint(max(0, lo), max(lo, hi))
    spr = shops_per_city_range(settings, catalog)
    return rng.randint(spr["min"], spr["max"])
