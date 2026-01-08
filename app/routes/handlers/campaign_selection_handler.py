"""
Campaign Selection Handler
Handles the campaign selection page logic for both GM and Player users
"""
from flask import render_template, redirect, url_for, flash, session
from flask_login import current_user
from app.extensions import db
from app.models.users import Player, GMProfile

def select_campaign():
    """Render the campaign selection page showing all campaigns the user is in"""
    try:
        campaigns = []
        
        if current_user.role == "GM":
            # For GMs: Show their GMProfile(s) - currently just one, but allows for future expansion
            gm_profile = GMProfile.query.filter_by(user_id=current_user.id).first()
            if gm_profile:
                campaigns.append({
                    'id': gm_profile.id,
                    'name': f"{current_user.username}'s Campaign",
                    'type': 'GM',
                    'gm_username': current_user.username,
                    'player_count': len(gm_profile.players) if gm_profile.players else 0
                })
        else:
            # For Players: Show all GMProfiles they're a player in
            players = Player.query.filter_by(user_id_player=current_user.id).all()
            for player in players:
                if player.gm_profile:
                    campaigns.append({
                        'id': player.gm_profile.id,
                        'name': f"{player.gm_profile.user.username}'s Campaign",
                        'type': 'Player',
                        'gm_username': player.gm_profile.user.username,
                        'player_count': len(player.gm_profile.players) if player.gm_profile.players else 0
                    })
        
        if not campaigns:
            flash("No campaigns found. Please contact support.", "error")
            return redirect(url_for("auth.logout"))
        
        return render_template("campaign_selection.html", campaigns=campaigns)
    except Exception as e:
        print(f"[ERROR] Error in select_campaign: {str(e)}")
        import traceback
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        flash("An error occurred while loading campaigns. Please try again.", "error")
        return redirect(url_for("auth.logout"))

def load_campaign(campaign_id):
    """Load a specific campaign and store it in session"""
    try:
        # Verify the user has access to this campaign
        has_access = False
        
        if current_user.role == "GM":
            gm_profile = GMProfile.query.filter_by(user_id=current_user.id, id=campaign_id).first()
            has_access = gm_profile is not None
        else:
            player = Player.query.filter_by(
                user_id_player=current_user.id,
                gm_profile_id=campaign_id
            ).first()
            has_access = player is not None
        
        if not has_access:
            flash("You do not have access to this campaign.", "error")
            return redirect(url_for("main.select_campaign"))
        
        # Store campaign ID in session
        session['campaign_id'] = campaign_id
        session.modified = True
        
        # Redirect to appropriate home page
        if current_user.role == "GM":
            return redirect(url_for("gm.gm_home"))
        else:
            return redirect(url_for("player.player_home"))
            
    except Exception as e:
        print(f"[ERROR] Error in load_campaign: {str(e)}")
        import traceback
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        flash("An error occurred while loading the campaign. Please try again.", "error")
        return redirect(url_for("main.select_campaign"))

