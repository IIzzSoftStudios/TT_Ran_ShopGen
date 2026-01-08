from sqlalchemy.orm import relationship
from sqlalchemy import JSON
from app.extensions import db, bcrypt, UserMixin
from datetime import datetime, timedelta
import secrets
import json

class User(db.Model, UserMixin):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False) # Consider Enum('GM', 'Player', 'Admin')?
    last_active = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Email verification fields
    email_verified = db.Column(db.Boolean, default=False, nullable=False)
    verification_token = db.Column(db.String(100), nullable=True)
    verification_token_expires = db.Column(db.DateTime, nullable=True)
    
    # Password reset fields
    reset_token = db.Column(db.String(100), nullable=True)
    reset_token_expires = db.Column(db.DateTime, nullable=True)
    
    # Two-factor authentication fields
    two_factor_enabled = db.Column(db.Boolean, default=False, nullable=False)
    two_factor_secret = db.Column(db.String(32), nullable=True)  # TOTP secret
    two_factor_backup_codes = db.Column(db.Text, nullable=True)  # JSON array of backup codes
    
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
    
    def generate_verification_token(self):
        """Generate an email verification token valid for 24 hours"""
        self.verification_token = secrets.token_urlsafe(32)
        self.verification_token_expires = datetime.utcnow() + timedelta(hours=24)
        db.session.commit()
        return self.verification_token
        
    def verify_email_token(self, token):
        """Verify if the email verification token is valid"""
        if not self.verification_token or not self.verification_token_expires:
            return False
        if datetime.utcnow() > self.verification_token_expires:
            return False
        return secrets.compare_digest(self.verification_token, token)
        
    def verify_email(self):
        """Mark email as verified and clear token"""
        self.email_verified = True
        self.verification_token = None
        self.verification_token_expires = None
        db.session.commit()
    
    def generate_backup_codes(self, count=10):
        """Generate backup codes for 2FA"""
        codes = [secrets.token_urlsafe(8) for _ in range(count)]
        self.two_factor_backup_codes = json.dumps(codes)
        db.session.commit()
        return codes
    
    def get_backup_codes(self):
        """Get backup codes as a list"""
        if not self.two_factor_backup_codes:
            return []
        try:
            return json.loads(self.two_factor_backup_codes)
        except:
            return []
    
    def use_backup_code(self, code):
        """Use a backup code and remove it from the list"""
        codes = self.get_backup_codes()
        if code in codes:
            codes.remove(code)
            self.two_factor_backup_codes = json.dumps(codes) if codes else None
            db.session.commit()
            return True
        return False
        
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
