from sqlalchemy.orm import relationship
from app.extensions import db, SQLAlchemy, bcrypt, UserMixin
from datetime import datetime

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
    # One-to-Many relationship with RegionalMarket
    regional_market = db.relationship("RegionalMarket", back_populates="city")

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

    # Many-to-Many relationship with Shop through ShopInventory
    inventory = db.relationship("ShopInventory", back_populates="item")
    # One-to-Many relationship with RegionalMarket
    regional_market = db.relationship("RegionalMarket", back_populates="item")
    # One-to-Many relationship with GlobalMarket
    global_market = db.relationship("GlobalMarket", back_populates="item")

    def __repr__(self):
        return f"<Item {self.name} (Type: {self.type}, Rarity: {self.rarity}, Price: {self.base_price})>"

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
        return f"<ShopInventory (Shop: {self.shop.name}, Item: {self.item.name}, Stock: {self.stock}, Price: {self.dynamic_price})>"

class RegionalMarket(db.Model):
    """Tracks supply and demand for items within a region."""
    __tablename__ = "regional_markets"
    
    market_id = db.Column(db.Integer, primary_key=True)
    city_id = db.Column(db.Integer, db.ForeignKey("cities.city_id"), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey("items.item_id"), nullable=False)
    total_supply = db.Column(db.Integer, default=0)
    total_demand = db.Column(db.Integer, default=0)
    average_price = db.Column(db.Float, nullable=False)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False)

    # Relationships
    city = db.relationship("City", back_populates="regional_market")
    item = db.relationship("Item", back_populates="regional_market")

    def __repr__(self):
        return f"<RegionalMarket (City: {self.city.name}, Item: {self.item.name}, Supply: {self.total_supply}, Demand: {self.total_demand})>"

class GlobalMarket(db.Model):
    """Tracks global supply and demand for items."""
    __tablename__ = "global_markets"
    
    market_id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("items.item_id"), nullable=False)
    total_supply = db.Column(db.Integer, default=0)
    total_demand = db.Column(db.Integer, default=0)
    average_price = db.Column(db.Float, nullable=False)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False)

    # Relationships
    item = db.relationship("Item", back_populates="global_market")

    def __repr__(self):
        return f"<GlobalMarket (Item: {self.item.name}, Supply: {self.total_supply}, Demand: {self.total_demand})>"

#Demand Modifier Models
class DemandModifier(db.Model):
    __tablename__ = "demand_modifiers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    scope = db.Column(db.Enum("global", "regional", "city", "shop", "item", name="modifier_scope"), nullable=False)
    effect_value = db.Column(db.Float, nullable=False, default=1.0)
    start_date = db.Column(db.DateTime, nullable=True, default=datetime.utcnow)
    end_date = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False)

    def is_currently_active(self):
        """Checks if the modifier is active and within its time range."""
        if not self.is_active:
            return False
        if self.end_date and datetime.utcnow() > self.end_date:
            return False
        return True

    @staticmethod
    def get_active_modifiers():
        """Fetches all currently active modifiers."""
        return DemandModifier.query.filter_by(is_active=True).all()

class ModifierTarget(db.Model):
    __tablename__ = "modifier_targets"

    id = db.Column(db.Integer, primary_key=True)
    modifier_id = db.Column(db.Integer, db.ForeignKey("demand_modifiers.id"), nullable=False)
    entity_type = db.Column(db.Enum("region", "city", "shop", "item", name="target_type"), nullable=False)
    entity_id = db.Column(db.Integer, nullable=False)  # The ID of the affected entity
    gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False)

    modifier = db.relationship("DemandModifier", backref="targets")

    def __repr__(self):
        return f"<ModifierTarget (Type: {self.entity_type}, Entity ID: {self.entity_id})>"

class User(db.Model, UserMixin):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    last_active = db.Column(db.DateTime, default=datetime.utcnow)
    
    # For GMs: Their players
    players = db.relationship("Player", backref="user", foreign_keys="Player.user_id")
    # GM Profile if they are a GM
    gm_profile = db.relationship("GMProfile", backref="user", uselist=False)

    def set_password(self, password):
        """Set the user's password"""
        self.password = bcrypt.generate_password_hash(password).decode('utf-8')
        
    def check_password(self, password):
        """Check if the provided password matches"""
        return bcrypt.check_password_hash(self.password, password)
        
    def update_activity(self):
        """Update the user's last active timestamp"""
        self.last_active = datetime.utcnow()
        db.session.commit()
        
    @property
    def is_active(self):
        """Check if the user is currently active (active in last 5 minutes)"""
        if not self.last_active:
            return False
        return (datetime.utcnow() - self.last_active).total_seconds() < 300  # 5 minutes

class GMProfile(db.Model):
    __tablename__ = "gm_profile"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, unique=True)
    
    # Relationships with game entities
    cities = db.relationship("City", backref="gm_profile")
    shops = db.relationship("Shop", backref="gm_profile")
    items = db.relationship("Item", backref="gm_profile")
    demand_modifiers = db.relationship("DemandModifier", backref="gm_profile")
    modifier_targets = db.relationship("ModifierTarget", backref="gm_profile")
    # Players managed by this GM
    players = db.relationship("Player", backref="gm_profile")

    def __repr__(self):
        return f"<GMProfile (User: {self.user.username})>"

class Player(db.Model):
    __tablename__ = "player"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, unique=True)
    gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False)
    currency = db.Column(db.Integer, default=0)
    
    # Relationship to player's inventory
    inventory = db.relationship("PlayerInventory", back_populates="player")

    def __repr__(self):
        return f"<Player (User: {self.user.username}, GM: {self.gm_profile.user.username})>"

class PlayerInventory(db.Model):
    __tablename__ = "player_inventory"
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey("items.item_id"), nullable=False)
    quantity = db.Column(db.Integer, default=1)

    # Relationships
    player = db.relationship("Player", back_populates="inventory")
    item = db.relationship("Item")

    def __repr__(self):
        return f"<PlayerInventory (Player: {self.player.user.username}, Item: {self.item.name}, Quantity: {self.quantity})>"

# class ResourceNode(db.Model):
#     __tablename__ = "resource_nodes"
#     node_id = db.Column(db.Integer, primary_key=True)
#     name = db.Column(db.String(100), nullable=False)
#     type = db.Column(db.String(50), nullable=False)  # mine, farm, forest, etc.
#     production_rate = db.Column(db.Float, nullable=False)  # units per day
#     quality = db.Column(db.Float, nullable=False)  # 0.0 to 1.0
#     city_id = db.Column(db.Integer, db.ForeignKey("cities.city_id"), nullable=False)
#     owner_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=True)  # Can be owned by players
#     gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False)
    
#     # Add relationship to Item
#     item_id = db.Column(db.Integer, db.ForeignKey("items.item_id"))
#     item = db.relationship("Item", backref="resource_nodes")
    
#     # Relationships
#     city = db.relationship("City", backref="resource_nodes")
#     owner = db.relationship("Player", backref="owned_resources")
#     production_history = db.relationship("ProductionHistory", back_populates="resource_node")

#     def __repr__(self):
#         return f"<ResourceNode {self.name} (Type: {self.type}, Rate: {self.production_rate})>"

# class ProductionHistory(db.Model):
#     __tablename__ = "production_history"
#     history_id = db.Column(db.Integer, primary_key=True)
#     node_id = db.Column(db.Integer, db.ForeignKey("resource_nodes.node_id"), nullable=False)
#     date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
#     amount_produced = db.Column(db.Float, nullable=False)
#     quality = db.Column(db.Float, nullable=False)
    
#     # Relationships
#     resource_node = db.relationship("ResourceNode", back_populates="production_history")

# class ResourceTransform(db.Model):
#     __tablename__ = "resource_transforms"
#     transform_id = db.Column(db.Integer, primary_key=True)
#     input_item_id = db.Column(db.Integer, db.ForeignKey("items.item_id"), nullable=False)
#     output_item_id = db.Column(db.Integer, db.ForeignKey("items.item_id"), nullable=False)
#     conversion_rate = db.Column(db.Float, nullable=False)  # How many output items per input item
#     shop_type = db.Column(db.String(100), nullable=False)  # Type of shop that can perform this transform
#     gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False)
    
#     # Relationships
#     input_item = db.relationship("Item", foreign_keys=[input_item_id])
#     output_item = db.relationship("Item", foreign_keys=[output_item_id])

# class MarketEvent(db.Model):
#     __tablename__ = "market_events"
#     event_id = db.Column(db.Integer, primary_key=True)
#     name = db.Column(db.String(100), nullable=False)
#     description = db.Column(db.Text)
#     trigger_type = db.Column(db.String(50), nullable=False)  # date_based, player_action, random_roll, faction_state
#     city_id = db.Column(db.Integer, db.ForeignKey("cities.city_id"), nullable=True)
#     region = db.Column(db.String(100), nullable=True)
#     effect_json = db.Column(db.JSON, nullable=False)
#     start_date = db.Column(db.DateTime, nullable=False)
#     end_date = db.Column(db.DateTime, nullable=True)
#     is_active = db.Column(db.Boolean, default=True)
#     gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False)
    
#     # Relationships
#     city = db.relationship("City", backref="market_events")

# class PlayerInvestment(db.Model):
#     __tablename__ = "player_investments"
#     investment_id = db.Column(db.Integer, primary_key=True)
#     player_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=False)
#     shop_id = db.Column(db.Integer, db.ForeignKey("shops.shop_id"), nullable=False)
#     amount_invested = db.Column(db.Float, nullable=False)
#     stake_percentage = db.Column(db.Float, nullable=False)
#     income_yield = db.Column(db.Float, nullable=False)
#     last_payout = db.Column(db.DateTime, nullable=False)
#     gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False)
    
#     # Relationships
#     player = db.relationship("Player", backref="investments")
#     shop = db.relationship("Shop", backref="investments")

# class ShopMaintenance(db.Model):
#     __tablename__ = "shop_maintenance"
#     maintenance_id = db.Column(db.Integer, primary_key=True)
#     shop_id = db.Column(db.Integer, db.ForeignKey("shops.shop_id"), nullable=False)
#     daily_cost = db.Column(db.Float, nullable=False)
#     last_payment = db.Column(db.DateTime, nullable=False)
#     gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False)
    
#     # Relationships
#     shop = db.relationship("Shop", backref="maintenance")