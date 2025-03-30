from typing import Dict, List, Optional, Tuple
from datetime import datetime
from sqlalchemy import func
from app.models import (
    Shop, ShopInventory, Item, City, RegionalMarket,
    GlobalMarket, SimulationLog
)
from app.extensions import db

class MarketService:
    def __init__(self, gm_profile_id: int):
        self.gm_profile_id = gm_profile_id
        self.regional_markets: Dict[Tuple[str, int], RegionalMarket] = {}  # (region, item_id) -> market
        self.global_markets: Dict[int, GlobalMarket] = {}  # item_id -> market

    def _log_event(self, event_type: str, details: dict):
        """Log a market event."""
        log = SimulationLog(
            event_type=event_type,
            details=details,
            gm_profile_id=self.gm_profile_id
        )
        db.session.add(log)

    def _get_regional_market(self, city: City, item: Item) -> RegionalMarket:
        """Get or create a regional market for a city-item pair."""
        key = (city.region, item.item_id)
        if key not in self.regional_markets:
            market = RegionalMarket.query.filter_by(
                city_id=city.city_id,
                item_id=item.item_id,
                gm_profile_id=self.gm_profile_id
            ).first()
            
            if not market:
                market = RegionalMarket(
                    city_id=city.city_id,
                    item_id=item.item_id,
                    total_supply=0,
                    total_demand=0,
                    average_price=item.base_price,
                    gm_profile_id=self.gm_profile_id
                )
                db.session.add(market)
            
            self.regional_markets[key] = market
        
        return self.regional_markets[key]

    def _get_global_market(self, item: Item) -> GlobalMarket:
        """Get or create a global market for an item."""
        if item.item_id not in self.global_markets:
            market = GlobalMarket.query.filter_by(
                item_id=item.item_id,
                gm_profile_id=self.gm_profile_id
            ).first()
            
            if not market:
                market = GlobalMarket(
                    item_id=item.item_id,
                    total_supply=0,
                    total_demand=0,
                    average_price=item.base_price,
                    gm_profile_id=self.gm_profile_id
                )
                db.session.add(market)
            
            self.global_markets[item.item_id] = market
        
        return self.global_markets[item.item_id]

    def update_regional_supply(self, city: City, item: Item, amount: int):
        """Update the supply of an item in a regional market."""
        market = self._get_regional_market(city, item)
        market.total_supply += amount
        market.last_updated = datetime.utcnow()
        
        # Update average price based on supply
        if market.total_supply > 0:
            market.average_price = item.base_price * (1 - (market.total_supply / 1000))
        
        self._log_event("regional_supply_update", {
            "city": city.name,
            "region": city.region,
            "item": item.name,
            "amount": amount,
            "new_supply": market.total_supply,
            "new_price": market.average_price
        })

    def update_regional_demand(self, city: City, item: Item, amount: int):
        """Update the demand for an item in a regional market."""
        market = self._get_regional_market(city, item)
        market.total_demand += amount
        market.last_updated = datetime.utcnow()
        
        # Update average price based on demand
        if market.total_demand > 0:
            market.average_price = item.base_price * (1 + (market.total_demand / 1000))
        
        self._log_event("regional_demand_update", {
            "city": city.name,
            "region": city.region,
            "item": item.name,
            "amount": amount,
            "new_demand": market.total_demand,
            "new_price": market.average_price
        })

    def update_global_supply(self, item: Item, amount: int):
        """Update the global supply of an item."""
        market = self._get_global_market(item)
        market.total_supply += amount
        market.last_updated = datetime.utcnow()
        
        # Update average price based on supply
        if market.total_supply > 0:
            market.average_price = item.base_price * (1 - (market.total_supply / 5000))
        
        self._log_event("global_supply_update", {
            "item": item.name,
            "amount": amount,
            "new_supply": market.total_supply,
            "new_price": market.average_price
        })

    def update_global_demand(self, item: Item, amount: int):
        """Update the global demand for an item."""
        market = self._get_global_market(item)
        market.total_demand += amount
        market.last_updated = datetime.utcnow()
        
        # Update average price based on demand
        if market.total_demand > 0:
            market.average_price = item.base_price * (1 + (market.total_demand / 5000))
        
        self._log_event("global_demand_update", {
            "item": item.name,
            "amount": amount,
            "new_demand": market.total_demand,
            "new_price": market.average_price
        })

    def get_item_price(self, shop: Shop, item: Item, city: City) -> float:
        """Get the price for an item in a shop, considering both regional and global markets."""
        regional_market = self._get_regional_market(city, item)
        global_market = self._get_global_market(item)
        
        # Get inventory preferences
        inventory = ShopInventory.query.filter_by(
            shop_id=shop.shop_id,
            item_id=item.item_id
        ).first()
        
        if not inventory:
            return item.base_price
        
        # Calculate weighted price based on sourcing preference
        if inventory.sourcing_preference == "regional":
            return regional_market.average_price
        elif inventory.sourcing_preference == "global":
            return global_market.average_price
        else:  # hybrid
            return (regional_market.average_price * 0.7 + global_market.average_price * 0.3)

    def find_item_sources(self, shop: Shop, item: Item, amount: int) -> List[Tuple[Shop, int]]:
        """Find sources for an item, prioritizing regional sources."""
        sources = []
        remaining_amount = amount
        
        # First try regional sources
        if shop.cities:
            city = shop.cities[0]  # Get the shop's primary city
            regional_shops = Shop.query.join(Shop.cities).filter(
                City.region == city.region,
                Shop.shop_id != shop.shop_id,
                Shop.gm_profile_id == self.gm_profile_id
            ).all()
            
            for source_shop in regional_shops:
                inventory = ShopInventory.query.filter_by(
                    shop_id=source_shop.shop_id,
                    item_id=item.item_id
                ).first()
                
                if inventory and inventory.stock > 0:
                    available = min(inventory.stock, remaining_amount)
                    sources.append((source_shop, available))
                    remaining_amount -= available
                    
                    if remaining_amount <= 0:
                        break
        
        # If still needed, try global sources
        if remaining_amount > 0:
            global_shops = Shop.query.filter(
                Shop.shop_id != shop.shop_id,
                Shop.gm_profile_id == self.gm_profile_id
            ).all()
            
            for source_shop in global_shops:
                inventory = ShopInventory.query.filter_by(
                    shop_id=source_shop.shop_id,
                    item_id=item.item_id
                ).first()
                
                if inventory and inventory.stock > 0:
                    available = min(inventory.stock, remaining_amount)
                    sources.append((source_shop, available))
                    remaining_amount -= available
                    
                    if remaining_amount <= 0:
                        break
        
        return sources

    def process_transaction(self, source_shop: Shop, target_shop: Shop, item: Item, amount: int):
        """Process a transaction between shops."""
        source_inventory = ShopInventory.query.filter_by(
            shop_id=source_shop.shop_id,
            item_id=item.item_id
        ).first()
        
        target_inventory = ShopInventory.query.filter_by(
            shop_id=target_shop.shop_id,
            item_id=item.item_id
        ).first()
        
        if not source_inventory or source_inventory.stock < amount:
            raise ValueError(f"Insufficient stock in source shop {source_shop.name}")
        
        # Update source inventory
        source_inventory.stock -= amount
        
        # Update or create target inventory
        if not target_inventory:
            target_inventory = ShopInventory(
                shop_id=target_shop.shop_id,
                item_id=item.item_id,
                stock=amount,
                dynamic_price=self.get_item_price(target_shop, item, target_shop.cities[0])
            )
            db.session.add(target_inventory)
        else:
            target_inventory.stock += amount
            target_inventory.dynamic_price = self.get_item_price(target_shop, item, target_shop.cities[0])
        
        # Update market states
        if source_shop.cities and target_shop.cities:
            source_city = source_shop.cities[0]
            target_city = target_shop.cities[0]
            
            if source_city.region == target_city.region:
                self.update_regional_supply(source_city, item, -amount)
                self.update_regional_demand(target_city, item, amount)
            else:
                self.update_regional_supply(source_city, item, -amount)
                self.update_regional_demand(target_city, item, amount)
                self.update_global_supply(item, -amount)
                self.update_global_demand(item, amount)
        
        self._log_event("shop_transaction", {
            "source_shop": source_shop.name,
            "target_shop": target_shop.name,
            "item": item.name,
            "amount": amount,
            "price": target_inventory.dynamic_price
        }) 