from sqlalchemy.orm import relationship
from app.extensions import db
from datetime import datetime

class RegionalMarket(db.Model):
    """Tracks supply and demand for items within a region (linked to a City)."""
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
    # No direct GMProfile relationship here, accessed via city or item

    def __repr__(self):
        city_name = self.city.name if self.city else "N/A"
        item_name = self.item.name if self.item else "N/A"
        return f"<RegionalMarket (City: {city_name}, Item: {item_name}, Supply: {self.total_supply}, Demand: {self.total_demand})>"

class GlobalMarket(db.Model):
    """Tracks global supply and demand for items."""
    __tablename__ = "global_markets"
    
    market_id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("items.item_id"), nullable=False, unique=True) # Should be unique per item
    total_supply = db.Column(db.Integer, default=0)
    total_demand = db.Column(db.Integer, default=0)
    average_price = db.Column(db.Float, nullable=False)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False) # Assuming GM owns global market entries too?

    # Relationships
    item = db.relationship("Item", back_populates="global_market")
    # No direct GMProfile relationship here, accessed via item

    def __repr__(self):
        item_name = self.item.name if self.item else "N/A"
        return f"<GlobalMarket (Item: {item_name}, Supply: {self.total_supply}, Demand: {self.total_demand})>"

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

    # Relationship back to GMProfile
    gm_profile = db.relationship("GMProfile", back_populates="demand_modifiers")
    # Relationship to targets
    targets = db.relationship("ModifierTarget", back_populates="modifier")

    def is_currently_active(self):
        """Checks if the modifier is active and within its time range."""
        if not self.is_active:
            return False
        now = datetime.utcnow()
        if self.start_date and now < self.start_date:
             return False
        if self.end_date and now > self.end_date:
            return False
        return True

    @staticmethod
    def get_active_modifiers(gm_profile_id):
        """Fetches all currently active modifiers for a specific GM."""
        now = datetime.utcnow()
        return DemandModifier.query.filter(
            DemandModifier.gm_profile_id == gm_profile_id,
            DemandModifier.is_active == True,
            (DemandModifier.start_date == None) | (DemandModifier.start_date <= now),
            (DemandModifier.end_date == None) | (DemandModifier.end_date >= now)
        ).all()

    def __repr__(self):
        return f"<DemandModifier {self.name} (Scope: {self.scope}, Effect: {self.effect_value})>"

class ModifierTarget(db.Model):
    __tablename__ = "modifier_targets"

    id = db.Column(db.Integer, primary_key=True)
    modifier_id = db.Column(db.Integer, db.ForeignKey("demand_modifiers.id"), nullable=False)
    entity_type = db.Column(db.Enum("region", "city", "shop", "item", name="target_type"), nullable=False)
    # Consider using String for entity_id if region names are used, or keep Integer if IDs are used for everything
    entity_id = db.Column(db.Integer, nullable=False)  # The ID or potentially name of the affected entity
    gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False)

    modifier = db.relationship("DemandModifier", back_populates="targets")
    # Relationship back to GMProfile
    gm_profile = db.relationship("GMProfile", back_populates="modifier_targets")

    def __repr__(self):
        return f"<ModifierTarget (Modifier: {self.modifier.name if self.modifier else 'N/A'}, Type: {self.entity_type}, Entity ID: {self.entity_id})>"
