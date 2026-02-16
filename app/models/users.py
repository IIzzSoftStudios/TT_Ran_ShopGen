from sqlalchemy.orm import relationship
from app.extensions import db, bcrypt, UserMixin
from datetime import datetime, timedelta
import secrets

class User(db.Model, UserMixin):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False) # Consider Enum('GM', 'Player', 'Admin')?
    last_active = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Password reset fields
    reset_token = db.Column(db.String(100), nullable=True)
    reset_token_expires = db.Column(db.DateTime, nullable=True)
    
    # For GMs: Their players
    # Use primaryjoin for clarity when multiple relationships point to Player
    managed_players = db.relationship("Player", back_populates="gm_user", foreign_keys="Player.user_id_gm") 
    # For Players: Their GM (if they are a player)
    gm_profile_player = db.relationship("Player", back_populates="player_user", foreign_keys="Player.user_id_player", uselist=False)
    # GM Profile if they are a GM
    gm_profile = db.relationship("GMProfile", back_populates="user", uselist=False)

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
        
    def generate_reset_token(self):
        """Generate a password reset token valid for 1 hour"""
        self.reset_token = secrets.token_urlsafe(32)
        self.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
        db.session.commit()
        return self.reset_token
        
    def verify_reset_token(self, token):
        """Verify if the reset token is valid"""
        if not self.reset_token or not self.reset_token_expires:
            return False
        if datetime.utcnow() > self.reset_token_expires:
            return False
        return secrets.compare_digest(self.reset_token, token)
        
    def clear_reset_token(self):
        """Clear the reset token after successful password reset"""
        self.reset_token = None
        self.reset_token_expires = None
        db.session.commit()
        
    @property
    def is_active(self):
        """Check if the user is currently active (active in last 5 minutes)"""
        if not self.last_active:
            return False
        return (datetime.utcnow() - self.last_active).total_seconds() < 300  # 5 minutes

    def __repr__(self):
        return f"<User {self.username} (Role: {self.role})>"

class GMProfile(db.Model):
    __tablename__ = "gm_profile"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, unique=True)
    
    # Relationship back to the User
    user = db.relationship("User", back_populates="gm_profile")

    # Relationships with game entities owned/managed by this GM
    cities = db.relationship("City", back_populates="gm_profile")
    shops = db.relationship("Shop", back_populates="gm_profile")
    items = db.relationship("Item", back_populates="gm_profile")
    demand_modifiers = db.relationship("DemandModifier", back_populates="gm_profile")
    modifier_targets = db.relationship("ModifierTarget", back_populates="gm_profile")
    # Players managed by this GM - Linked via Player.gm_profile_id
    players = db.relationship("Player", back_populates="gm_profile", foreign_keys="Player.gm_profile_id")
    # Campaigns owned by this GM
    campaigns = db.relationship("Campaign", back_populates="gm_profile", cascade="all, delete-orphan")

    def __repr__(self):
        username = self.user.username if self.user else "N/A"
        return f"<GMProfile (User: {username})>"

class Player(db.Model):
    __tablename__ = "player"
    id = db.Column(db.Integer, primary_key=True)
    # Link to the User account representing the player
    user_id_player = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, unique=True)
    # Link to the GMProfile managing this player
    gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False)
    # Link to the User account of the GM
    user_id_gm = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False) 

    currency = db.Column(db.Integer, default=0)
    
    # Relationship back to the User who is the player
    player_user = db.relationship("User", back_populates="gm_profile_player", foreign_keys=[user_id_player])
    # Relationship back to the User who is the GM
    gm_user = db.relationship("User", back_populates="managed_players", foreign_keys=[user_id_gm])
    # Relationship back to the GMProfile
    gm_profile = db.relationship("GMProfile", back_populates="players", foreign_keys=[gm_profile_id])

    # Relationship to player's inventory
    inventory = db.relationship("PlayerInventory", back_populates="player")
    # Relationship to the player's characters (one player can have multiple characters per GM/campaign)
    characters = db.relationship("PlayerCharacter", back_populates="player", cascade="all, delete-orphan")

    # Memberships in campaigns (many-to-many via CampaignPlayer)
    campaign_memberships = db.relationship(
        "CampaignPlayer",
        back_populates="player",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        player_username = self.player_user.username if self.player_user else "N/A"
        gm_username = self.gm_profile.user.username if self.gm_profile and self.gm_profile.user else "N/A"
        return f"<Player (User: {player_username}, GM: {gm_username})>"

class PlayerInventory(db.Model):
    __tablename__ = "player_inventory"
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey("items.item_id"), nullable=False)
    quantity = db.Column(db.Integer, default=1)

    # Relationships
    player = db.relationship("Player", back_populates="inventory")
    item = db.relationship("Item", back_populates="player_inventories")

    def __repr__(self):
        player_username = self.player.player_user.username if self.player and self.player.player_user else "N/A"
        item_name = self.item.name if self.item else "N/A"
        return f"<PlayerInventory (Player: {player_username}, Item: {item_name}, Quantity: {self.quantity})>"


class PlayerCharacter(db.Model):
    """
    Represents a specific character for a Player within a GM's campaign.
    Normalized away from Player so one Player can eventually have multiple characters.
    """
    __tablename__ = "player_character"

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=False, index=True)

    # Campaign this character belongs to (one character per player per campaign for now)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaign.id"), nullable=True, index=True)

    # Basic identity
    name = db.Column(db.String(100), nullable=False)

    # System this character is using (DnD 5e, Pathfinder 2e, Savage Worlds, etc.).
    # For consistency, this should usually mirror Campaign.system_type.
    system_type = db.Column(db.String(50), nullable=False, default="generic")

    # Common meta
    level = db.Column(db.Integer, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    # Relationships
    player = db.relationship("Player", back_populates="characters")
    campaign = db.relationship("Campaign", back_populates="characters")
    equipment_slots = db.relationship(
        "CharacterEquipmentSlot",
        back_populates="character",
        cascade="all, delete-orphan",
    )
    stats = db.relationship(
        "CharacterStat",
        back_populates="character",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<PlayerCharacter (Name: {self.name}, System: {self.system_type})>"


class CharacterEquipmentSlot(db.Model):
    """
    Represents a single equipment slot on a character (e.g. head, chest, main_hand).
    Each slot may have zero or one equipped Item.
    """
    __tablename__ = "character_equipment_slot"

    id = db.Column(db.Integer, primary_key=True)
    character_id = db.Column(db.Integer, db.ForeignKey("player_character.id"), nullable=False, index=True)

    # Logical slot name used by UI and logic (e.g. head, chest, main_hand, off_hand, legs)
    slot_name = db.Column(db.String(50), nullable=False)

    # Equipped item reference; nullable means empty slot
    item_id = db.Column(db.Integer, db.ForeignKey("items.item_id"), nullable=True)

    # Relationships
    character = db.relationship("PlayerCharacter", back_populates="equipment_slots")
    item = db.relationship("Item")

    __table_args__ = (
        # Ensure each character has at most one row per slot_name
        db.UniqueConstraint("character_id", "slot_name", name="uq_character_slot"),
    )

    def __repr__(self):
        return f"<CharacterEquipmentSlot (Character: {self.character_id}, Slot: {self.slot_name}, Item: {self.item_id})>"


class CharacterStat(db.Model):
    """
    Flexible stat key/value store for a character.
    Supports multiple systems (DnD, Pathfinder, Savage Worlds) by changing stat keys.
    """
    __tablename__ = "character_stat"

    id = db.Column(db.Integer, primary_key=True)
    character_id = db.Column(db.Integer, db.ForeignKey("player_character.id"), nullable=False, index=True)

    # e.g. STR, DEX, CON, Agility, Fighting, etc.
    stat_key = db.Column(db.String(50), nullable=False)

    # Optional grouping: ability, skill, derived, resource, etc.
    category = db.Column(db.String(50), nullable=True)

    # Store as simple numeric value for now
    value = db.Column(db.Float, nullable=True)

    # Relationships
    character = db.relationship("PlayerCharacter", back_populates="stats")

    __table_args__ = (
        # Each character should have at most one row per stat_key+category
        db.UniqueConstraint("character_id", "stat_key", "category", name="uq_character_stat_key_category"),
    )

    def __repr__(self):
        return f"<CharacterStat (Character: {self.character_id}, Key: {self.stat_key}, Value: {self.value})>"
