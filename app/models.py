from sqlalchemy.orm import relationship
from sqlalchemy import UniqueConstraint, func, Index
from sqlalchemy.dialects.postgresql import JSONB
from app.extensions import db, SQLAlchemy, bcrypt, UserMixin
from datetime import datetime


def _json_with_jsonb():
    """Return a JSON column type that upgrades to JSONB on PostgreSQL.

    Using a factory so each column gets its own type instance (SQLAlchemy
    requires this for proper reflection).
    """
    return db.JSON().with_variant(JSONB, "postgresql")

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
    government_type = db.Column(db.String(50), nullable=True, index=True)
    size = db.Column(db.String(50))
    population = db.Column(db.Integer)
    region = db.Column(db.String(100), index=True)
    region_id = db.Column(
        db.Integer, db.ForeignKey("region.id", ondelete="SET NULL"), nullable=True, index=True
    )
    gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False)

    # Many-to-Many relationship with Shop
    shops = db.relationship("Shop", secondary=shop_cities, back_populates="cities")
    # One-to-Many relationship with RegionalMarket
    regional_market = db.relationship("RegionalMarket", back_populates="city")
    region_obj = db.relationship("Region", backref=db.backref("cities", lazy="dynamic"))

    def __repr__(self):
        return f"<City {self.name} (Size: {self.size}, Population: {self.population}, Region: {self.region})>"


class Region(db.Model):
    """A campaign-scoped region with per-region axis flavor.

    The fused `tech_magic_balance` axis roll for each region is stored in
    `local_flavor` as `{"axis_position": int}`. Cities read this at
    runtime via `City.region_obj.local_flavor["axis_position"]`.
    """

    __tablename__ = "region"
    __table_args__ = (
        UniqueConstraint("campaign_id", "name", name="uq_region_campaign_name"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    campaign_id = db.Column(
        db.Integer,
        db.ForeignKey("campaign.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    gm_profile_id = db.Column(
        db.Integer, db.ForeignKey("gm_profile.id"), nullable=False, index=True
    )
    local_flavor = db.Column(_json_with_jsonb(), nullable=True)
    created_at = db.Column(db.DateTime, server_default=func.now(), nullable=False)

    campaign = db.relationship(
        "Campaign",
        backref=db.backref(
            "regions", cascade="all, delete-orphan", passive_deletes=True
        ),
    )

    def __repr__(self):
        return f"<Region {self.name} campaign={self.campaign_id}>"

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
    __table_args__ = (
        Index("ix_item_gm_axis", "gm_profile_id", "axis_position"),
    )

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
    # System-specific stat block (D&D 5e / PF2E / generic).
    stats = db.Column(_json_with_jsonb(), nullable=True)
    # Fused-axis position this item was forged for (0=God Magic .. 10=Post-Apoc Tech).
    axis_position = db.Column(db.Integer, nullable=True, index=True)

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


class PriceHistory(db.Model):
    __tablename__ = "price_history"
    # Existing PostgreSQL deployments use PK column name `id`; map Python attr history_id to that column.
    history_id = db.Column("id", db.Integer, primary_key=True, autoincrement=True)
    shop_id = db.Column(db.Integer, db.ForeignKey("shops.shop_id"), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey("items.item_id"), nullable=False)
    price = db.Column(db.Float, nullable=False)
    recorded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False)

    shop = db.relationship("Shop", backref="price_history_entries")
    item = db.relationship("Item", backref="price_history_entries")

    def __repr__(self):
        return f"<PriceHistory shop={self.shop_id} item={self.item_id} price={self.price}>"


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
    def get_active_modifiers(gm_profile_id: int):
        """Fetches active modifiers for one campaign."""
        return DemandModifier.query.filter_by(
            is_active=True, gm_profile_id=gm_profile_id
        ).all()

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
    email = db.Column(db.String(255), nullable=True, unique=True)
    last_active = db.Column(db.DateTime, nullable=True)
    reset_token = db.Column(db.String(100), nullable=True)
    reset_token_expires = db.Column(db.DateTime, nullable=True)
    reset_otp_hash = db.Column(db.String(128), nullable=True)
    reset_otp_expires = db.Column(db.DateTime, nullable=True)

    # For GMs: Their players
    players = db.relationship("Player", backref="user", foreign_keys="Player.user_id")
    # GM Profile if they are a GM
    gm_profile = db.relationship("GMProfile", backref="user", uselist=False)

    def set_password(self, password):
        self.password = bcrypt.generate_password_hash(password).decode("utf-8") 

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password, password)

    def update_activity(self):
        self.last_active = datetime.utcnow()
        db.session.commit()

    def get_id(self):
        return str(self.id)

    @property
    def is_active(self):
        return True

class GMProfile(db.Model):
    __tablename__ = "gm_profile"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, unique=True)
    current_game_day = db.Column(db.Integer, nullable=True, default=1)

    # Relationships with game entities
    cities = db.relationship("City", backref="gm_profile")
    shops = db.relationship("Shop", backref="gm_profile")
    items = db.relationship("Item", backref="gm_profile")
    demand_modifiers = db.relationship("DemandModifier", backref="gm_profile")
    modifier_targets = db.relationship("ModifierTarget", backref="gm_profile")
    # Players managed by this GM
    players = db.relationship("Player", backref="gm_profile")
    campaigns = db.relationship(
        "Campaign", back_populates="gm_profile", cascade="all, delete-orphan"
    )

    @property
    def calendar_state(self):
        """30-day months, 12 months/year (360 days/year); one tick = one game day.

        `month` is kept as a global (non-wrapping) counter for backward compat
        with any existing consumer. `year` and `month_of_year` are the
        year-relative values the UI renders."""
        total_days = self.current_game_day or 1
        month = ((total_days - 1) // 30) + 1
        day_of_month = ((total_days - 1) % 30) + 1
        day_of_week = (total_days - 1) % 7
        year = ((total_days - 1) // 360) + 1
        month_of_year = (((total_days - 1) % 360) // 30) + 1
        return {
            "month": month,
            "month_of_year": month_of_year,
            "year": year,
            "day": day_of_month,
            "dow": day_of_week,
            "total": total_days,
        }

    def __repr__(self):
        return f"<GMProfile (User: {self.user.username})>"


class Campaign(db.Model):
    __tablename__ = "campaign"

    id = db.Column(db.Integer, primary_key=True)
    gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    system_type = db.Column(db.String(50), nullable=False, default="generic")
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_free_tier = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    gm_profile = db.relationship("GMProfile", back_populates="campaigns")
    players = db.relationship(
        "CampaignPlayer", back_populates="campaign", cascade="all, delete-orphan"
    )


class CampaignPlayer(db.Model):
    __tablename__ = "campaign_player"

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaign.id"), nullable=False, index=True)
    player_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="active")
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    campaign = db.relationship("Campaign", back_populates="players")
    player = db.relationship("Player", back_populates="campaign_memberships")

    __table_args__ = (
        db.UniqueConstraint("campaign_id", "player_id", name="uq_campaign_player_membership"),
    )


class AccessRequest(db.Model):
    __tablename__ = "access_requests"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, index=True)
    user_role = db.Column(db.String(50), nullable=False)
    player_count = db.Column(db.Integer, default=0)
    total_expected_users = db.Column(db.Integer, default=1)
    is_homebrew = db.Column(db.Boolean, default=False)
    primary_ruleset = db.Column(db.String(100))
    discovery_source = db.Column(db.String(255))
    notes = db.Column(db.Text)
    status = db.Column(db.String(20), default="pending")
    processed_at = db.Column(db.DateTime, nullable=True)
    vault_key = db.Column(db.String(100), unique=True, nullable=True, index=True)
    vault_key_used = db.Column(db.Boolean, default=False, nullable=False)
    vault_key_used_at = db.Column(db.DateTime, nullable=True)
    queue_sort_ts = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class RegistrationKey(db.Model):
    __tablename__ = "registration_key"
    id = db.Column(db.Integer, primary_key=True)
    key_code = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), nullable=True, index=True)
    is_admin_test_key = db.Column(db.Boolean, default=False, nullable=False)
    is_used = db.Column(db.Boolean, default=False, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("registration_key_used", uselist=False))


class Player(db.Model):
    __tablename__ = "player"
    id = db.Column(db.Integer, primary_key=True)
    # DB column is `user_id_player` (see initial migration 405dc230924f); the
    # ORM attribute stays `user_id` so existing queries/constructors keep working.
    user_id = db.Column(
        "user_id_player",
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
        unique=True,
    )
    gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False)
    currency = db.Column(db.Integer, default=0)

    campaign_memberships = db.relationship(
        "CampaignPlayer",
        back_populates="player",
        cascade="all, delete-orphan",
    )

    # Relationship to player's inventory
    inventory = db.relationship("PlayerInventory", back_populates="player")
    equipment_slots = db.relationship(
        "PlayerEquipment", back_populates="player", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Player (User: {self.user.username}, GM: {self.gm_profile.user.username})>"

class PlayerInventory(db.Model):
    __tablename__ = "player_inventory"
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey("items.item_id"), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    # Provenance tag: "GM" when the row was created by a GM equip/grant action,
    # NULL for rows the player earned/purchased normally. Keep short + nullable
    # so future sources ("LOOT", "SHOP", ...) can be added without migration.
    source = db.Column(db.String(16), nullable=True)

    # Relationships
    player = db.relationship("Player", back_populates="inventory")
    item = db.relationship("Item")

    def __repr__(self):
        return f"<PlayerInventory (Player: {self.player.user.username}, Item: {self.item.name}, Quantity: {self.quantity})>"


class PlayerEquipment(db.Model):
    __tablename__ = "player_equipment"
    __table_args__ = (UniqueConstraint("player_id", "slot", name="uq_player_equipment_slot"),)

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=False)
    slot = db.Column(db.String(50), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey("items.item_id"), nullable=True)
    # "GM" when a GM equipped this slot for the player; NULL when the player
    # equipped it themselves. Rendered as a badge in GM_view_character.html.
    source = db.Column(db.String(16), nullable=True)

    player = db.relationship("Player", back_populates="equipment_slots")
    item = db.relationship("Item")

    def __repr__(self):
        return f"<PlayerEquipment player={self.player_id} slot={self.slot} item={self.item_id}>"


class PlayerCharacterSheet(db.Model):
    """Per-(player, campaign) character sheet blob.

    Shape of ``sheet_json`` is validated in Python against the rule set
    registry in app/services/rulesets, not at the DB level. Keeping this as
    a single JSON column means new rule sets (or GM-configurable rule sets)
    do not require schema migrations.
    """

    __tablename__ = "player_character_sheet"
    __table_args__ = (
        UniqueConstraint("player_id", "campaign_id", name="uq_sheet_player_campaign"),
    )

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(
        db.Integer, db.ForeignKey("player.id"), nullable=False, index=True
    )
    campaign_id = db.Column(
        db.Integer, db.ForeignKey("campaign.id"), nullable=False, index=True
    )
    sheet_json = db.Column(db.JSON, nullable=False, default=dict)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    player = db.relationship("Player", backref="character_sheets")
    campaign = db.relationship("Campaign", backref="character_sheets")

    def __repr__(self):
        return (
            f"<PlayerCharacterSheet player={self.player_id} "
            f"campaign={self.campaign_id}>"
        )


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
    
    # Relationships
    city = db.relationship("City", backref="resource_nodes")
    owner = db.relationship("Player", backref="owned_resources")
    production_history = db.relationship("ProductionHistory", back_populates="resource_node")

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

class ResourceTransform(db.Model):
    __tablename__ = "resource_transforms"
    transform_id = db.Column(db.Integer, primary_key=True)
    input_item_id = db.Column(db.Integer, db.ForeignKey("items.item_id"), nullable=False)
    output_item_id = db.Column(db.Integer, db.ForeignKey("items.item_id"), nullable=False)
    conversion_rate = db.Column(db.Float, nullable=False)  # How many output items per input item
    shop_type = db.Column(db.String(100), nullable=False)  # Type of shop that can perform this transform
    gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False)
    
    # Relationships
    input_item = db.relationship("Item", foreign_keys=[input_item_id])
    output_item = db.relationship("Item", foreign_keys=[output_item_id])

class MarketEvent(db.Model):
    __tablename__ = "market_events"
    event_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    trigger_type = db.Column(db.String(50), nullable=False)  # date_based, player_action, random_roll, faction_state
    city_id = db.Column(db.Integer, db.ForeignKey("cities.city_id"), nullable=True)
    region = db.Column(db.String(100), nullable=True)
    effect_json = db.Column(db.JSON, nullable=False)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False)
    
    # Relationships
    city = db.relationship("City", backref="market_events")

class SimulationState(db.Model):
    __tablename__ = "simulation_state"
    state_id = db.Column(db.Integer, primary_key=True)
    current_tick = db.Column(db.Integer, nullable=False, default=0)
    speed = db.Column(db.String(10), nullable=False, default="pause")
    last_tick_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False)
    
    # Relationships
    gm_profile = db.relationship(
        "GMProfile", backref=db.backref("simulation_state", uselist=False)
    )
    
    def __repr__(self):
        return f"<SimulationState (Tick: {self.current_tick}, Speed: {self.speed})>"


class GMWorldState(db.Model):
    """Unified per-GM simulation snapshot (JSON keyed by ShopInventory.inventory_id). Phase 2+ authoritative writes."""

    __tablename__ = "gm_world_state"

    gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), primary_key=True)
    state_json = db.Column(db.JSON, nullable=True)
    schema_version = db.Column(db.Integer, nullable=False, default=1)
    tick_seq = db.Column(db.Integer, nullable=True)
    tick_generation_id = db.Column(db.String(36), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=True, default=datetime.utcnow, onupdate=datetime.utcnow)

    gm_profile = db.relationship("GMProfile", backref=db.backref("gm_world_state", uselist=False))

    def __repr__(self):
        return f"<GMWorldState gm={self.gm_profile_id} tick_seq={self.tick_seq}>"

class SimulationLog(db.Model):
    __tablename__ = "simulation_logs"
    log_id = db.Column(db.Integer, primary_key=True)
    tick_id = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    event_type = db.Column(db.String(50), nullable=False)  # price_change, stock_update, restock, city_event
    details = db.Column(db.JSON, nullable=False)
    gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False)
    
    # Relationships
    gm_profile = db.relationship("GMProfile", backref="simulation_logs")
    
    def __repr__(self):
        return f"<SimulationLog (Tick: {self.tick_id}, Type: {self.event_type})>"

class SimRule(db.Model):
    __tablename__ = "sim_rules"
    rule_id = db.Column(db.Integer, primary_key=True)
    rule_type = db.Column(db.String(50), nullable=False)  # price, stock, event
    target_type = db.Column(db.String(50), nullable=False)  # item_id, region_id, city_id
    function_type = db.Column(db.String(50), nullable=False)  # linear, decay, etc.
    condition_json = db.Column(db.JSON, nullable=False)
    gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False)
    
    # Relationships
    gm_profile = db.relationship("GMProfile", backref="sim_rules")
    
    def __repr__(self):
        return f"<SimRule (Type: {self.rule_type}, Target: {self.target_type})>"


class CampaignWorldConfig(db.Model):
    """Persisted world-generation recipe for a Campaign.

    `settings_json` stores the normalized output of
    `world_generator.validator.validate` including the `schema_version`,
    the `ranges` dict (each {min,max}), the fused `tech_magic_balance`
    range, the chosen `system_type`, and the resolved `world_seed`.
    Per-city government is stored on `City` rows
    (generated at world-gen time). A second,
    top-level `world_seed` column is denormalized for fast lookup.
    """

    __tablename__ = "campaign_world_config"

    campaign_id = db.Column(
        db.Integer,
        db.ForeignKey("campaign.id", ondelete="CASCADE"),
        primary_key=True,
    )
    settings_json = db.Column(_json_with_jsonb(), nullable=False)
    schema_version = db.Column(db.Integer, nullable=False, default=1)
    world_seed = db.Column(db.BigInteger, nullable=True)
    generated_at = db.Column(db.DateTime, server_default=func.now(), nullable=False)

    campaign = db.relationship(
        "Campaign",
        backref=db.backref(
            "world_config",
            uselist=False,
            cascade="all, delete-orphan",
            passive_deletes=True,
        ),
    )

    def __repr__(self):
        return f"<CampaignWorldConfig campaign_id={self.campaign_id} seed={self.world_seed}>"
