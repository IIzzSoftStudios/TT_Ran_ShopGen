from sqlalchemy.orm import relationship
from app.extensions import db
import json

# Junction table for the many-to-many relationship between Shop and City
shop_cities = db.Table(
    "shop_cities",
    db.Column("shop_id", db.Integer, db.ForeignKey("shops.shop_id"), primary_key=True),
    db.Column("city_id", db.Integer, db.ForeignKey("cities.city_id"), primary_key=True),
)

class City(db.Model):
    __tablename__ = "cities"
    city_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    size = db.Column(db.String(50))
    population = db.Column(db.Integer)
    region = db.Column(db.String(100), index=True)
    gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False)

    # Many-to-Many relationship with Shop
    shops = db.relationship("Shop", secondary=shop_cities, back_populates="cities")
    # One-to-Many relationship with RegionalMarket (Defined in market.py)
    regional_market = db.relationship("RegionalMarket", back_populates="city")
    # Relationship back to GMProfile
    gm_profile = db.relationship("GMProfile", back_populates="cities")
    # Relationship to MarketEvent (Defined in economy.py) - Commented out until implemented
    # market_events = db.relationship("MarketEvent", back_populates="city")
    # Relationship to ResourceNode (Defined in production.py) - Commented out until implemented
    # resource_nodes = db.relationship("ResourceNode", back_populates="city")

    def __repr__(self):
        return f"<City {self.name} (Size: {self.size}, Population: {self.population}, Region: {self.region})>"

class Shop(db.Model):
    __tablename__ = "shops"
    shop_id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False)
    preferred_region = db.Column(db.String(100), nullable=True)  # Preferred region for sourcing

    # Many-to-Many relationship with City
    cities = db.relationship("City", secondary=shop_cities, back_populates="shops")
    # Many-to-Many relationship with Item through ShopInventory
    inventory = db.relationship("ShopInventory", back_populates="shop")
    # Relationship to PlayerInvestment (Defined in economy.py) - Commented out until implemented
    # investments = db.relationship("PlayerInvestment", back_populates="shop")
    # Relationship to ShopMaintenance (Defined in economy.py) - Commented out until implemented
    # maintenance = db.relationship("ShopMaintenance", back_populates="shop")
    # Relationship back to GMProfile
    gm_profile = db.relationship("GMProfile", back_populates="shops")

    def __repr__(self):
        return f"<Shop {self.name} (Type: {self.type})>"

class Item(db.Model):
    __tablename__ = "items"
    item_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    type = db.Column(db.String(50), nullable=False)
    rarity = db.Column(db.String(50), nullable=False)
    base_price = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text)
    range = db.Column(db.String(50))
    damage = db.Column(db.String(100))
    rate_of_fire = db.Column(db.Integer)
    min_str = db.Column(db.String(10))
    notes = db.Column(db.Text)
    gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False)
    preferred_regions = db.Column(db.JSON, nullable=True)  # List of regions where this item is commonly produced
    
    # New universal fields for system-agnostic item properties
    weight = db.Column(db.Float, nullable=True)  # Universal stat for carrying capacity
    is_magic = db.Column(db.Boolean, default=False, nullable=False)  # Universal flag for magical/mundane
    properties_json = db.Column(db.Text, nullable=True)  # Stores all system-specific, type-specific attributes as JSON

    # Many-to-Many relationship with Shop through ShopInventory
    inventory = db.relationship("ShopInventory", back_populates="item")
    # One-to-Many relationship with RegionalMarket (Defined in market.py)
    regional_market = db.relationship("RegionalMarket", back_populates="item")
    # One-to-Many relationship with GlobalMarket (Defined in market.py)
    global_market = db.relationship("GlobalMarket", back_populates="item")
    # Relationship to PlayerInventory (Defined in users.py)
    player_inventories = db.relationship("PlayerInventory", back_populates="item") # Renamed to avoid conflict
    # Relationship to ResourceNode (Defined in production.py) - Commented out until implemented
    # resource_nodes = db.relationship("ResourceNode", back_populates="item")
    # Relationship to ResourceTransform (Input) (Defined in production.py) - Commented out until implemented
    # input_transforms = db.relationship("ResourceTransform", foreign_keys="ResourceTransform.input_item_id", back_populates="input_item")
    # Relationship to ResourceTransform (Output) (Defined in production.py) - Commented out until implemented
    # output_transforms = db.relationship("ResourceTransform", foreign_keys="ResourceTransform.output_item_id", back_populates="output_item")
    # Relationship back to GMProfile
    gm_profile = db.relationship("GMProfile", back_populates="items")

    def __repr__(self):
        return f"<Item {self.name} (Type: {self.type}, Rarity: {self.rarity}, Price: {self.base_price})>"
    
    def to_dict(self, include_shop_data=False):
        """
        Serialize Item to dictionary format.
        
        Args:
            include_shop_data (bool): If True, includes shop_inventory data for the first shop
                                     that has this item in stock.
        
        Returns:
            dict: Dictionary containing all universal attributes, parsed properties_json as 'properties',
                  and optionally shop_inventory data.
        """
        # Build base dictionary with universal attributes
        result = {
            "item_id": self.item_id,
            "name": self.name,
            "type": self.type,
            "rarity": self.rarity,
            "base_price": float(self.base_price),
            "description": self.description,
            "weight": float(self.weight) if self.weight is not None else None,
            "is_magic": bool(self.is_magic) if self.is_magic is not None else False,
        }
        
        # Parse properties_json and include as 'properties'
        properties = {}
        if self.properties_json:
            try:
                properties = json.loads(self.properties_json)
            except (json.JSONDecodeError, TypeError):
                # If JSON is invalid, return empty dict
                properties = {}
        result["properties"] = properties
        
        # Conditionally include shop_inventory data
        if include_shop_data:
            # Get the first ShopInventory entry for this item
            shop_inventory = self.inventory[0] if self.inventory else None
            if shop_inventory:
                result["shop_inventory"] = {
                    "shop_id": shop_inventory.shop_id,
                    "stock": shop_inventory.stock,
                    "dynamic_price": float(shop_inventory.dynamic_price)
                }
        
        return result

class ShopInventory(db.Model):
    __tablename__ = "shop_inventory"
    inventory_id = db.Column(db.Integer, primary_key=True)

    # Foreign keys linking Shop and Item
    shop_id = db.Column(db.Integer, db.ForeignKey("shops.shop_id"), nullable=True)
    item_id = db.Column(db.Integer, db.ForeignKey("items.item_id"), nullable=True)

    # Shop-specific attributes for the item
    stock = db.Column(db.Integer, default=0)
    dynamic_price = db.Column(db.Float, nullable=False)
    sourcing_preference = db.Column(db.Enum("regional", "global", "hybrid", name="sourcing_preference"), default="hybrid")

    # Relationships for accessing item and shop details
    shop = db.relationship("Shop", back_populates="inventory")
    item = db.relationship("Item", back_populates="inventory")

    def __repr__(self):
        # Ensure shop and item exist before accessing name
        shop_name = self.shop.name if self.shop else "N/A"
        item_name = self.item.name if self.item else "N/A"
        return f"<ShopInventory (Shop: {shop_name}, Item: {item_name}, Stock: {self.stock}, Price: {self.dynamic_price})>"
