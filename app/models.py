from sqlalchemy.orm import relationship, foreign
from app.extensions import db


class City(db.Model):
    __tablename__ = "cities"
    city_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    size = db.Column(db.String(50))
    population = db.Column(db.Integer)
    region = db.Column(db.String(100), index=True)

    def __repr__(self):
        return f"<City {self.name} (Size: {self.size}, Population: {self.population}, Region: {self.region})>"

class Shop(db.Model):
    __tablename__ = "shops"
    shop_id = db.Column(db.Integer, primary_key=True)
    city_id = db.Column(db.Integer, nullable=True)  # Allow NULL values
    type = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(100), nullable=False)

    # Logical relationship with City
    city = db.relationship(
        "City",
        primaryjoin="and_(City.city_id == foreign(Shop.city_id))",
        viewonly=True,
    )

    def __repr__(self):
        return f"<Shop {self.name} (Type: {self.type})>"

class Item(db.Model):
    __tablename__ = "items"
    item_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    type = db.Column(db.String(50), nullable=False)  # E.g., Weapon, Armor, etc.
    rarity = db.Column(db.String(50), nullable=False)  # E.g., Common, Rare, etc.
    base_price = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text)  # Link or short description
    range = db.Column(db.String(50))  # Whole # / Whole # / Whole #
    damage = db.Column(db.String(100))  # Text + Whole #
    rate_of_fire = db.Column(db.Integer)  # Whole #
    min_str = db.Column(db.String(10))  # Whole # or "N/A"
    notes = db.Column(db.Text)  # Text strings
    shop_id = db.Column(db.Integer)  # This is no longer a ForeignKey

    # Logical relationship with Shop (explicit join condition)
    shop = relationship(
        "Shop",
        primaryjoin="and_(Shop.shop_id == foreign(Item.shop_id))",
        viewonly=True,
    )

    def __repr__(self):
        return f"<Item {self.name} (Type: {self.type}, Rarity: {self.rarity}, Price: {self.base_price})>"

class ShopInventory(db.Model):
    __tablename__ = "shop_inventory"
    inventory_id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey("shops.shop_id"), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey("items.item_id"), nullable=False)
    stock = db.Column(db.Integer, default=0)  # Stock level of the item in the shop

    shop = db.relationship("Shop", backref="inventory")
    item = db.relationship("Item", backref="inventory")

    def __repr__(self):
        return f"<ShopInventory (Shop: {self.shop.name}, Item: {self.item.name}, Stock: {self.stock})>"
