from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy import func
from app.models import (
    Shop, ShopInventory, Item, City, ResourceNode,
    ProductionHistory, ResourceTransform, MarketEvent,
    ShopMaintenance, SimulationState, SimulationLog,
    DemandModifier, ModifierTarget
)
from app.extensions import db
from app.services.economy.demand import calculate_demand
from app.services.economy.market_service import MarketService
from app.services.logging_config import event_logger
import logging

logger = logging.getLogger(__name__)

class EconomicSimulationTick:
    def __init__(self, gm_profile_id: int):
        self.gm_profile_id = gm_profile_id
        self.current_tick = self._get_current_tick()
        self.market_service = MarketService(gm_profile_id)
        self.global_supply: Dict[int, float] = {}  # item_id -> total supply
        self.global_demand: Dict[int, float] = {}  # item_id -> total demand
        self.city_demands: Dict[int, Dict[int, float]] = {}  # city_id -> {item_id -> demand}

    def _get_current_tick(self) -> int:
        """Get the current simulation tick number."""
        state = SimulationState.query.filter_by(gm_profile_id=self.gm_profile_id).first()
        return state.current_tick if state else 0

    def _log_event(self, event_type: str, details: dict):
        """Log a simulation event."""
        log = SimulationLog(
            tick_id=self.current_tick,
            event_type=event_type,
            details=details,
            gm_profile_id=self.gm_profile_id
        )
        db.session.add(log)
        # Also log to event logger
        event_logger.log_error(self.gm_profile_id, event_type, str(details))

    def _calculate_global_market(self):
        """Calculate global supply and demand for all items."""
        # Reset global market state
        self.global_supply.clear()
        self.global_demand.clear()

        # Calculate global supply from all shops
        for shop in Shop.query.filter_by(gm_profile_id=self.gm_profile_id).all():
            for inventory in shop.inventory:
                item_id = inventory.item_id
                self.global_supply[item_id] = self.global_supply.get(item_id, 0) + inventory.stock

        # Calculate city-specific demands
        for city in City.query.filter_by(gm_profile_id=self.gm_profile_id).all():
            self.city_demands[city.city_id] = {}
            # TODO: Implement population-based demand calculation
            # For now, use fixed demand values
            for item in Item.query.filter_by(gm_profile_id=self.gm_profile_id).all():
                base_demand = 10  # Placeholder
                self.city_demands[city.city_id][item.item_id] = base_demand
                self.global_demand[item.item_id] = self.global_demand.get(item.item_id, 0) + base_demand

    def _process_resource_nodes(self):
        """Process production from resource nodes."""
        logger.info(f"Processing resource nodes for GM {self.gm_profile_id}")
        nodes = ResourceNode.query.filter_by(gm_profile_id=self.gm_profile_id).all()
        logger.debug(f"Found {len(nodes)} resource nodes to process")
        
        for node in nodes:
            try:
                logger.debug(f"Processing node {node.node_id}: {node.name} (Type: {node.type})")
                
                # Validate node data
                if not node.item:
                    logger.error(f"Resource node {node.node_id} has no associated item")
                    continue
                    
                if not node.city:
                    logger.error(f"Resource node {node.node_id} has no associated city")
                    continue
                
                # Calculate production
                amount_produced = node.production_rate * node.quality
                logger.debug(f"Node {node.node_id} produced {amount_produced} units of {node.item.name}")
                
                # Record production history
                history = ProductionHistory(
                    node_id=node.node_id,
                    amount_produced=amount_produced,
                    quality=node.quality
                )
                db.session.add(history)
                logger.debug(f"Added production history for node {node.node_id}")

                # Update regional market with produced resources
                self.market_service.update_regional_supply(node.city, node.item, amount_produced)
                self.market_service.update_global_supply(node.item, amount_produced)
                logger.debug(f"Updated market supply for node {node.node_id}")
                
            except Exception as e:
                logger.error(f"Error processing resource node {node.node_id}: {str(e)}", exc_info=True)
                continue  # Continue with next node even if one fails
                
        logger.info(f"Completed processing resource nodes for GM {self.gm_profile_id}")

    def _process_building_production(self):
        """Process production from buildings."""
        # TODO: Implement building production logic
        # This will require adding building models and production rules
        pass

    def _process_npc_purchases(self):
        """Simulate NPC purchases from shops."""
        for city_id, demands in self.city_demands.items():
            city = City.query.get(city_id)
            if not city:
                continue

            city_shops = Shop.query.join(Shop.cities).filter(
                City.city_id == city_id,
                Shop.gm_profile_id == self.gm_profile_id
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
        for shop in Shop.query.filter_by(gm_profile_id=self.gm_profile_id).all():
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
        for shop in Shop.query.filter_by(gm_profile_id=self.gm_profile_id).all():
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

    def _process_shop_maintenance(self):
        """Process daily maintenance costs for shops."""
        for shop in Shop.query.filter_by(gm_profile_id=self.gm_profile_id).all():
            maintenance = ShopMaintenance.query.filter_by(shop_id=shop.shop_id).first()
            if maintenance:
                # TODO: Implement proper shop balance tracking
                # For now, just log the maintenance cost
                self._log_event("maintenance", {
                    "shop_id": shop.shop_id,
                    "cost": maintenance.daily_cost
                })

    def _update_simulation_state(self):
        """Update the simulation state for the next tick."""
        state = SimulationState.query.filter_by(gm_profile_id=self.gm_profile_id).first()
        if state:
            # Only update last_tick_time, don't increment tick count
            state.last_tick_time = datetime.utcnow()
            state.update_performance_metrics(0)  # Will be updated with actual duration
            logger.debug(f"Updated simulation state for GM {self.gm_profile_id}: last_tick={state.last_tick_time}")
        else:
            state = SimulationState(
                gm_profile_id=self.gm_profile_id,
                current_tick=1,
                last_tick_time=datetime.utcnow(),
                speed="pause"  # Default to pause
            )
            db.session.add(state)
            logger.debug(f"Created new simulation state for GM {self.gm_profile_id}")

    def run_tick(self):
        """Run a single simulation tick."""
        try:
            start_time = datetime.utcnow()
            event_logger.log_tick_start(self.gm_profile_id, self.current_tick)
            
            # Calculate global market state
            self._calculate_global_market()
            
            # Process resource nodes
            self._process_resource_nodes()
            
            # Process building production
            self._process_building_production()
            
            # Process NPC purchases
            self._process_npc_purchases()
            
            # Update shop prices
            self._update_shop_prices()
            
            # Check shop viability
            self._check_shop_viability()
            
            # Process shop maintenance
            self._process_shop_maintenance()
            
            # Update simulation state
            self._update_simulation_state()
            
            # Calculate duration
            duration = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            # Log successful tick completion
            event_logger.log_tick_end(self.gm_profile_id, self.current_tick, duration)
            
            return True, "Tick completed successfully"
            
        except Exception as e:
            logger.error(f"Error during simulation tick: {str(e)}", exc_info=True)
            event_logger.log_error(self.gm_profile_id, "tick_error", str(e))
            return False, str(e) 