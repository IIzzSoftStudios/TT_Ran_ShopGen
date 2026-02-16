from datetime import datetime

from app.extensions import db


class Campaign(db.Model):
    """
    Represents a single campaign owned by a GM.
    Each campaign has a game system (dnd5e, pf2e, savage_worlds, generic)
    and can have many players and characters.
    """

    __tablename__ = "campaign"

    id = db.Column(db.Integer, primary_key=True)
    gm_profile_id = db.Column(db.Integer, db.ForeignKey("gm_profile.id"), nullable=False, index=True)

    name = db.Column(db.String(120), nullable=False)

    # Game system identifier
    system_type = db.Column(
        db.String(50),
        nullable=False,
        default="generic",  # generic fallback
    )

    # Soft-activation flag (for future monetization / archiving)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # Planning-only monetization hints (no payment logic wired yet)
    is_free_tier = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    gm_profile = db.relationship("GMProfile", back_populates="campaigns")
    players = db.relationship("CampaignPlayer", back_populates="campaign", cascade="all, delete-orphan")
    characters = db.relationship("PlayerCharacter", back_populates="campaign", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Campaign (Name: {self.name}, System: {self.system_type}, GMProfile: {self.gm_profile_id})>"


class CampaignPlayer(db.Model):
    """
    Join table linking Players to Campaigns.
    Allows a GM to run multiple campaigns and assign the same or different players
    to each campaign.
    """

    __tablename__ = "campaign_player"

    id = db.Column(db.Integer, primary_key=True)

    campaign_id = db.Column(db.Integer, db.ForeignKey("campaign.id"), nullable=False, index=True)
    player_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=False, index=True)

    # Simple status field for future use (invited, active, removed, etc.)
    status = db.Column(db.String(20), nullable=False, default="active")

    # Soft-delete / activity flag
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    campaign = db.relationship("Campaign", back_populates="players")
    player = db.relationship("Player", back_populates="campaign_memberships")

    __table_args__ = (
        # Ensure a player only has one active membership per campaign
        db.UniqueConstraint("campaign_id", "player_id", name="uq_campaign_player_membership"),
    )

    def __repr__(self) -> str:
        return f"<CampaignPlayer (Campaign: {self.campaign_id}, Player: {self.player_id}, Status: {self.status})>"

