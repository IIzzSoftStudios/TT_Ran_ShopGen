"""
Campaign Selection Handler
Handles the campaign selection page logic for both GM and Player users
"""
from flask import render_template, redirect, url_for, flash, session
from flask_login import current_user
from app.extensions import db
from app.models.users import Player, GMProfile
from app.models.campaigns import Campaign, CampaignPlayer

def select_campaign():
    """Render the campaign selection page showing all campaigns the user is in"""
    try:
        campaigns = []
        
        if current_user.role == "GM":
            # For GMs: show all of their campaigns
            gm_profile = GMProfile.query.filter_by(user_id=current_user.id).first()
            if gm_profile:
                gm_campaigns = Campaign.query.filter_by(gm_profile_id=gm_profile.id).all()
                for campaign in gm_campaigns:
                    player_count = CampaignPlayer.query.filter_by(campaign_id=campaign.id, is_active=True).count()
                    campaigns.append({
                        'id': campaign.id,
                        'name': campaign.name,
                        'type': 'GM',
                        'system_type': campaign.system_type,
                        'gm_username': current_user.username,
                        'player_count': player_count,
                    })
        else:
            # For Players: show all campaigns they are a member of
            player = Player.query.filter_by(user_id_player=current_user.id).first()
            if player:
                memberships = CampaignPlayer.query.filter_by(player_id=player.id, is_active=True).all()
                for membership in memberships:
                    campaign = membership.campaign
                    if campaign and campaign.gm_profile and campaign.gm_profile.user:
                        campaigns.append({
                            'id': campaign.id,
                            'name': campaign.name,
                            'type': 'Player',
                            'system_type': campaign.system_type,
                            'gm_username': campaign.gm_profile.user.username,
                            'player_count': CampaignPlayer.query.filter_by(campaign_id=campaign.id, is_active=True).count(),
                        })
        
        if not campaigns:
            # For GMs with no campaigns, redirect to campaign creation
            if current_user.role == "GM":
                flash("You don't have any campaigns yet. Create your first campaign!", "info")
                return redirect(url_for("gm.gm_add_campaign"))
            # For Players with no campaigns, redirect to character creation (which will show a message)
            else:
                return redirect(url_for("player.create_character"))
        
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
        
        campaign = Campaign.query.filter_by(id=campaign_id).first()
        if not campaign:
            flash("Campaign not found.", "error")
            return redirect(url_for("main.select_campaign"))

        if current_user.role == "GM":
            gm_profile = GMProfile.query.filter_by(user_id=current_user.id).first()
            has_access = gm_profile is not None and campaign.gm_profile_id == gm_profile.id
        else:
            player = Player.query.filter_by(user_id_player=current_user.id).first()
            if not player:
                has_access = False
            else:
                membership = CampaignPlayer.query.filter_by(
                    campaign_id=campaign.id,
                    player_id=player.id,
                    is_active=True,
                ).first()
                has_access = membership is not None
        
        if not has_access:
            flash("You do not have access to this campaign.", "error")
            return redirect(url_for("main.select_campaign"))
        
        # Store campaign ID in session
        session['campaign_id'] = campaign_id
        session['system_type'] = campaign.system_type
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

