"""
Player Helper Functions
Utility functions for player-related handlers
"""
from flask import redirect, url_for, flash, session
from flask_login import current_user
from app.models.users import Player

def get_current_player():
    """
    Get the current player based on the campaign selected in session.
    Returns (player, redirect_response) tuple.
    If player is found, redirect_response is None.
    If player is not found or campaign not selected, redirect_response is a redirect.
    """
    campaign_id = session.get('campaign_id')
    if not campaign_id:
        flash("Please select a campaign first.", "info")
        return None, redirect(url_for("main.campaigns"))
    
    player = Player.query.filter_by(
        user_id_player=current_user.id,
        gm_profile_id=campaign_id
    ).first()
    
    if not player:
        flash("Player profile not found for this campaign. Please contact your GM.", "error")
        session.pop('campaign_id', None)
        return None, redirect(url_for("main.campaigns"))
    
    return player, None

