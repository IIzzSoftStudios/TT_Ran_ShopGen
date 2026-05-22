from sqlalchemy.orm import relationship
from sqlalchemy import UniqueConstraint, func, Index, event
from sqlalchemy.dialects.postgresql import JSONB
from app.extensions import db, SQLAlchemy, bcrypt, UserMixin
from app.utils.validators import PASSWORD_REUSE_FORBIDDEN_DAYS
from datetime import datetime, timedelta


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
    campaign_id = db.Column(
        db.Integer,
        db.ForeignKey("campaign.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

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
    campaign_id = db.Column(
        db.Integer,
        db.ForeignKey("campaign.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    preferred_region = db.Column(db.String(100), nullable=True)  # Preferred region for sourcing
    next_restock_day = db.Column(db.Integer, nullable=True)

    # Many-to-Many relationship with City
    cities = db.relationship("City", secondary=shop_cities, back_populates="shops")
    # Many-to-Many relationship with Item through ShopInventory
    inventory = db.relationship("ShopInventory", back_populates="shop")

    def __repr__(self):
        return f"<Shop {self.name} (Type: {self.type})>"

class Item(db.Model):
    __tablename__ = "items"
    __table_args__ = (
        Index("ix_item_campaign_axis", "campaign_id", "axis_position"),
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
    campaign_id = db.Column(
        db.Integer,
        db.ForeignKey("campaign.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
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
    campaign_id = db.Column(
        db.Integer,
        db.ForeignKey("campaign.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

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
    shop_id = db.Column(
        db.Integer,
        db.ForeignKey("shops.shop_id", ondelete="CASCADE"),
        nullable=False,
    )
    item_id = db.Column(db.Integer, db.ForeignKey("items.item_id"), nullable=False)
    price = db.Column(db.Float, nullable=False)
    recorded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    campaign_id = db.Column(
        db.Integer,
        db.ForeignKey("campaign.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    shop = db.relationship("Shop", backref="price_history_entries")
    item = db.relationship("Item", backref="price_history_entries")

    def __repr__(self):
        return f"<PriceHistory shop={self.shop_id} item={self.item_id} price={self.price}>"


class RegionalMarket(db.Model):
    """Tracks supply and demand for items within a region."""
    __tablename__ = "regional_markets"
    
    market_id = db.Column(db.Integer, primary_key=True)
    city_id = db.Column(
        db.Integer,
        db.ForeignKey("cities.city_id", ondelete="CASCADE"),
        nullable=False,
    )
    item_id = db.Column(db.Integer, db.ForeignKey("items.item_id"), nullable=False)
    total_supply = db.Column(db.Integer, default=0)
    total_demand = db.Column(db.Integer, default=0)
    average_price = db.Column(db.Float, nullable=False)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    campaign_id = db.Column(
        db.Integer,
        db.ForeignKey("campaign.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

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
    baseline_avg_stock = db.Column(db.Float, nullable=True)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    campaign_id = db.Column(
        db.Integer,
        db.ForeignKey("campaign.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

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
    campaign_id = db.Column(
        db.Integer,
        db.ForeignKey("campaign.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    def is_currently_active(self):
        """Checks if the modifier is active and within its time range."""
        if not self.is_active:
            return False
        if self.end_date and datetime.utcnow() > self.end_date:
            return False
        return True

    @staticmethod
    def get_active_modifiers(campaign_id: int):
        """Fetches active modifiers for one campaign."""
        return DemandModifier.query.filter_by(
            is_active=True, campaign_id=campaign_id
        ).all()

class ModifierTarget(db.Model):
    __tablename__ = "modifier_targets"

    id = db.Column(db.Integer, primary_key=True)
    modifier_id = db.Column(db.Integer, db.ForeignKey("demand_modifiers.id"), nullable=False)
    entity_type = db.Column(db.Enum("region", "city", "shop", "item", name="target_type"), nullable=False)
    entity_id = db.Column(db.Integer, nullable=False)  # The ID of the affected entity
    campaign_id = db.Column(
        db.Integer,
        db.ForeignKey("campaign.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

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
    avatar_updated_at = db.Column(db.DateTime, nullable=True)

    # For GMs: Their players
    players = db.relationship("Player", backref="user", foreign_keys="Player.user_id")
    # GM Profile if they are a GM
    gm_profile = db.relationship("GMProfile", backref="user", uselist=False)

    def set_password(self, password):
        self.password = bcrypt.generate_password_hash(password).decode("utf-8") 

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password, password)

    def set_reset_otp(self, plaintext_code):
        self.reset_otp_hash = bcrypt.generate_password_hash(plaintext_code).decode("utf-8")
        self.reset_otp_expires = datetime.utcnow() + timedelta(minutes=10)

    def clear_reset_otp(self):
        self.reset_otp_hash = None
        self.reset_otp_expires = None

    def verify_reset_otp(self, plaintext_code):
        if not self.reset_otp_hash or not self.reset_otp_expires:
            return False
        if datetime.utcnow() > self.reset_otp_expires:
            return False
        return bcrypt.check_password_hash(self.reset_otp_hash, plaintext_code)

    def plaintext_matches_recent_password(self, plaintext, *, days=None):
        """True if plaintext matches current password or any hash from the last `days`."""
        if days is None:
            days = PASSWORD_REUSE_FORBIDDEN_DAYS
        cutoff = datetime.utcnow() - timedelta(days=days)
        if self.check_password(plaintext):
            return True
        for row in UserPasswordHistory.query.filter(
            UserPasswordHistory.user_id == self.id,
            UserPasswordHistory.created_at >= cutoff,
        ).all():
            if bcrypt.check_password_hash(row.password_hash, plaintext):
                return True
        return False

    def archive_password_hash_before_change(self):
        """Store current password hash in history before replacing it (for reuse policy)."""
        if self.id is None or not self.password:
            return
        db.session.add(
            UserPasswordHistory(
                user_id=self.id,
                password_hash=self.password,
                created_at=datetime.utcnow(),
            )
        )

    def prune_password_history_older_than(self, *, days=None):
        """Drop history rows older than `days` (keeps checks aligned with policy window)."""
        if days is None:
            days = PASSWORD_REUSE_FORBIDDEN_DAYS
        cutoff = datetime.utcnow() - timedelta(days=days)
        UserPasswordHistory.query.filter(
            UserPasswordHistory.user_id == self.id,
            UserPasswordHistory.created_at < cutoff,
        ).delete(synchronize_session=False)

    def update_activity(self):
        self.last_active = datetime.utcnow()
        db.session.commit()

    def get_id(self):
        return str(self.id)

    @property
    def is_active(self):
        return True


class UserPasswordHistory(db.Model):
    """Prior password hashes for reuse policy (e.g. no reuse within 180 days)."""

    __tablename__ = "user_password_history"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("password_history", lazy="dynamic"))


class GMProfile(db.Model):
    __tablename__ = "gm_profile"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, unique=True)

    campaigns = db.relationship(
        "Campaign", back_populates="gm_profile", cascade="all, delete-orphan"
    )

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
    allow_player_debt = db.Column(db.Boolean, default=False, nullable=False)
    current_game_day = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    join_code = db.Column(db.String(32), unique=True, nullable=True, index=True)

    gm_profile = db.relationship("GMProfile", back_populates="campaigns")
    cities = db.relationship(
        "City", backref="campaign", cascade="all, delete-orphan", passive_deletes=True
    )
    shops = db.relationship(
        "Shop", backref="campaign", cascade="all, delete-orphan", passive_deletes=True
    )
    items = db.relationship(
        "Item", backref="campaign", cascade="all, delete-orphan", passive_deletes=True
    )
    inventory = db.relationship(
        "ShopInventory",
        backref="campaign",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    demand_modifiers = db.relationship(
        "DemandModifier",
        backref="campaign",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    modifier_targets = db.relationship(
        "ModifierTarget",
        backref="campaign",
        cascade="all, delete-orphan",
        passive_deletes=True,
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


class UserSubmission(db.Model):
    """Account-menu feedback, bug reports, and suggestions."""

    __tablename__ = "user_submissions"

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(20), nullable=False, index=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    username_snapshot = db.Column(db.String(100), nullable=False)
    submitted_session_mode = db.Column(db.String(20), nullable=False)
    account_role = db.Column(db.String(50), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(120), nullable=True)
    body = db.Column(db.Text, nullable=False)
    extra = db.Column(_json_with_jsonb(), nullable=False, default=dict)
    page_url = db.Column(db.String(500), nullable=False)
    campaign_id = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = db.relationship(
        "User",
        backref=db.backref("submissions", lazy="dynamic"),
    )


class AccessRequest(db.Model):
    __tablename__ = "access_requests"

    id = db.Column(db.Integer, primary_key=True)
    contact_name = db.Column(db.String(120), nullable=False, default="")
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
    key_phase = db.Column(db.String(40), nullable=False, default="default", index=True)
    is_admin_test_key = db.Column(db.Boolean, default=False, nullable=False)
    is_used = db.Column(db.Boolean, default=False, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("registration_key_used", uselist=False))


class Player(db.Model):
    __tablename__ = "player"
    # Per-character row. ``campaign_id`` is the sole campaign tenancy column;
    # NULL means a solo vault character (not yet joined to any campaign).
    __table_args__ = tuple()
    id = db.Column(db.Integer, primary_key=True)
    # PostgreSQL DDL in the wild uses `user_id_gm` for the linked login user
    # (historical name). The ORM attribute stays `user_id`; filters must use
    # `Player.user_id`, never raw column-name strings in SQLAlchemy filters.
    user_id = db.Column(
        "user_id_gm",
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
    )
    # NULL = pre-campaign "solo" vault character. Not NULL = joined to a campaign.
    campaign_id = db.Column(
        db.Integer,
        db.ForeignKey("campaign.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    currency = db.Column(db.Integer, default=0)
    is_npc = db.Column(db.Boolean, default=False, nullable=False)
    join_code = db.Column(db.String(32), unique=True, nullable=True, index=True)

    campaign = db.relationship("Campaign", backref="players")

    # Relationship to player's inventory
    inventory = db.relationship("PlayerInventory", back_populates="player")
    equipment_slots = db.relationship(
        "PlayerEquipment", back_populates="player", cascade="all, delete-orphan"
    )

    def __repr__(self):
        uname = self.user.username if self.user else "NPC"
        camp = "solo" if self.campaign_id is None else f"camp={self.campaign_id}"
        return f"<Player (User: {uname}, {camp})>"

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
        pl = (
            self.player.user.username
            if self.player and self.player.user
            else (f"NPC#{self.player_id}" if self.player_id else "?")
        )
        iname = self.item.name if self.item else "?"
        return f"<PlayerInventory (Player: {pl}, Item: {iname}, Quantity: {self.quantity})>"


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
    """Per-player character sheet: one vault row (campaign_id NULL) and/or per-campaign rows.

    Shape of ``sheet_json`` is validated in Python against the rule set
    registry in app/services/rulesets, not at the DB level. Keeping this as
    a single JSON column means new rule sets (or GM-configurable rule sets)
    do not require schema migrations.
    """

    __tablename__ = "player_character_sheet"
    # Partial unique indexes (vault vs per-campaign) — see schema_compat.
    __table_args__ = tuple()

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(
        db.Integer, db.ForeignKey("player.id"), nullable=False, index=True
    )
    campaign_id = db.Column(
        db.Integer, db.ForeignKey("campaign.id"), nullable=True, index=True
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


class ResourceTransform(db.Model):
    __tablename__ = "resource_transforms"
    transform_id = db.Column(db.Integer, primary_key=True)
    input_item_id = db.Column(db.Integer, db.ForeignKey("items.item_id"), nullable=False)
    output_item_id = db.Column(db.Integer, db.ForeignKey("items.item_id"), nullable=False)
    conversion_rate = db.Column(db.Float, nullable=False)  # How many output items per input item
    shop_type = db.Column(db.String(100), nullable=False)  # Type of shop that can perform this transform
    campaign_id = db.Column(
        db.Integer,
        db.ForeignKey("campaign.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

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
    campaign_id = db.Column(
        db.Integer,
        db.ForeignKey("campaign.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Relationships
    city = db.relationship("City", backref="market_events")

class SimulationState(db.Model):
    __tablename__ = "simulation_state"
    state_id = db.Column(db.Integer, primary_key=True)
    current_tick = db.Column(db.Integer, nullable=False, default=0)
    speed = db.Column(db.String(10), nullable=False, default="pause")
    last_tick_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    campaign_id = db.Column(
        db.Integer,
        db.ForeignKey("campaign.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    # GM dashboard simulation control clicks (vault usage report).
    sim_clicks_day = db.Column(db.Integer, nullable=False, default=0)
    sim_clicks_week = db.Column(db.Integer, nullable=False, default=0)
    sim_clicks_month = db.Column(db.Integer, nullable=False, default=0)
    sim_clicks_year = db.Column(db.Integer, nullable=False, default=0)
    sim_clicks_pause = db.Column(db.Integer, nullable=False, default=0)
    last_market_run = db.Column(db.JSON, nullable=True)

    campaign = db.relationship(
        "Campaign",
        backref=db.backref("simulation_state", uselist=False, passive_deletes="all"),
    )

    def __repr__(self):
        return f"<SimulationState (campaign={self.campaign_id}, Tick: {self.current_tick}, Speed: {self.speed})>"


class GMWorldState(db.Model):
    """Per-campaign simulation snapshot (JSON keyed by ShopInventory.inventory_id). Phase 2+ authoritative writes."""

    __tablename__ = "gm_world_state"

    campaign_id = db.Column(
        db.Integer,
        db.ForeignKey("campaign.id", ondelete="CASCADE"),
        primary_key=True,
    )
    state_json = db.Column(db.JSON, nullable=True)
    schema_version = db.Column(db.Integer, nullable=False, default=1)
    tick_seq = db.Column(db.Integer, nullable=True)
    tick_generation_id = db.Column(db.String(36), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=True, default=datetime.utcnow, onupdate=datetime.utcnow)

    campaign = db.relationship(
        "Campaign",
        backref=db.backref("world_state", uselist=False, passive_deletes="all"),
    )

    def __repr__(self):
        return f"<GMWorldState campaign={self.campaign_id} tick_seq={self.tick_seq}>"

class SimulationLog(db.Model):
    __tablename__ = "simulation_logs"
    log_id = db.Column(db.Integer, primary_key=True)
    tick_id = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    event_type = db.Column(db.String(50), nullable=False)  # price_change, stock_update, restock, city_event
    details = db.Column(db.JSON, nullable=False)
    campaign_id = db.Column(
        db.Integer,
        db.ForeignKey("campaign.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    campaign = db.relationship(
        "Campaign",
        backref=db.backref("simulation_logs", passive_deletes=True),
    )

    def __repr__(self):
        return f"<SimulationLog (Tick: {self.tick_id}, Type: {self.event_type})>"

class SimRule(db.Model):
    __tablename__ = "sim_rules"
    rule_id = db.Column(db.Integer, primary_key=True)
    rule_type = db.Column(db.String(50), nullable=False)  # price, stock, event
    target_type = db.Column(db.String(50), nullable=False)  # item_id, region_id, city_id
    function_type = db.Column(db.String(50), nullable=False)  # linear, decay, etc.
    condition_json = db.Column(db.JSON, nullable=False)
    campaign_id = db.Column(
        db.Integer,
        db.ForeignKey("campaign.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    campaign = db.relationship(
        "Campaign",
        backref=db.backref("sim_rules", passive_deletes=True),
    )

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


class DeletedCampaignSimSnapshot(db.Model):
    """Tombstone of a Campaign's simulation usage metrics, retained after delete.

    When a GM deletes a Campaign, the live ``simulation_state`` row, the
    ``current_game_day`` value, and the campaign's identity all cascade
    away with the parent. The vault-keeper-facing GM simulation usage
    dashboard is the surface that needs continuity for analytical purposes,
    so this table archives the final per-campaign metrics at the moment of
    deletion. The dashboard then unions live + tombstone rows when computing
    per-GM totals and per-campaign drill-downs.

    The row is intentionally denormalized (campaign name + system + dates +
    counters) so that the analyst view can render meaningful campaign
    identity even after the source rows are gone. There is no FK back to
    ``campaign`` because the parent has been deleted by the time this row
    is queried; the original ``campaign_id`` is preserved as a soft
    reference for cross-checks but not enforced.

    Retention: indefinite. The payload contains no raw user PII (only
    GM-supplied campaign name, system slug, click counters, timestamps).
    Deleting the owning ``GMProfile`` cascades these rows away, since
    per-GM analytics lose meaning once the GM is gone.
    """

    __tablename__ = "deleted_campaign_sim_snapshot"

    snapshot_id = db.Column(db.Integer, primary_key=True)
    gm_profile_id = db.Column(
        db.Integer,
        db.ForeignKey("gm_profile.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    campaign_id = db.Column(db.Integer, nullable=False, index=True)
    campaign_name = db.Column(db.String(120), nullable=False)
    system_type = db.Column(db.String(50), nullable=False, default="generic")
    campaign_created_at = db.Column(db.DateTime, nullable=True)
    deleted_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    current_game_day = db.Column(db.Integer, nullable=False, default=1)
    days_simulated = db.Column(db.Integer, nullable=False, default=0)
    sim_clicks_day = db.Column(db.Integer, nullable=False, default=0)
    sim_clicks_week = db.Column(db.Integer, nullable=False, default=0)
    sim_clicks_month = db.Column(db.Integer, nullable=False, default=0)
    sim_clicks_year = db.Column(db.Integer, nullable=False, default=0)
    sim_clicks_pause = db.Column(db.Integer, nullable=False, default=0)
    last_tick_time = db.Column(db.DateTime, nullable=True)

    gm_profile = db.relationship(
        "GMProfile",
        backref=db.backref(
            "deleted_campaign_snapshots",
            cascade="all, delete-orphan",
            passive_deletes=True,
        ),
    )

    def __repr__(self):
        return (
            f"<DeletedCampaignSimSnapshot gm_profile={self.gm_profile_id} "
            f"campaign={self.campaign_id} name={self.campaign_name!r} "
            f"deleted_at={self.deleted_at}>"
        )


# --- Join codes: listeners run after module load (join_codes imports these models). ---
def _register_join_code_listeners():
    from sqlalchemy import inspect as orm_inspect

    from app.services import join_codes as _jc

    @event.listens_for(Campaign, "before_insert")
    def _campaign_join_code(mapper, connection, target):
        if getattr(target, "join_code", None):
            return
        target.join_code = _jc.generate_raw_code(_jc.CAMPAIGN_PREFIX)

    @event.listens_for(Player, "before_insert")
    def _player_join_code(mapper, connection, target):
        if getattr(target, "is_npc", False):
            return
        if getattr(target, "join_code", None):
            return
        target.join_code = _jc.generate_raw_code(_jc.PLAYER_PREFIX)

    @event.listens_for(Player, "before_update")
    def _player_join_code_on_update(mapper, connection, target):
        """Assign PLY- code when promoting NPC → PC (not on every PC update)."""
        if getattr(target, "is_npc", False):
            return
        if getattr(target, "join_code", None):
            return
        hist = orm_inspect(target).attrs.is_npc.history
        if not hist.has_changes():
            return
        prior = hist.deleted
        if not prior or True not in prior:
            return
        target.join_code = _jc.generate_raw_code(_jc.PLAYER_PREFIX)


_register_join_code_listeners()
