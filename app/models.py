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

    def __repr__(self):
        return f"<City {self.name} (Size: {self.size}, Population: {self.population}, Region: {self.region})>"

class Shop(db.Model):
    __tablename__ = "shops"
    shop_id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False)

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

    # Many-to-Many relationship with Shop through ShopInventory
    inventory = db.relationship("ShopInventory", back_populates="item")

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

    # Relationships for accessing item and shop details
    shop = db.relationship("Shop", back_populates="inventory")
    item = db.relationship("Item", back_populates="inventory")

    def __repr__(self):
        return f"<ShopInventory (Shop: {self.shop.name}, Item: {self.item.name}, Stock: {self.stock}, Price: {self.dynamic_price})>"

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
    username = db.Column(db.String(100), nullable=False, unique=True)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(50), nullable=False)
    
    # For GMs: Their players
    players = db.relationship("Player", backref="user", foreign_keys="Player.user_id")
    # GM Profile if they are a GM
    gm_profile = db.relationship("GMProfile", backref="user", uselist=False)

    def set_password(self, password):
        self.password = bcrypt.generate_password_hash(password).decode("utf-8") 

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password, password)
    
    def get_id(self):
        return str(self.id)

    @property
    def is_active(self):
        return True

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

    def __repr__(self):
        return f"<Player (User: {self.user.username}, GM: {self.gm_profile.user.username})>"
