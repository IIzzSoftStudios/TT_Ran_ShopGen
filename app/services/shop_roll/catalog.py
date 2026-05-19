"""Load and query ``data/shop_roll_catalog.yaml``."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

import yaml

_CATALOG_PATH = Path(__file__).resolve().parents[3] / "data" / "shop_roll_catalog.yaml"


@dataclass(frozen=True)
class ShopRollCatalog:
    raw: Mapping[str, Any]

    @property
    def city_sizes(self) -> List[str]:
        return list(self.raw["city_sizes"])

    @property
    def variation_tier_steps(self) -> Dict[int, int]:
        return {int(k): int(v) for k, v in self.raw["variation_tier_steps"].items()}

    @property
    def population_bands(self) -> Dict[str, List[int]]:
        return dict(self.raw["population_bands"])

    @property
    def shops_per_size(self) -> Dict[str, List[int]]:
        return dict(self.raw["shops_per_size"])

    @property
    def daily_demand_units(self) -> Dict[str, float]:
        return {k: float(v) for k, v in self.raw["daily_demand_units"].items()}

    @property
    def restock_units(self) -> Dict[str, int]:
        return {k: int(v) for k, v in self.raw["restock_units"].items()}

    @property
    def stock_cap(self) -> Dict[str, int]:
        return {k: int(v) for k, v in self.raw["stock_cap"].items()}

    @property
    def price_elasticity(self) -> float:
        return float(self.raw.get("price_elasticity", 1.0))

    @property
    def price_elasticity_by_category(self) -> Dict[str, float]:
        return dict(self.raw.get("price_elasticity_by_category", {}))

    @property
    def price_ratio_floor(self) -> float:
        return float(self.raw.get("price_ratio_floor", 0.2))

    @property
    def demand_multiplier_min(self) -> float:
        return float(self.raw.get("demand_multiplier_min", 0.01))

    @property
    def demand_multiplier_max(self) -> float:
        return float(self.raw.get("demand_multiplier_max", 5.0))

    @property
    def daily_variance(self) -> Tuple[float, float]:
        pair = self.raw.get("daily_variance", [0.85, 1.15])
        return float(pair[0]), float(pair[1])

    @property
    def restock_variance(self) -> Tuple[float, float]:
        pair = self.raw.get("restock_variance", [0.9, 1.1])
        return float(pair[0]), float(pair[1])

    @property
    def restock_interval_days(self) -> Tuple[int, int]:
        pair = self.raw.get("restock_interval_days", [15, 30])
        return int(pair[0]), int(pair[1])

    @property
    def slot_ranges(self) -> Dict[str, List[int]]:
        return dict(self.raw["slot_ranges"])

    @property
    def item_pools(self) -> Dict[str, List[str]]:
        return dict(self.raw["item_pools"])

    @property
    def base_prices_copper(self) -> Dict[str, int]:
        return {k: int(v) for k, v in self.raw["base_prices_copper"].items()}

    def max_shops_per_city(self) -> int:
        return max(int(bounds[1]) for bounds in self.shops_per_size.values())

    def shops_count_range(self, city_size: str) -> Tuple[int, int]:
        lo, hi = self.shops_per_size.get(city_size, [1, 3])
        return int(lo), int(hi)

    def slot_count_range(self, city_size: str) -> Tuple[int, int]:
        lo, hi = self.slot_ranges.get(city_size, [3, 8])
        return int(lo), int(hi)

    def elasticity_for_shop_type(self, shop_type: str, category_map: Mapping[str, str]) -> float:
        category = category_map.get(shop_type, "general")
        return float(
            self.price_elasticity_by_category.get(
                category,
                self.price_elasticity,
            )
        )


def load_catalog(path: Optional[Path] = None) -> ShopRollCatalog:
    catalog_path = path or _CATALOG_PATH
    with catalog_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid catalog at {catalog_path}")
    return ShopRollCatalog(raw=data)


@lru_cache(maxsize=1)
def get_catalog() -> ShopRollCatalog:
    return load_catalog()
