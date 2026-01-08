"""
GM Helper Functions
Utility functions for GM-related handlers
"""
from flask import redirect, url_for, flash, session
from flask_login import current_user
from app.models.users import GMProfile

def get_current_gm_profile():
    """
    Get the current GM profile based on the campaign selected in session.
    Returns (gm_profile, redirect_response) tuple.
    If gm_profile is found, redirect_response is None.
    If gm_profile is not found or campaign not selected, redirect_response is a redirect.
    """
    campaign_id = session.get('campaign_id')
    if not campaign_id:
        flash("Please select a campaign first.", "info")
        return None, redirect(url_for("main.campaigns"))
    
    gm_profile = GMProfile.query.filter_by(
        user_id=current_user.id,
        id=campaign_id
    ).first()
    
    if not gm_profile:
        flash("You do not have access to this campaign.", "error")
        session.pop('campaign_id', None)
        return None, redirect(url_for("main.campaigns"))
    
    return gm_profile, None

