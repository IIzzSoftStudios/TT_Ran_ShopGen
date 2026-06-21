<<<<<<< HEAD
import random
import logging
import threading
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from app.extensions import db
from app.models.backend import Shop, ShopInventory, City, PriceHistory
from app.models.users import GMProfile
from app.services.economy import calculate_dynamic_price
from app.config.simulation_config import SimulationConfig, default_config
from app.config.price_history_config import default_price_history_retention

class SimulationEngine:
    """Handles the simulation of the game economy."""
    
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_lock(cls) -> threading.Lock:
        return cls._lock

    def __new__(cls, config: Optional[SimulationConfig] = None):
        if cls._instance is None:
            cls._instance = super(SimulationEngine, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, config: Optional[SimulationConfig] = None):
        if self._initialized:
            return
            
        self.config = config or default_config
        self._setup_logging()
        self.current_speed = "pause"
        self.last_tick_time = datetime.now()
        # Retention configuration for PriceHistory snapshots
        self.price_history_retention = default_price_history_retention
        self._initialized = True
        self._log_tick("SimulationEngine initialized")
        self._debug_state()
        
    def _setup_logging(self):
        """Configure logging for simulation events."""
        if self.config.enable_tick_logging:
            logging.basicConfig(
                filename=self.config.log_file_path,
                level=logging.DEBUG,  # Changed to DEBUG for more detailed logging
                format='%(asctime)s - %(levelname)s - %(message)s'
            )
            self.logger = logging.getLogger('simulation')
        else:
            self.logger = None
            
    def _log_tick(self, message: str, level: str = "info"):
        """Log a simulation event if logging is enabled."""
        if self.logger:
            if level == "debug":
                self.logger.debug(message)
            elif level == "info":
                self.logger.info(message)
            elif level == "warning":
                self.logger.warning(message)
            elif level == "error":
                self.logger.error(message)
        print(f"[Simulation] {message}")  # Also print to console for debugging
            
    def _debug_state(self):
        """Log the current state of the simulation engine."""
        self._log_tick(
            f"Current State:\n"
            f"  Speed: {self.current_speed}\n"
            f"  Last Tick: {self.last_tick_time}\n"
            f"  Time Since Last Tick: {datetime.now() - self.last_tick_time}\n"
            f"  Speed Multiplier: {self.get_speed_multiplier()}",
            "debug"
        )
            
    def _calculate_price_change(self, current_price: float) -> float:
        """Calculate a random price change within configured bounds."""
        try:
            if current_price <= 0:
                self._log_tick(f"Warning: Invalid current price {current_price}, using minimum price", "warning")
                current_price = 1.0  # Use a minimum price of 1.0 instead of base_price
                
            change_percent = random.uniform(
                self.config.min_price_change_percent,
                self.config.max_price_change_percent
            )
            
            # Ensure we don't get a zero or negative price
            new_price = current_price * (1 + change_percent / 100)
            if new_price <= 0:
                self._log_tick(f"Warning: Calculated price {new_price} is invalid, using minimum price", "warning")
                new_price = 1.0  # Use a minimum price of 1.0 instead of base_price
                
            return round(new_price, 2)
            
        except Exception as e:
            self._log_tick(f"Error calculating price change: {str(e)}", "error")
            return 1.0  # Return minimum price on error
        
    def set_speed(self, speed: str):
        """Set the simulation speed."""
        valid_speeds = ["pause", "day", "week", "month", "year"]
        if speed not in valid_speeds:
            raise ValueError(f"Invalid speed: {speed}. Must be one of {valid_speeds}")
        old_speed = self.current_speed
        self.current_speed = speed
        self._log_tick(f"Speed changed from {old_speed} to {speed}")
        self._debug_state()
        
    def get_speed_multiplier(self) -> int:
        """Get the time multiplier for the current speed setting (used for real-time tick scheduling)."""
        if self.current_speed == "pause":
            return 0
        # day, week, month, year are used as time-period buttons; return 1 if any is set
        return 1
        
    def should_run_tick(self) -> bool:
        """Determine if a tick should run based on current speed and time elapsed."""
        self._debug_state()  # Log current state before checking
        
        if self.current_speed == "pause":
            self._log_tick("Simulation paused, skipping tick", "debug")
            return False
            
        multiplier = self.get_speed_multiplier()
        if multiplier == 0:
            self._log_tick("Speed multiplier is 0, skipping tick", "debug")
            return False
            
        # Calculate time since last tick
        time_since_last = datetime.now() - self.last_tick_time
        # For 1x speed, run every second
        # For other speeds, adjust accordingly
        required_interval = timedelta(seconds=1 / multiplier)
        
        should_run = time_since_last >= required_interval
        if should_run:
            self._log_tick(
                f"Time to run tick:\n"
                f"  Time elapsed: {time_since_last.total_seconds():.1f}s\n"
                f"  Required interval: {required_interval.total_seconds():.1f}s\n"
                f"  Speed: {self.current_speed}\n"
                f"  Multiplier: {multiplier}",
                "debug"
            )
        else:
            self._log_tick(
                f"Not time for tick yet:\n"
                f"  Time elapsed: {time_since_last.total_seconds():.1f}s\n"
                f"  Required interval: {required_interval.total_seconds():.1f}s\n"
                f"  Speed: {self.current_speed}\n"
                f"  Multiplier: {multiplier}",
                "debug"
            )
        
        return should_run
        
    def run_tick(self, gm_profile_id: int, commit: bool = True) -> Dict:
        """
        Execute one simulation tick (one tick = one game day).
        Args:
            gm_profile_id: The ID of the GM whose shops should be updated
            commit: If True, commit at end of tick; if False, caller commits (e.g. once per time period).
        Returns a dictionary containing tick results and statistics.
        """
        tick_start = datetime.now()
        stats = {
            'shops_updated': 0,
            'items_updated': 0,
            'price_changes': [],
            'tick_duration': 0
        }
        shops_seen = set()

        try:
            self._log_tick("Starting simulation tick", "debug")

            # Single batch query: all ShopInventory for GM's shops with item and shop.cities eager-loaded
            inventory_rows = (
                ShopInventory.query
                .join(Shop, ShopInventory.shop_id == Shop.shop_id)
                .filter(Shop.gm_profile_id == gm_profile_id)
=======
"""Stateless price simulation; concurrency via Redis locks (see distributed_lock).

Primary tick path for the GM dashboard and Celery uses this module's ``SimulationEngine``
with campaign-scoped inventory and ``calculate_dynamic_price`` (demand modifiers).

A separate legacy path exists in ``economy/simulation_tick.py`` (uses ``MarketService``
pricing, not demand modifiers); both stacks now key off ``campaign_id`` only.

Phase 1 instrumentation: ``t_load``, ``t_compute``, ``t_flush``, ``t_persist``; compute phase uses
``session.autoflush = False`` to avoid hidden flush mid-loop (SQLAlchemy autoflush before queries
would emit N INSERTs early and corrupt timing). Dual-write to ``GMWorldState`` when
``WORLD_STATE_ENABLED`` is True — otherwise rows remain sole source of truth; enabling reads from
blob without that flag risks divergence under retry (see ``READ_PRICES_FROM_WORLD_STATE``).
"""

from __future__ import annotations

import hashlib
import logging
import os
import random
import uuid
from dataclasses import dataclass
from datetime import datetime
from time import perf_counter
from typing import Dict, List, Optional

from app.constants.simulation_flags import world_state_writes_enabled
from app.extensions import db
from app.models import (
    Campaign,
    GMWorldState,
    PriceHistory,
    Shop,
    ShopInventory,
    SimulationState,
)
from app.services.economy import calculate_dynamic_price
from app.services.economy.demand import DemandContext, load_active_modifiers_for_campaign
from app.services.economy.supply_demand import (
    apply_supply_demand_to_inventory_rows,
    backfill_shop_restock_schedules,
)
from app.services.world_generator.pricing import rarity_for_simulation
from app.services.simulation_state_helpers import get_simulation_state_for_campaign
from app.services.world_generator.campaign_settings import (
    read_market_volatility,
    read_supply_demand_flag,
)

logger = logging.getLogger(__name__)


@dataclass
class SimulationConfig:
    enable_tick_logging: bool = False
    log_file_path: str = "simulation.log"


default_config = SimulationConfig()
default_price_history_retention = 30  # days; reserved for future pruning


class SimulationEngine:
    """
    Stateless simulation utility.

    Concurrency safety must be handled outside this class (e.g., Redis distributed locks),
    and any simulation scheduling/timing state must live in persistent storage.
    """

    def __init__(self, config: Optional[SimulationConfig] = None):
        self.config = config or default_config
        self._setup_logging()
        self.price_history_retention = default_price_history_retention

    def _setup_logging(self) -> None:
        if self.config.enable_tick_logging:
            logging.basicConfig(
                filename=self.config.log_file_path,
                level=logging.DEBUG,
                format="%(asctime)s - %(levelname)s - %(message)s",
            )
            self.tick_logger = logging.getLogger("simulation")
        else:
            self.tick_logger = None

    def _log_tick(self, message: str, level: str = "info") -> None:
        if self.tick_logger:
            log_fn = getattr(self.tick_logger, level, self.tick_logger.info)
            log_fn(message)
        logger.debug(message)

    def run_tick(
        self,
        campaign_id: int,
        commit: bool = True,
        flush_only: bool = False,
    ) -> Dict:
        """
        Execute one simulation tick (one game day) for a single campaign.

        ``current_game_day`` is incremented on the Campaign row only after the pricing loop, in
        the same transaction as flush/commit; rollback restores the prior day. ``current_game_day``
        is not advanced if ``commit`` is False (session rolled back after flush timing).

        When ``flush_only=True`` the engine flushes pending changes but neither commits nor
        rolls back — the caller owns the outer transaction. This is the path used by the ACID
        batch driver (``run_period_task``): all 365 ticks of a Year share one transaction, so
        a mid-batch failure rolls back every tick (and every PriceHistory row) atomically and
        the campaign world is never left half-advanced. ``flush_only`` takes precedence over
        ``commit``.
        """
        tick_start = perf_counter()
        stats: Dict = {
            "shops_updated": 0,
            "items_updated": 0,
            "price_changes": [],
            "tick_duration": 0.0,
            "t_load": 0.0,
            "t_compute": 0.0,
            "t_flush": 0.0,
            "t_persist": 0.0,
            "t_orm_pressure": 0.0,
            "session_dirty_count": 0,
            "session_new_count": 0,
            "inventory_row_count": 0,
            "world_state_written": False,
            "units_sold": 0,
            "shops_restocked": 0,
            "supply_demand_ms": 0.0,
            "supply_demand_enabled": True,
        }
        shops_seen = set()

        try:
            self._log_tick("Starting simulation tick", "debug")

            t_load_start = perf_counter()
            campaign = Campaign.query.filter_by(id=campaign_id).first()
            if campaign is None:
                raise ValueError(f"No Campaign found for id {campaign_id}")
            tick_day = campaign.current_game_day or 1

            sim_state = get_simulation_state_for_campaign(db.session, campaign_id)

            inventory_rows = (
                ShopInventory.query.join(Shop, ShopInventory.shop_id == Shop.shop_id)
                .filter(Shop.campaign_id == campaign_id)
>>>>>>> GCP
                .options(
                    db.joinedload(ShopInventory.item),
                    db.joinedload(ShopInventory.shop).joinedload(Shop.cities),
                )
<<<<<<< HEAD
                .all()
            )
            self._log_tick(f"Found {len(inventory_rows)} inventory rows to update", "debug")

            for inventory in inventory_rows:
                old_price = inventory.dynamic_price
                base_price = inventory.item.base_price
                rarity = int(inventory.item.rarity) if inventory.item.rarity.isdigit() else 5
                shop = inventory.shop
                cities = shop.cities if shop else []

                # Per-city evaluation (in memory): aggregate to one price per row for future modifiers
                if cities:
                    prices = []
                    for city in cities:
                        p = calculate_dynamic_price(
                            base_price=base_price,
                            rarity=rarity,
                            stock_level=inventory.stock,
                            shop_id=shop.shop_id,
                            city_id=city.city_id
                        )
                        prices.append(p)
                    new_price = round(sum(prices) / len(prices), 2)
                else:
                    new_price = calculate_dynamic_price(
                        base_price=base_price,
                        rarity=rarity,
                        stock_level=inventory.stock,
                        shop_id=shop.shop_id if shop else None,
                        city_id=None
                    )

                inventory.dynamic_price = new_price
                stats['items_updated'] += 1

                # Snapshot for stock-style charts (same transaction)
                db.session.add(PriceHistory(
                    shop_id=inventory.shop_id,
                    item_id=inventory.item_id,
                    price=new_price,
                    recorded_at=datetime.utcnow(),
                    gm_profile_id=gm_profile_id
                ))

                if old_price > 0 and abs(new_price - old_price) / old_price > 0.10:
                    primary_city_id = cities[0].city_id if cities else None
                    stats['price_changes'].append({
                        'item_id': inventory.item_id,
                        'city_id': primary_city_id,
                        'old_price': old_price,
                        'new_price': new_price
                    })

                if shop and shop.shop_id not in shops_seen:
                    shops_seen.add(shop.shop_id)
                    stats['shops_updated'] += 1

            profile = GMProfile.query.filter_by(id=gm_profile_id).first()
            if profile is None:
                raise ValueError(f"No GMProfile found for id {gm_profile_id}")
            profile.current_game_day = (profile.current_game_day or 1) + 1
            stats["current_game_day"] = profile.current_game_day

            if commit:
                db.session.commit()

            self.last_tick_time = datetime.now()
            tick_duration = (datetime.now() - tick_start).total_seconds()
            stats['tick_duration'] = tick_duration

            self._log_tick(
                f"Tick completed:\n"
                f"  Shops updated: {stats['shops_updated']}\n"
                f"  Items updated: {stats['items_updated']}\n"
                f"  Duration: {tick_duration:.2f}s\n"
                f"  New last tick time: {self.last_tick_time}",
                "debug"
            )

            return stats

        except Exception as e:
            self._log_tick(f"Error during tick: {str(e)}", "error")
            db.session.rollback()
            raise

    def run_time_period(self, gm_profile_id: int, time_period: str) -> Dict:
        """
        Run multiple ticks to simulate a specific time period. One tick = one game day.
        Args:
            gm_profile_id: The ID of the GM whose shops should be updated
            time_period: One of "day", "week", "month", "year"
        Returns a dictionary containing simulation results and statistics.
        """
        ticks_per_period = {
            "day": 1,
            "week": 7,
            "month": 30,
            "year": 365
        }
        if time_period not in ticks_per_period:
            raise ValueError(f"Invalid time period: {time_period}. Must be one of {list(ticks_per_period.keys())}")

        total_ticks = ticks_per_period[time_period]
        total_stats = {
            'shops_updated': 0,
            'items_updated': 0,
            'price_changes': [],
            'total_duration': 0,
            'ticks_completed': 0
        }

        self._log_tick(f"Starting {time_period} simulation ({total_ticks} ticks)", "debug")

        for i in range(total_ticks):
            try:
                tick_stats = self.run_tick(gm_profile_id, commit=False)
                total_stats['shops_updated'] += tick_stats['shops_updated']
                total_stats['items_updated'] += tick_stats['items_updated']
                total_stats['price_changes'].extend(tick_stats['price_changes'])
                total_stats['total_duration'] += tick_stats['tick_duration']
                total_stats['ticks_completed'] += 1
            except Exception as e:
                self._log_tick(f"Error during tick {i+1}/{total_ticks}: {str(e)}", "error")
                db.session.rollback()
                break
        else:
            db.session.commit()

        self._log_tick(
            f"Time period simulation completed:\n"
            f"  Period: {time_period}\n"
            f"  Ticks completed: {total_stats['ticks_completed']}/{total_ticks}\n"
            f"  Total shops updated: {total_stats['shops_updated']}\n"
            f"  Total items updated: {total_stats['items_updated']}\n"
            f"  Total duration: {total_stats['total_duration']:.2f}s",
            "debug"
        )

        return total_stats 
=======
                .order_by(ShopInventory.inventory_id)
                .all()
            )
            stats["inventory_row_count"] = len(inventory_rows)
            stats["t_load"] = perf_counter() - t_load_start

            seed_material = f"{campaign_id}_{tick_day}".encode("utf-8")
            seed_int = int(hashlib.sha256(seed_material).hexdigest(), 16) % (2**32)
            local_rng = random.Random(seed_int)

            run_supply = read_supply_demand_flag(campaign_id)
            stats["supply_demand_enabled"] = run_supply
            market_volatility = read_market_volatility(campaign_id)
            stats["market_volatility"] = market_volatility

            if run_supply and inventory_rows:
                backfill_shop_restock_schedules(
                    campaign_id, tick_day, local_rng
                )
                sd_stats = apply_supply_demand_to_inventory_rows(
                    inventory_rows,
                    tick_day,
                    local_rng,
                )
                stats["units_sold"] = sd_stats.get("units_sold", 0)
                stats["shops_restocked"] = sd_stats.get("shops_restocked", 0)
                stats["supply_demand_ms"] = sd_stats.get("supply_demand_ms", 0.0)
                if stats["units_sold"] == 0 and any(
                    int(inv.stock or 0) > 0 for inv in inventory_rows
                ):
                    logger.warning(
                        "supply_demand sold 0 units but campaign %s has in-stock "
                        "rows on game day %s (check Supply On and item prices)",
                        campaign_id,
                        tick_day,
                    )
            elif not run_supply and inventory_rows:
                logger.debug(
                    "supply_demand skipped for campaign %s (Supply Off in world config)",
                    campaign_id,
                )

            recorded_at = datetime.utcnow()
            price_history_rows: List[Dict] = []
            state_blob: Dict[str, Dict] = {}

            active_modifiers = load_active_modifiers_for_campaign(campaign_id)
            demand_context = DemandContext.from_modifiers(
                campaign_id, active_modifiers
            )

            prev_autoflush = db.session.autoflush
            db.session.autoflush = False
            t_compute_start = perf_counter()
            try:
                for inventory in inventory_rows:
                    if not inventory.item or not inventory.shop:
                        continue
                    old_price = inventory.dynamic_price
                    base_price = inventory.item.base_price
                    rarity = rarity_for_simulation(inventory.item.rarity)
                    shop = inventory.shop
                    cities = sorted((shop.cities if shop else []), key=lambda c: c.city_id)

                    if cities:
                        prices = []
                        for city in cities:
                            p = calculate_dynamic_price(
                                base_price,
                                rarity,
                                inventory.stock,
                                shop.shop_id,
                                city.city_id,
                                campaign_id,
                                item_id=inventory.item_id,
                                rng=local_rng,
                                demand_context=demand_context,
                                market_volatility=market_volatility,
                            )
                            prices.append(p)
                        new_price = round(sum(prices) / len(prices), 2)
                    else:
                        new_price = calculate_dynamic_price(
                            base_price,
                            rarity,
                            inventory.stock,
                            shop.shop_id if shop else None,
                            None,
                            campaign_id,
                            item_id=inventory.item_id,
                            rng=local_rng,
                            demand_context=demand_context,
                            market_volatility=market_volatility,
                        )

                    inventory.dynamic_price = new_price
                    stats["items_updated"] += 1

                    price_history_rows.append(
                        {
                            "shop_id": inventory.shop_id,
                            "item_id": inventory.item_id,
                            "price": new_price,
                            "recorded_at": recorded_at,
                            "campaign_id": campaign_id,
                        }
                    )

                    state_blob[str(inventory.inventory_id)] = {
                        "dynamic_price": new_price,
                        "stock": inventory.stock,
                    }

                    if old_price and old_price > 0 and abs(new_price - old_price) / old_price > 0.10:
                        primary_city_id = cities[0].city_id if cities else None
                        stats["price_changes"].append(
                            {
                                "item_id": inventory.item_id,
                                "city_id": primary_city_id,
                                "old_price": old_price,
                                "new_price": new_price,
                            }
                        )

                    if shop and shop.shop_id not in shops_seen:
                        shops_seen.add(shop.shop_id)
                        stats["shops_updated"] += 1

                if price_history_rows:
                    db.session.bulk_insert_mappings(PriceHistory, price_history_rows)

                campaign.current_game_day = (campaign.current_game_day or 1) + 1
                stats["current_game_day"] = campaign.current_game_day

                if sim_state:
                    sim_state.current_tick = campaign.current_game_day
                    sim_state.last_tick_time = recorded_at
                else:
                    db.session.add(
                        SimulationState(
                            campaign_id=campaign_id,
                            current_tick=campaign.current_game_day,
                            speed="pause",
                            last_tick_time=recorded_at,
                        )
                    )

                if world_state_writes_enabled():
                    gws = GMWorldState.query.filter_by(campaign_id=campaign_id).first()
                    if gws is None:
                        gws = GMWorldState(campaign_id=campaign_id)
                        db.session.add(gws)
                    if state_blob:
                        gws.state_json = state_blob
                    gws.schema_version = 1
                    gws.tick_seq = campaign.current_game_day
                    gws.tick_generation_id = str(uuid.uuid4())
                    gws.updated_at = recorded_at
                    stats["world_state_written"] = True

                stats["session_dirty_count"] = len(db.session.dirty)
                stats["session_new_count"] = len(db.session.new)

                if os.getenv("SIM_TICK_DEBUG_ASSERTS"):
                    # bulk_insert_mappings may not populate session.new like ORM add(); assert dirty set scale.
                    assert stats["session_dirty_count"] >= 0

            finally:
                db.session.autoflush = prev_autoflush

            stats["t_compute"] = perf_counter() - t_compute_start
            stats["t_orm_pressure"] = stats["t_compute"]

            t_flush_start = perf_counter()
            db.session.flush()
            t_flush_end = perf_counter()
            stats["t_flush"] = t_flush_end - t_flush_start

            if flush_only:
                stats["t_persist"] = 0.0
            elif commit:
                t_commit_start = perf_counter()
                db.session.commit()
                db.session.expire_all()
                stats["t_persist"] = perf_counter() - t_commit_start
            else:
                db.session.rollback()
                stats["t_persist"] = 0.0

            stats["tick_duration"] = perf_counter() - tick_start

            self._log_tick(
                f"Tick completed: shops={stats['shops_updated']} items={stats['items_updated']} "
                f"duration={stats['tick_duration']:.4f}s "
                f"t_load={stats['t_load']:.4f} t_compute={stats['t_compute']:.4f} "
                f"t_flush={stats['t_flush']:.4f} t_persist={stats['t_persist']:.4f} "
                f"units_sold={stats.get('units_sold', 0)} "
                f"shops_restocked={stats.get('shops_restocked', 0)} "
                f"supply_demand_ms={stats.get('supply_demand_ms', 0):.3f}",
                "debug",
            )

            return stats

        except Exception as e:
            self._log_tick(f"Error during tick: {str(e)}", "error")
            db.session.rollback()
            raise
>>>>>>> GCP
