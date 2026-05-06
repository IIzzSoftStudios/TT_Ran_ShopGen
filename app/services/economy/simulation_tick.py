"""Legacy economic tick: regional/global markets via MarketService (not demand modifiers).

Dashboard/Celery simulation uses ``app.services.simulation.SimulationEngine`` instead.
"""
from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy import func
from app.models import (
    Shop, ShopInventory, Item, City,
    ResourceTransform, MarketEvent,
    SimulationState, SimulationLog,
    DemandModifier, ModifierTarget
)
from app.extensions import db
from app.services.economy.market_service import MarketService
from app.services.simulation_state_helpers import get_simulation_state_for_gm

class EconomicSimulationTick:
    def __init__(self, gm_profile_id: int, campaign_id: Optional[int] = None):
        self.gm_profile_id = gm_profile_id
        self.campaign_id = campaign_id
        self.current_tick = self._get_current_tick()
        self.market_service = MarketService(gm_profile_id, campaign_id=campaign_id)
        self.global_supply: Dict[int, float] = {}  # item_id -> total supply
        self.global_demand: Dict[int, float] = {}  # item_id -> total demand
        self.city_demands: Dict[int, Dict[int, float]] = {}  # city_id -> {item_id -> demand}

    def _get_current_tick(self) -> int:
        """Get the current simulation tick number."""
        state = get_simulation_state_for_gm(db.session, self.gm_profile_id)
        return state.current_tick if state else 0

    def _log_event(self, event_type: str, details: dict):
        """Log a simulation event."""
        log = SimulationLog(
            tick_id=self.current_tick,
            event_type=event_type,
            details=details,
            gm_profile_id=self.gm_profile_id,
            campaign_id=self.campaign_id,
        )
        db.session.add(log)

    def _calculate_global_market(self):
        """Calculate global supply and demand for all items."""
        # Reset global market state
        self.global_supply.clear()
        self.global_demand.clear()

        # Calculate global supply from all shops
        for shop in Shop.query.filter_by(gm_profile_id=self.gm_profile_id).filter(
            Shop.campaign_id == self.campaign_id if self.campaign_id is not None else True
        ).all():
            for inventory in shop.inventory:
                item_id = inventory.item_id
                self.global_supply[item_id] = self.global_supply.get(item_id, 0) + inventory.stock

        # Calculate city-specific demands
        for city in City.query.filter_by(gm_profile_id=self.gm_profile_id).filter(
            City.campaign_id == self.campaign_id if self.campaign_id is not None else True
        ).all():
            self.city_demands[city.city_id] = {}
            # TODO: Implement population-based demand calculation
            # For now, use fixed demand values
            for item in Item.query.filter_by(gm_profile_id=self.gm_profile_id).filter(
                Item.campaign_id == self.campaign_id if self.campaign_id is not None else True
            ).all():
                base_demand = 10  # Placeholder
                self.city_demands[city.city_id][item.item_id] = base_demand
                self.global_demand[item.item_id] = self.global_demand.get(item.item_id, 0) + base_demand

    def _process_building_production(self):
        """Process production from buildings."""
        # TODO: Implement building production logic
        # This will require adding building models and production rules
        pass

    def _process_npc_purchases(self):
        """Simulate NPC purchases from shops."""
        for city_id, demands in self.city_demands.items():
            city = City.query.filter_by(
                city_id=city_id, gm_profile_id=self.gm_profile_id
            ).filter(
                City.campaign_id == self.campaign_id if self.campaign_id is not None else True
            ).first()
            if not city:
                continue

            city_shops = Shop.query.join(Shop.cities).filter(
                City.city_id == city_id,
                Shop.gm_profile_id == self.gm_profile_id,
                Shop.campaign_id == self.campaign_id if self.campaign_id is not None else True,
            ).all()

            for shop in city_shops:
                for inventory in shop.inventory:
                    item_id = inventory.item_id
                    if item_id in demands:
                        # Calculate purchase amount based on demand and available stock
                        demand = demands[item_id]
                        available_stock = inventory.stock
                        purchase_amount = min(demand, available_stock)

                        if purchase_amount > 0:
                            # Update stock and shop revenue
                            inventory.stock -= purchase_amount
                            revenue = purchase_amount * inventory.dynamic_price
                            # TODO: Add revenue to shop balance

                            # Update market states
                            self.market_service.update_regional_demand(city, inventory.item, purchase_amount)
                            self.market_service.update_global_demand(inventory.item, purchase_amount)

                            self._log_event("purchase", {
                                "shop_id": shop.shop_id,
                                "item_id": item_id,
                                "amount": purchase_amount,
                                "revenue": revenue
                            })

    def _update_shop_prices(self):
        """Update prices for all shop inventories."""
        for shop in Shop.query.filter_by(gm_profile_id=self.gm_profile_id).filter(
            Shop.campaign_id == self.campaign_id if self.campaign_id is not None else True
        ).all():
            city = shop.cities[0] if shop.cities else None
            
            for inventory in shop.inventory:
                old_price = inventory.dynamic_price
                new_price = self.market_service.get_item_price(shop, inventory.item, city)
                
                inventory.dynamic_price = new_price

                if old_price != new_price:
                    self._log_event("price_change", {
                        "shop_id": shop.shop_id,
                        "item_id": inventory.item_id,
                        "old_price": old_price,
                        "new_price": new_price
                    })

    def _check_shop_viability(self):
        """Check if shops are viable or should be marked as bankrupt."""
        for shop in Shop.query.filter_by(gm_profile_id=self.gm_profile_id).filter(
            Shop.campaign_id == self.campaign_id if self.campaign_id is not None else True
        ).all():
            # Calculate total inventory value
            inventory_value = sum(
                inv.stock * inv.dynamic_price
                for inv in shop.inventory
            )

            # TODO: Implement proper shop balance tracking
            # For now, just check if inventory value is positive
            if inventory_value <= 0:
                self._log_event("bankruptcy", {
                    "shop_id": shop.shop_id,
                    "inventory_value": inventory_value
                })

    def _update_simulation_state(self):
        """Update the simulation state for the next tick."""
        state = get_simulation_state_for_gm(db.session, self.gm_profile_id)
        if state:
            state.current_tick += 1
            state.last_tick_time = datetime.utcnow()
        else:
            state = SimulationState(
                gm_profile_id=self.gm_profile_id,
                current_tick=1,
                last_tick_time=datetime.utcnow()
            )
            db.session.add(state)

    def run_tick(self):
        """Run a complete economic simulation tick."""
        try:
            # Calculate global market state
            self._calculate_global_market()

            # Process building production
            self._process_building_production()

            # Process NPC purchases
            self._process_npc_purchases()

            # Update shop prices
            self._update_shop_prices()

            # Check shop viability
            self._check_shop_viability()

            # Update simulation state
            self._update_simulation_state()

            # Commit all changes
            db.session.commit()
            db.session.expire_all()

            return True, "Simulation tick completed successfully"

        except Exception as e:
            db.session.rollback()
            return False, f"Error during simulation tick: {str(e)}" 