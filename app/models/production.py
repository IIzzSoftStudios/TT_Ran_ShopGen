from sqlalchemy.orm import relationship
from app.extensions import db
from datetime import datetime

# Use try-except for potential circular imports during initialization
try:
    from .backend import City, Item
    from .users import Player, GMProfile
except ImportError:
    City, Item = None, None
    Player, GMProfile = None, None

class ResourceNode(db.Model):
    __tablename__ = "resource_nodes"
    node_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(50), nullable=False)  # mine, farm, forest, etc.
    production_rate = db.Column(db.Float, nullable=False)  # units per day
    quality = db.Column(db.Float, nullable=False)  # 0.0 to 1.0
    city_id = db.Column(db.Integer, db.ForeignKey("cities.city_id"), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=True)  # Can be owned by players
    gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey("items.item_id")) # What item does this node produce?
    
    # Relationships
    city = db.relationship("City", back_populates="resource_nodes")
    owner = db.relationship("Player", back_populates="owned_resources")
    item = db.relationship("Item", back_populates="resource_nodes")
    production_history = db.relationship("ProductionHistory", back_populates="resource_node")
    # No direct GM relationship needed if accessed via city/item/owner?
    # gm_profile = db.relationship("GMProfile", back_populates="resource_nodes") 

    def __repr__(self):
        return f"<ResourceNode {self.name} (Type: {self.type}, Rate: {self.production_rate})>"

class ProductionHistory(db.Model):
    __tablename__ = "production_history"
    history_id = db.Column(db.Integer, primary_key=True)
    node_id = db.Column(db.Integer, db.ForeignKey("resource_nodes.node_id"), nullable=False)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    amount_produced = db.Column(db.Float, nullable=False)
    quality = db.Column(db.Float, nullable=False)
    
    # Relationships
    resource_node = db.relationship("ResourceNode", back_populates="production_history")

    def __repr__(self):
        return f"<ProductionHistory (Node: {self.node_id}, Date: {self.date}, Amount: {self.amount_produced})>"

class ResourceTransform(db.Model):
    __tablename__ = "resource_transforms"
    transform_id = db.Column(db.Integer, primary_key=True)
    input_item_id = db.Column(db.Integer, db.ForeignKey("items.item_id"), nullable=False)
    output_item_id = db.Column(db.Integer, db.ForeignKey("items.item_id"), nullable=False)
    conversion_rate = db.Column(db.Float, nullable=False)  # How many output items per input item
    shop_type = db.Column(db.String(100), nullable=False)  # Type of shop that can perform this transform
    gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False)
    
    # Relationships
    input_item = db.relationship("Item", foreign_keys=[input_item_id], back_populates="input_transforms")
    output_item = db.relationship("Item", foreign_keys=[output_item_id], back_populates="output_transforms")
    # No direct GM relationship needed?
    # gm_profile = db.relationship("GMProfile", back_populates="resource_transforms")

    def __repr__(self):
        input_name = self.input_item.name if self.input_item else "N/A"
        output_name = self.output_item.name if self.output_item else "N/A"
        return f"<ResourceTransform (Input: {input_name}, Output: {output_name}, Rate: {self.conversion_rate})>"
