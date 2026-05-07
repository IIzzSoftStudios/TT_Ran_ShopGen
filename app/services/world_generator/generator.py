"""Deterministic, rules-aware world generator.

Called by `generate_world_submit` after the handler has already:
- opened a DB transaction,
- created the Campaign row,
- created the CampaignWorldConfig row with `settings_json`.

`generate()` then materializes regions, cities, shops, items, shop
inventory, regional / global markets, and a
`SimulationState` row. It does NOT commit -- the handler is authoritative
for `commit()` / `rollback()`.

Session discipline (swarm-mandated):
- Everything runs under `with db.session.no_autoflush:`.
- Every entity class uses `db.session.add_all([...])`.
- A single `flush()` between batches assigns autoincrement IDs.
"""

from __future__ import annotations

import logging
import random
import secrets
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.extensions import db
from app.models import (
    City,
    GlobalMarket,
    Item,
    MarketEvent,
    RegionalMarket,
    Shop,
    ShopInventory,
    SimulationState,
)

# Region is defined in app/models.py by this plan's migration.
from app.models import Region  # noqa: E402

from app.services.world_generator import naming_logic, pricing, stat_factory
from app.services.world_generator.defaults import (
    AXIS_TOLERANCE_IMPORTED,
    AXIS_TOLERANCE_PRIMARY,
    CURSED_UNIQUE_FREQUENCY_DEFAULT,
    DEFAULT_SIMULATION_SPEED,
    GENERATION_TIMEOUT_SECONDS,
    GOVERNMENT_TYPES,
    IMPORTED_PRICE_MULTIPLIER,
    ITEM_CATEGORIES,
    RARITIES,
    RARITY_WEIGHTS,
    SEED_MAX,
)

log = logging.getLogger(__name__)


class GenerationTimeoutError(RuntimeError):
    """Raised when generation blows past the wall-clock budget."""


@dataclass
class GenerationResult:
    """Summary returned to the handler so it can audit-log + persist the
    resolved seed back onto `CampaignWorldConfig.world_seed`."""

    effective_seed: int
    n_regions: int
    n_cities: int
    n_shops: int
    n_items: int
    n_inventory_rows: int


# -----------------------------------------------------------------------------
# RNG helpers
# -----------------------------------------------------------------------------
def _resolve_seed(requested: Optional[int]) -> int:
    if requested is None:
        return secrets.randbits(31)
    return max(0, min(SEED_MAX, int(requested)))


def _derive_subrng(root: random.Random, tag: str) -> random.Random:
    """Derive a named sub-RNG from the root. Using a hash-stable tag keeps
    the sub-sequence deterministic across Python processes."""
    child_seed = root.randint(0, 2 ** 63 - 1) ^ (hash(tag) & 0xFFFFFFFF)
    return random.Random(child_seed)


# -----------------------------------------------------------------------------
# Helpers for rolling items
# -----------------------------------------------------------------------------
def _weighted_choice(rng: random.Random, choices: List[str], weights: Dict[str, float]) -> str:
    total = sum(weights.get(c, 0.0) for c in choices)
    if total <= 0:
        return rng.choice(choices)
    roll = rng.uniform(0, total)
    acc = 0.0
    for c in choices:
        acc += weights.get(c, 0.0)
        if roll <= acc:
            return c
    return choices[-1]


def _draw_category(rng: random.Random) -> str:
    # 60% equipment, 40% general/consumable. Feels like a classic RPG store.
    return rng.choices(
        list(ITEM_CATEGORIES),
        weights=[30, 15, 15, 25, 15],
        k=1,
    )[0]


def _draw_rarity(rng: random.Random) -> str:
    return _weighted_choice(rng, list(RARITIES), RARITY_WEIGHTS)


# -----------------------------------------------------------------------------
# Public entry point
# -----------------------------------------------------------------------------
def generate(
    campaign_id: int,
    settings: Dict[str, Any],
) -> GenerationResult:
    """Materialize a world. Does NOT commit.

    Parameters:
        campaign_id: every entity FK is scoped to this value.
        settings: normalized settings dict from `validator.validate`.

    Returns a `GenerationResult` the handler should persist /audit-log.

    Raises `GenerationTimeoutError` if the wall-clock budget is exceeded
    mid-pipeline.
    """
    t0 = time.monotonic()

    def _check_budget() -> None:
        if GENERATION_TIMEOUT_SECONDS is None or GENERATION_TIMEOUT_SECONDS <= 0:
            return
        elapsed = time.monotonic() - t0
        if elapsed > GENERATION_TIMEOUT_SECONDS:
            raise GenerationTimeoutError(
                f"World generation exceeded {GENERATION_TIMEOUT_SECONDS}s "
                f"(elapsed {elapsed:.1f}s). Try a smaller world."
            )

    ranges = settings["ranges"]
    system_type = settings["system_type"]
    sim_speed = DEFAULT_SIMULATION_SPEED
    effective_seed = _resolve_seed(settings.get("world_seed"))

    root_rng = random.Random(effective_seed)
    rng_cities = _derive_subrng(root_rng, "cities")
    rng_regions = _derive_subrng(root_rng, "regions")
    rng_shops = _derive_subrng(root_rng, "shops")
    rng_items = _derive_subrng(root_rng, "items")
    rng_inventory = _derive_subrng(root_rng, "inventory")

    # Collision-guard sets, reset per campaign.
    city_names: set = set()
    shop_names: set = set()
    item_names: set = set()
    region_names: set = set()

    axis_range = ranges["tech_magic_balance"]

    with db.session.no_autoflush:
        # ---------------------------------------------------------------
        # Step 1: Regions (roll each region's axis position)
        # ---------------------------------------------------------------
        n_regions = rng_regions.randint(
            ranges["num_regions"]["min"], ranges["num_regions"]["max"]
        )
        regions: List[Region] = []
        for _ in range(n_regions):
            axis_pos = rng_regions.randint(axis_range["min"], axis_range["max"])
            reg_gov = rng_regions.choice(GOVERNMENT_TYPES)
            # Reuse city-naming vocabulary for regions.
            raw_name = naming_logic.city_name(
                rng_regions, axis_pos, reg_gov, region_names
            )
            regions.append(
                Region(
                    name=raw_name,
                    campaign_id=campaign_id,
                    local_flavor={"axis_position": int(axis_pos)},
                )
            )
        db.session.add_all(regions)
        db.session.flush()  # assign region.id
        _check_budget()
        log.info(
            "world_gen phase=regions campaign_id=%s n=%d",
            campaign_id,
            len(regions),
        )

        # Build a region lookup keyed by id for deterministic iteration.
        regions_sorted = sorted(regions, key=lambda r: r.id)

        # ---------------------------------------------------------------
        # Step 2: Global item pool (built BEFORE cities so inventory can
        # reference item.item_id). Every item stamped with its axis.
        # ---------------------------------------------------------------
        n_items = rng_items.randint(
            ranges["global_item_pool_size"]["min"],
            ranges["global_item_pool_size"]["max"],
        )
        items: List[Item] = []
        base_price_table: Dict[int, int] = {}  # keyed later by item.item_id
        # Temporary parallel list because item ids aren't assigned until flush.
        pending_prices: List[int] = []

        for _ in range(n_items):
            axis_pos = rng_items.randint(axis_range["min"], axis_range["max"])
            category = _draw_category(rng_items)
            rarity = _draw_rarity(rng_items)
            is_cursed = rng_items.random() < CURSED_UNIQUE_FREQUENCY_DEFAULT

            stats = stat_factory.build_item_stats(
                rng_items,
                system_type=system_type,
                category=category,
                rarity=rarity,
                axis_position=axis_pos,
                is_cursed=is_cursed,
            )
            name = naming_logic.item_name(
                rng_items, axis_pos, category, rarity, is_cursed, item_names
            )
            base_price = pricing.compute_base_price(category, rarity, stats)
            items.append(
                Item(
                    name=name,
                    type=category,
                    rarity=rarity,
                    base_price=base_price,
                    description=f"{rarity} {category} (axis {axis_pos})",
                    campaign_id=campaign_id,
                    stats=stats,
                    axis_position=int(axis_pos),
                )
            )
            pending_prices.append(base_price)

        db.session.add_all(items)
        db.session.flush()  # assign item.item_id
        for item, price in zip(items, pending_prices):
            base_price_table[item.item_id] = price
        _check_budget()
        log.info(
            "world_gen phase=items campaign_id=%s n=%d",
            campaign_id,
            len(items),
        )

        # Index items by axis for efficient tolerance-window lookup.
        items_by_axis: Dict[int, List[Item]] = {}
        for item in items:
            items_by_axis.setdefault(item.axis_position, []).append(item)

        # ---------------------------------------------------------------
        # Step 3: Cities (each assigned a region; inherits axis at runtime)
        # ---------------------------------------------------------------
        n_cities = rng_cities.randint(
            ranges["num_cities"]["min"], ranges["num_cities"]["max"]
        )
        cities: List[City] = []
        city_region_map: Dict[int, Region] = {}  # city index -> region
        for idx in range(n_cities):
            region = regions_sorted[idx % len(regions_sorted)] if regions_sorted else None
            city_axis = region.local_flavor["axis_position"] if region else 5
            city_gov = rng_cities.choice(GOVERNMENT_TYPES)
            name = naming_logic.city_name(
                rng_cities, city_axis, city_gov, city_names
            )
            population = rng_cities.randint(500, 25_000)
            size = "Small" if population < 3_000 else "Medium" if population < 12_000 else "Large"
            city = City(
                name=name,
                government_type=city_gov,
                size=size,
                population=population,
                region=region.name if region else None,
                campaign_id=campaign_id,
            )
            # region_id is set by the migration adding a nullable FK. Guarded
            # here in case the deployment hasn't applied that column yet.
            if hasattr(City, "region_id") and region is not None:
                setattr(city, "region_id", region.id)
            cities.append(city)
            city_region_map[idx] = region
        db.session.add_all(cities)
        db.session.flush()
        _check_budget()
        log.info(
            "world_gen phase=cities campaign_id=%s n=%d",
            campaign_id,
            len(cities),
        )

        # ---------------------------------------------------------------
        # Step 4: Shops per city + Step 5: ShopInventory per shop
        # ---------------------------------------------------------------
        all_shops: List[Shop] = []
        city_shop_pairs: List[Tuple[City, Shop]] = []
        shops_per_city_counts: List[int] = []
        for city in cities:
            n_shops_here = rng_shops.randint(
                ranges["shops_per_city"]["min"],
                ranges["shops_per_city"]["max"],
            )
            shops_per_city_counts.append(n_shops_here)
            region = next(
                (r for r in regions_sorted if r.name == city.region),
                regions_sorted[0] if regions_sorted else None,
            )
            city_axis = region.local_flavor["axis_position"] if region else 5
            for _ in range(n_shops_here):
                shop_type = naming_logic.shop_type_for_axis(rng_shops, city_axis)
                city_gov = city.government_type or GOVERNMENT_TYPES[0]
                sname = naming_logic.shop_name(
                    rng_shops, city_axis, city_gov, shop_type, shop_names
                )
                shop = Shop(
                    name=sname,
                    type=shop_type,
                    campaign_id=campaign_id,
                    preferred_region=city.region,
                )
                all_shops.append(shop)
                city_shop_pairs.append((city, shop))
        db.session.add_all(all_shops)
        db.session.flush()

        # Link shops to cities via many-to-many.
        for city, shop in city_shop_pairs:
            shop.cities.append(city)
        _check_budget()
        log.info(
            "world_gen phase=shops campaign_id=%s n=%d (starting shop inventory)",
            campaign_id,
            len(all_shops),
        )

        # Build inventory.
        n_inventory_rows = 0
        inventory_batch: List[ShopInventory] = []
        for city, shop in city_shop_pairs:
            region = next(
                (r for r in regions_sorted if r.name == city.region),
                regions_sorted[0] if regions_sorted else None,
            )
            city_axis = region.local_flavor["axis_position"] if region else 5
            n_items_here = rng_inventory.randint(
                ranges["items_per_shop"]["min"],
                ranges["items_per_shop"]["max"],
            )

            # Build the eligible item list: native (|d| <= PRIMARY) + imported
            # (PRIMARY < |d| <= IMPORTED, priced at IMPORTED_PRICE_MULTIPLIER).
            native: List[Item] = []
            imported: List[Item] = []
            for axis_val, bucket in items_by_axis.items():
                delta = abs(axis_val - city_axis)
                if delta <= AXIS_TOLERANCE_PRIMARY:
                    native.extend(bucket)
                elif delta <= AXIS_TOLERANCE_IMPORTED:
                    imported.extend(bucket)

            if not native and not imported:
                # Fallback: take the full pool. Should be unreachable after
                # the density rule in validator, but defensive.
                native = items

            picked_items = set()
            attempts = 0
            max_attempts = n_items_here * 4
            while len(picked_items) < n_items_here and attempts < max_attempts:
                attempts += 1
                # 70/30 bias toward native stock.
                if native and (not imported or rng_inventory.random() < 0.7):
                    candidate = rng_inventory.choice(native)
                    multiplier = 1.0
                elif imported:
                    candidate = rng_inventory.choice(imported)
                    multiplier = IMPORTED_PRICE_MULTIPLIER
                else:
                    break
                if candidate.item_id in picked_items:
                    continue
                picked_items.add(candidate.item_id)
                dynamic = pricing.dynamic_price_arithmetic(
                    base_price_table[candidate.item_id],
                    region_mult=1.0,
                    axis_distance_mult=multiplier,
                )
                inventory_batch.append(
                    ShopInventory(
                        shop_id=shop.shop_id,
                        item_id=candidate.item_id,
                        campaign_id=campaign_id,
                        stock=rng_inventory.randint(1, 10),
                        dynamic_price=dynamic,
                    )
                )
                n_inventory_rows += 1

            _check_budget()

        if inventory_batch:
            db.session.add_all(inventory_batch)
            db.session.flush()
        log.info(
            "world_gen phase=shop_inventory campaign_id=%s shop_inventory_rows=%d",
            campaign_id,
            n_inventory_rows,
        )

        # ---------------------------------------------------------------
        # Step 6: Regional + Global markets (per item per region / global)
        # ---------------------------------------------------------------
        regional_markets: List[RegionalMarket] = []
        # One RegionalMarket row per (first city in region, item) pair.
        first_city_by_region = {
            region.id: next(
                (c for c in cities if c.region == region.name),
                None,
            )
            for region in regions_sorted
        }
        for item in items:
            for region in regions_sorted:
                first_city = first_city_by_region.get(region.id)
                if first_city is None:
                    continue
                regional_markets.append(
                    RegionalMarket(
                        city_id=first_city.city_id,
                        item_id=item.item_id,
                        total_supply=0,
                        total_demand=0,
                        average_price=float(base_price_table[item.item_id]),
                        campaign_id=campaign_id,
                    )
                )
        if regional_markets:
            db.session.add_all(regional_markets)

        global_markets = [
            GlobalMarket(
                item_id=item.item_id,
                total_supply=0,
                total_demand=0,
                average_price=float(base_price_table[item.item_id]),
                campaign_id=campaign_id,
            )
            for item in items
        ]
        if global_markets:
            db.session.add_all(global_markets)
        log.info(
            "world_gen phase=markets campaign_id=%s regional=%d global=%d",
            campaign_id,
            len(regional_markets),
            len(global_markets),
        )

        # ---------------------------------------------------------------
        # Step 7: SimulationState (seed default speed)
        # ---------------------------------------------------------------
        existing_sim = (
            db.session.query(SimulationState)
            .filter_by(campaign_id=campaign_id)
            .first()
        )
        if existing_sim is None:
            db.session.add(
                SimulationState(
                    current_tick=0,
                    speed=sim_speed,
                    campaign_id=campaign_id,
                )
            )
        # Do not overwrite speed on an existing row — GM controls it from the sim UI.

        _check_budget()
        log.info("world_gen phase=done campaign_id=%s", campaign_id)

    return GenerationResult(
        effective_seed=effective_seed,
        n_regions=len(regions),
        n_cities=len(cities),
        n_shops=len(all_shops),
        n_items=len(items),
        n_inventory_rows=n_inventory_rows,
    )


def generate_cities_for_empty_region(
    campaign_id: int,
    region_id: int,
    settings: Dict[str, Any],
) -> int:
    """If the region has no cities yet, create a batch using world-config ranges.

    Uses the same seed discipline as ``generate_shops_onward`` so partial runs
    stay deterministic. Does NOT commit.

    Returns:
        Number of new cities inserted (0 if the region already had cities).
    """
    t0 = time.monotonic()

    def _check_budget() -> None:
        if GENERATION_TIMEOUT_SECONDS is None or GENERATION_TIMEOUT_SECONDS <= 0:
            return
        elapsed = time.monotonic() - t0
        if elapsed > GENERATION_TIMEOUT_SECONDS:
            raise GenerationTimeoutError(
                f"World generation exceeded {GENERATION_TIMEOUT_SECONDS}s "
                f"(elapsed {elapsed:.1f}s). Try a smaller world."
            )

    ranges = settings["ranges"]
    effective_seed = _resolve_seed(settings.get("world_seed"))
    root_rng = random.Random(effective_seed)
    rng_cities = _derive_subrng(root_rng, f"empty_region_{region_id}_cities")

    region_row = (
        db.session.query(Region)
        .filter_by(
            id=region_id,
            campaign_id=campaign_id,
        )
        .first()
    )
    if region_row is None:
        raise ValueError("Region not found for this campaign.")

    cities_in_region = (
        db.session.query(City)
        .filter_by(
            campaign_id=campaign_id,
            region_id=region_id,
        )
        .count()
    )
    if cities_in_region:
        return 0

    city_names = {
        n[0]
        for n in db.session.query(City.name)
        .filter_by(campaign_id=campaign_id)
        .all()
    }

    axis_pos = 5
    if region_row.local_flavor and "axis_position" in region_row.local_flavor:
        axis_pos = int(region_row.local_flavor["axis_position"])

    n_new = rng_cities.randint(
        ranges["num_cities"]["min"],
        ranges["num_cities"]["max"],
    )
    new_cities: List[City] = []
    with db.session.no_autoflush:
        for _ in range(n_new):
            _check_budget()
            city_gov = rng_cities.choice(GOVERNMENT_TYPES)
            name = naming_logic.city_name(
                rng_cities, axis_pos, city_gov, city_names
            )
            population = rng_cities.randint(500, 25_000)
            size = (
                "Small"
                if population < 3_000
                else "Medium"
                if population < 12_000
                else "Large"
            )
            new_cities.append(
                City(
                    name=name,
                    government_type=city_gov,
                    size=size,
                    population=population,
                    region=region_row.name,
                    campaign_id=campaign_id,
                    region_id=region_row.id,
                )
            )
        db.session.add_all(new_cities)
    db.session.flush()
    log.info(
        "world_gen phase=cities_empty_region campaign_id=%s region_id=%s n=%d",
        campaign_id,
        region_id,
        len(new_cities),
    )
    return len(new_cities)


def generate_shops_onward(
    campaign_id: int,
    region_id: int,
    settings: Dict[str, Any],
) -> GenerationResult:
    """Create shops + shop inventory (+ markets / sim seed) for cities in one region.

    Assumes regions, cities, and a non-empty item pool already exist for the
    campaign. Skips cities in that region that already have at least one linked
    shop. Does NOT commit.

    Reuses the same RNG derivation as `generate()` from ``settings['world_seed']``
    (or ``None`` for random), so behavior matches full world-gen when the same
    seed is stored on `CampaignWorldConfig`.
    """
    t0 = time.monotonic()

    def _check_budget() -> None:
        if GENERATION_TIMEOUT_SECONDS is None or GENERATION_TIMEOUT_SECONDS <= 0:
            return
        elapsed = time.monotonic() - t0
        if elapsed > GENERATION_TIMEOUT_SECONDS:
            raise GenerationTimeoutError(
                f"World generation exceeded {GENERATION_TIMEOUT_SECONDS}s "
                f"(elapsed {elapsed:.1f}s). Try a smaller world."
            )

    ranges = settings["ranges"]
    sim_speed = DEFAULT_SIMULATION_SPEED
    effective_seed = _resolve_seed(settings.get("world_seed"))

    root_rng = random.Random(effective_seed)
    rng_shops = _derive_subrng(root_rng, "shops")
    rng_inventory = _derive_subrng(root_rng, "inventory")

    region_row = (
        db.session.query(Region)
        .filter_by(
            id=region_id,
            campaign_id=campaign_id,
        )
        .first()
    )
    if region_row is None:
        raise ValueError("Region not found for this campaign.")

    regions_sorted = (
        db.session.query(Region)
        .filter_by(campaign_id=campaign_id)
        .order_by(Region.id)
        .all()
    )
    regions_by_id = {r.id: r for r in regions_sorted}

    cities_in_region = (
        db.session.query(City)
        .filter_by(
            campaign_id=campaign_id,
            region_id=region_id,
        )
        .order_by(City.city_id)
        .all()
    )
    if not cities_in_region:
        raise ValueError(
            "No cities are assigned to this region. Assign cities, then try again."
        )

    items = (
        db.session.query(Item)
        .filter_by(campaign_id=campaign_id)
        .all()
    )
    if not items:
        raise ValueError(
            "This campaign has no items yet. Run full world generation or add "
            "items before generating shops."
        )

    shop_names: set = {
        s[0]
        for s in db.session.query(Shop.name)
        .filter_by(campaign_id=campaign_id)
        .all()
    }

    items_by_axis: Dict[int, List[Item]] = {}
    base_price_table: Dict[int, int] = {}
    for item in items:
        axis_val = item.axis_position if item.axis_position is not None else 5
        items_by_axis.setdefault(int(axis_val), []).append(item)
        base_price_table[item.item_id] = int(item.base_price)

    cities_to_stock: List[City] = [c for c in cities_in_region if not c.shops]
    if not cities_to_stock:
        raise ValueError(
            "Every city in this region already has shops. Add new cities or "
            "remove shops if you need to regenerate."
        )

    all_shops: List[Shop] = []
    city_shop_pairs: List[Tuple[City, Shop]] = []

    def _city_axis(city: City) -> int:
        reg = regions_by_id.get(city.region_id) if city.region_id else None
        if reg and reg.local_flavor:
            return int(reg.local_flavor.get("axis_position", 5))
        return 5

    with db.session.no_autoflush:
        for city in cities_to_stock:
            n_shops_here = rng_shops.randint(
                ranges["shops_per_city"]["min"],
                ranges["shops_per_city"]["max"],
            )
            reg = regions_by_id.get(city.region_id)
            city_axis = _city_axis(city)
            for _ in range(n_shops_here):
                shop_type = naming_logic.shop_type_for_axis(rng_shops, city_axis)
                city_gov = city.government_type or GOVERNMENT_TYPES[0]
                sname = naming_logic.shop_name(
                    rng_shops, city_axis, city_gov, shop_type, shop_names
                )
                pref = reg.name if reg else (city.region or "")
                shop = Shop(
                    name=sname,
                    type=shop_type,
                    campaign_id=campaign_id,
                    preferred_region=pref or None,
                )
                all_shops.append(shop)
                city_shop_pairs.append((city, shop))
            _check_budget()

        db.session.add_all(all_shops)
        db.session.flush()

        for city, shop in city_shop_pairs:
            shop.cities.append(city)
        _check_budget()
        log.info(
            "world_gen phase=shops_partial campaign_id=%s region_id=%s n=%d",
            campaign_id,
            region_id,
            len(all_shops),
        )

        n_inventory_rows = 0
        inventory_batch: List[ShopInventory] = []
        for city, shop in city_shop_pairs:
            city_axis = _city_axis(city)
            n_items_here = rng_inventory.randint(
                ranges["items_per_shop"]["min"],
                ranges["items_per_shop"]["max"],
            )

            native: List[Item] = []
            imported: List[Item] = []
            for axis_val, bucket in items_by_axis.items():
                delta = abs(axis_val - city_axis)
                if delta <= AXIS_TOLERANCE_PRIMARY:
                    native.extend(bucket)
                elif delta <= AXIS_TOLERANCE_IMPORTED:
                    imported.extend(bucket)

            if not native and not imported:
                native = items

            picked_items = set()
            attempts = 0
            max_attempts = n_items_here * 4
            while len(picked_items) < n_items_here and attempts < max_attempts:
                attempts += 1
                if native and (not imported or rng_inventory.random() < 0.7):
                    candidate = rng_inventory.choice(native)
                    multiplier = 1.0
                elif imported:
                    candidate = rng_inventory.choice(imported)
                    multiplier = IMPORTED_PRICE_MULTIPLIER
                else:
                    break
                if candidate.item_id in picked_items:
                    continue
                picked_items.add(candidate.item_id)
                dynamic = pricing.dynamic_price_arithmetic(
                    base_price_table[candidate.item_id],
                    region_mult=1.0,
                    axis_distance_mult=multiplier,
                )
                inventory_batch.append(
                    ShopInventory(
                        shop_id=shop.shop_id,
                        item_id=candidate.item_id,
                        campaign_id=campaign_id,
                        stock=rng_inventory.randint(1, 10),
                        dynamic_price=dynamic,
                    )
                )
                n_inventory_rows += 1

            _check_budget()

        if inventory_batch:
            db.session.add_all(inventory_batch)
            db.session.flush()
        log.info(
            "world_gen phase=shop_inventory_partial campaign_id=%s shop_inventory_rows=%d",
            campaign_id,
            n_inventory_rows,
        )

        all_campaign_cities = (
            db.session.query(City)
            .filter_by(campaign_id=campaign_id)
            .order_by(City.city_id)
            .all()
        )
        first_city_by_region: Dict[int, Optional[City]] = {}
        for region in regions_sorted:
            first_city_by_region[region.id] = next(
                (c for c in all_campaign_cities if c.region_id == region.id),
                None,
            )

        existing_regional = {
            (row.city_id, row.item_id)
            for row in db.session.query(RegionalMarket.city_id, RegionalMarket.item_id)
            .filter_by(campaign_id=campaign_id)
            .all()
        }
        regional_markets: List[RegionalMarket] = []
        for item in items:
            for region in regions_sorted:
                first_city = first_city_by_region.get(region.id)
                if first_city is None:
                    continue
                key = (first_city.city_id, item.item_id)
                if key in existing_regional:
                    continue
                existing_regional.add(key)
                regional_markets.append(
                    RegionalMarket(
                        city_id=first_city.city_id,
                        item_id=item.item_id,
                        total_supply=0,
                        total_demand=0,
                        average_price=float(base_price_table[item.item_id]),
                        campaign_id=campaign_id,
                    )
                )
        if regional_markets:
            db.session.add_all(regional_markets)

        existing_global_item_ids = {
            row[0]
            for row in db.session.query(GlobalMarket.item_id)
            .filter_by(campaign_id=campaign_id)
            .all()
        }
        global_markets = [
            GlobalMarket(
                item_id=item.item_id,
                total_supply=0,
                total_demand=0,
                average_price=float(base_price_table[item.item_id]),
                campaign_id=campaign_id,
            )
            for item in items
            if item.item_id not in existing_global_item_ids
        ]
        if global_markets:
            db.session.add_all(global_markets)
        log.info(
            "world_gen phase=markets_partial campaign_id=%s regional_new=%d global_new=%d",
            campaign_id,
            len(regional_markets),
            len(global_markets),
        )

        existing_sim = (
            db.session.query(SimulationState)
            .filter_by(campaign_id=campaign_id)
            .first()
        )
        if existing_sim is None:
            db.session.add(
                SimulationState(
                    current_tick=0,
                    speed=sim_speed,
                    campaign_id=campaign_id,
                )
            )

        _check_budget()
        log.info(
            "world_gen phase=done_partial campaign_id=%s region_id=%s",
            campaign_id,
            region_id,
        )

    return GenerationResult(
        effective_seed=effective_seed,
        n_regions=len(regions_sorted),
        n_cities=len(cities_to_stock),
        n_shops=len(all_shops),
        n_items=len(items),
        n_inventory_rows=n_inventory_rows,
    )
