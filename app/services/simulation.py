import random
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from app.extensions import db
from app.models.backend import Shop, ShopInventory, City
from app.services.economy import calculate_dynamic_price
from app.config.simulation_config import SimulationConfig, default_config

class SimulationEngine:
    """Handles the simulation of the game economy."""
    
    _instance = None
    
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
        valid_speeds = ["pause", "1x", "5x", "100x", "1000x"]
        if speed not in valid_speeds:
            raise ValueError(f"Invalid speed: {speed}. Must be one of {valid_speeds}")
        old_speed = self.current_speed
        self.current_speed = speed
        self._log_tick(f"Speed changed from {old_speed} to {speed}")
        self._debug_state()
        
    def get_speed_multiplier(self) -> int:
        """Get the time multiplier for the current speed setting."""
        if self.current_speed == "pause":
            return 0
        elif self.current_speed == "1x":
            return 1  # 1 second = 1 second
        elif self.current_speed == "5x":
            return 5  # 1 second = 5 seconds
        elif self.current_speed == "100x":
            return 100  # 1 second = 100 seconds
        elif self.current_speed == "1000x":
            return 1000  # 1 second = 1000 seconds
        return 0
        
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
        
    def run_tick(self, gm_profile_id: int) -> Dict:
        """
        Execute one simulation tick.
        Args:
            gm_profile_id: The ID of the GM whose shops should be updated
        Returns a dictionary containing tick results and statistics.
        """
        tick_start = datetime.now()
        stats = {
            'shops_updated': 0,
            'items_updated': 0,
            'price_changes': [],
            'tick_duration': 0
        }
        
        try:
            self._log_tick("Starting simulation tick", "debug")
            
            # Get only shops belonging to the current GM
            shops = Shop.query.filter_by(gm_profile_id=gm_profile_id).all()
            self._log_tick(f"Found {len(shops)} shops to update", "debug")
            
            for shop in shops:
                # Get all cities this shop operates in
                cities = City.query.join(Shop.cities).filter(Shop.shop_id == shop.shop_id).all()
                
                # Get all inventory items for this shop
                inventory_items = ShopInventory.query.filter_by(shop_id=shop.shop_id).all()
                
                for item in inventory_items:
                    # For each city the shop operates in, calculate the price
                    for city in cities:
                        # Get the item's base price and rarity
                        base_price = item.item.base_price
                        rarity = int(item.item.rarity) if item.item.rarity.isdigit() else 5
                        
                        # Calculate new price based on cities and other factors
                        new_price = calculate_dynamic_price(
                            base_price=base_price,
                            rarity=rarity,
                            stock_level=item.stock,
                            shop_id=shop.shop_id,
                            city_id=city.city_id
                        )
                        item.dynamic_price = new_price
                        stats['items_updated'] += 1
                        stats['price_changes'].append({
                            'item_id': item.item_id,
                            'city_id': city.city_id,
                            'old_price': item.dynamic_price,
                            'new_price': new_price
                        })
                
                stats['shops_updated'] += 1
            
            # Commit all changes
            db.session.commit()
            
            # Update last tick time
            self.last_tick_time = datetime.now()
            
            # Calculate tick duration
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
        Run multiple ticks to simulate a specific time period.
        Args:
            gm_profile_id: The ID of the GM whose shops should be updated
            time_period: One of "hour", "day", "week", "month"
        Returns a dictionary containing simulation results and statistics.
        """
        # Map time periods to number of ticks
        ticks_per_period = {
            "hour": 1,
            "day": 24,
            "week": 168,
            "month": 720  # Assuming 30 days
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
                tick_stats = self.run_tick(gm_profile_id)
                total_stats['shops_updated'] += tick_stats['shops_updated']
                total_stats['items_updated'] += tick_stats['items_updated']
                total_stats['price_changes'].extend(tick_stats['price_changes'])
                total_stats['total_duration'] += tick_stats['tick_duration']
                total_stats['ticks_completed'] += 1
            except Exception as e:
                self._log_tick(f"Error during tick {i+1}/{total_ticks}: {str(e)}", "error")
                break
                
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