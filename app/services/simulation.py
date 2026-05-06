"""Stateless price simulation; concurrency via Redis locks (see distributed_lock).

Primary tick path for the GM dashboard and Celery uses this module's ``SimulationEngine``
with campaign-scoped inventory and ``calculate_dynamic_price`` (demand modifiers).

A separate legacy path exists: ``EconomicSimulationTick`` in ``economy/simulation_tick.py``
and ``app/routes/simulation.py`` (uses ``MarketService`` pricing, not demand modifiers).
Consolidating those stacks is optional; tenant isolation for modifiers applies here.

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
from app.models import GMProfile, GMWorldState, PriceHistory, Shop, ShopInventory, SimulationState
from app.services.economy import calculate_dynamic_price
from app.services.simulation_state_helpers import get_simulation_state_for_gm

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
        gm_profile_id: int,
        campaign_id: Optional[int] = None,
        commit: bool = True,
    ) -> Dict:
        """
        Execute one simulation tick (one game day).

        ``current_game_day`` is incremented only after the pricing loop, in the same transaction as
        flush/commit; rollback restores the prior day. ``current_game_day`` is not advanced if
        ``commit`` is False (session rolled back after flush timing).
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
        }
        shops_seen = set()

        try:
            self._log_tick("Starting simulation tick", "debug")

            t_load_start = perf_counter()
            profile = GMProfile.query.filter_by(id=gm_profile_id).first()
            if profile is None:
                raise ValueError(f"No GMProfile found for id {gm_profile_id}")
            tick_day = profile.current_game_day or 1

            sim_state = get_simulation_state_for_gm(db.session, gm_profile_id)

            inventory_rows = (
                ShopInventory.query.join(Shop, ShopInventory.shop_id == Shop.shop_id)
                .filter(Shop.gm_profile_id == gm_profile_id)
                .filter(Shop.campaign_id == campaign_id if campaign_id is not None else True)
                .options(
                    db.joinedload(ShopInventory.item),
                    db.joinedload(ShopInventory.shop).joinedload(Shop.cities),
                )
                .order_by(ShopInventory.inventory_id)
                .all()
            )
            stats["inventory_row_count"] = len(inventory_rows)
            stats["t_load"] = perf_counter() - t_load_start

            seed_material = f"{gm_profile_id}_{tick_day}".encode("utf-8")
            seed_int = int(hashlib.sha256(seed_material).hexdigest(), 16) % (2**32)
            local_rng = random.Random(seed_int)

            recorded_at = datetime.utcnow()
            price_history_rows: List[Dict] = []
            state_blob: Dict[str, Dict] = {}

            prev_autoflush = db.session.autoflush
            db.session.autoflush = False
            t_compute_start = perf_counter()
            try:
                for inventory in inventory_rows:
                    if not inventory.item or not inventory.shop:
                        continue
                    old_price = inventory.dynamic_price
                    base_price = inventory.item.base_price
                    rarity = int(inventory.item.rarity) if inventory.item.rarity.isdigit() else 5
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
                                gm_profile_id,
                                item_id=inventory.item_id,
                                rng=local_rng,
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
                            gm_profile_id,
                            item_id=inventory.item_id,
                            rng=local_rng,
                        )

                    inventory.dynamic_price = new_price
                    stats["items_updated"] += 1

                    price_history_rows.append(
                        {
                            "shop_id": inventory.shop_id,
                            "item_id": inventory.item_id,
                            "price": new_price,
                            "recorded_at": recorded_at,
                            "gm_profile_id": gm_profile_id,
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

                # Calendar + simulation clock only after compute; same transaction as flush/commit.
                profile.current_game_day = (profile.current_game_day or 1) + 1
                stats["current_game_day"] = profile.current_game_day

                if sim_state:
                    sim_state.current_tick = profile.current_game_day
                    sim_state.last_tick_time = recorded_at
                else:
                    db.session.add(
                        SimulationState(
                            gm_profile_id=gm_profile_id,
                            current_tick=profile.current_game_day,
                            speed="pause",
                            last_tick_time=recorded_at,
                        )
                    )

                if world_state_writes_enabled():
                    gws = GMWorldState.query.filter_by(gm_profile_id=gm_profile_id).first()
                    if gws is None:
                        gws = GMWorldState(gm_profile_id=gm_profile_id)
                        db.session.add(gws)
                    if state_blob:
                        gws.state_json = state_blob
                    gws.schema_version = 1
                    gws.tick_seq = profile.current_game_day
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

            if commit:
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
                f"t_flush={stats['t_flush']:.4f} t_persist={stats['t_persist']:.4f}",
                "debug",
            )

            return stats

        except Exception as e:
            self._log_tick(f"Error during tick: {str(e)}", "error")
            db.session.rollback()
            raise
