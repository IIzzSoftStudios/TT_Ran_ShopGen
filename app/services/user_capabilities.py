"""Capability checks for unified GM + player accounts."""

from __future__ import annotations

from app.extensions import db
from app.models import GMProfile, Player


def has_gm_capability(user) -> bool:
    """GM management tasks: requires linked GMProfile."""
    return user is not None and user.gm_profile is not None


def has_player_capability(user) -> bool:
    """Latent or active player status; excludes vault_keeper."""
    if not user or user.role == "vault_keeper":
        return False
    if user.role in ("Player", "Both"):
        return True
    return (
        db.session.query(Player.id)
        .filter(Player.user_id == user.id, Player.is_npc.is_(False))
        .first()
        is not None
    )


def ensure_gm_profile(user) -> GMProfile:
    """Idempotent GMProfile; flush inside caller transaction."""
    if not user:
        raise ValueError("A valid user instance is required.")
    if user.gm_profile:
        return user.gm_profile
    profile = GMProfile(user_id=user.id)
    db.session.add(profile)
    db.session.flush()
    return profile


def can_redeem_campaign_code(user) -> bool:
    """Block vault_keeper from standard campaign redeem loops."""
    return user is not None and user.role != "vault_keeper"
