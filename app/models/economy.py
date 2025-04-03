from sqlalchemy.orm import relationship
from app.extensions import db
from datetime import datetime

# Use try-except for potential circular imports during initialization
try:
    from .backend import City, Shop
    from .users import Player, GMProfile
except ImportError:
    City, Shop = None, None
    Player, GMProfile = None, None

class MarketEvent(db.Model):
    __tablename__ = "market_events"
    event_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    trigger_type = db.Column(db.String(50), nullable=False)  # date_based, player_action, random_roll, faction_state
    city_id = db.Column(db.Integer, db.ForeignKey("cities.city_id"), nullable=True)
    region = db.Column(db.String(100), nullable=True)
    effect_json = db.Column(db.JSON, nullable=False)
    start_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow) # Added default
    end_date = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False)
    
    # Relationships
    city = db.relationship("City", back_populates="market_events")
    # No direct GM relationship needed?
    # gm_profile = db.relationship("GMProfile", back_populates="market_events")

    def __repr__(self):
        return f"<MarketEvent {self.name} (Trigger: {self.trigger_type})>"

class PlayerInvestment(db.Model):
    __tablename__ = "player_investments"
    investment_id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=False)
    shop_id = db.Column(db.Integer, db.ForeignKey("shops.shop_id"), nullable=False)
    amount_invested = db.Column(db.Float, nullable=False)
    stake_percentage = db.Column(db.Float, nullable=False)
    income_yield = db.Column(db.Float, nullable=False)
    last_payout = db.Column(db.DateTime, nullable=False, default=datetime.utcnow) # Added default
    gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False)
    
    # Relationships
    player = db.relationship("Player", back_populates="investments")
    shop = db.relationship("Shop", back_populates="investments")
    # No direct GM relationship needed?
    # gm_profile = db.relationship("GMProfile", back_populates="player_investments")

    def __repr__(self):
        player_name = self.player.player_user.username if self.player and self.player.player_user else "N/A"
        shop_name = self.shop.name if self.shop else "N/A"
        return f"<PlayerInvestment (Player: {player_name}, Shop: {shop_name}, Amount: {self.amount_invested})>"

class ShopMaintenance(db.Model):
    __tablename__ = "shop_maintenance"
    maintenance_id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey("shops.shop_id"), nullable=False)
    daily_cost = db.Column(db.Float, nullable=False)
    last_payment = db.Column(db.DateTime, nullable=False, default=datetime.utcnow) # Added default
    gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False)
    
    # Relationships
    shop = db.relationship("Shop", back_populates="maintenance")
    # No direct GM relationship needed?
    # gm_profile = db.relationship("GMProfile", back_populates="shop_maintenances")

    def __repr__(self):
        shop_name = self.shop.name if self.shop else "N/A"
        return f"<ShopMaintenance (Shop: {shop_name}, Cost: {self.daily_cost})>"
