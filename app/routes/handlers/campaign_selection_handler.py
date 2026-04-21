"""Campaign selection and session loading."""

from flask import render_template, redirect, url_for, flash, session
from flask_login import current_user

from app.extensions import db
from app.models import GMProfile, Player, Campaign, CampaignPlayer


def select_campaign():
    if getattr(current_user, "role", None) == "vault_keeper":
        return redirect(url_for("admin.keys_overview"))
    try:
        campaigns = []

        if current_user.role == "GM":
            gm_profile = GMProfile.query.filter_by(user_id=current_user.id).first()
            if gm_profile:
                gm_campaigns = Campaign.query.filter_by(
                    gm_profile_id=gm_profile.id
                ).all()
                for campaign in gm_campaigns:
                    player_count = CampaignPlayer.query.filter_by(
                        campaign_id=campaign.id, is_active=True
                    ).count()
                    campaigns.append(
                        {
                            "id": campaign.id,
                            "name": campaign.name,
                            "type": "GM",
                            "system_type": campaign.system_type,
                            "gm_username": current_user.username,
                            "player_count": player_count,
                        }
                    )
        else:
            player = Player.query.filter_by(user_id=current_user.id).first()
            if player:
                memberships = CampaignPlayer.query.filter_by(
                    player_id=player.id, is_active=True
                ).all()
                for membership in memberships:
                    campaign = membership.campaign
                    if campaign and campaign.gm_profile and campaign.gm_profile.user:
                        campaigns.append(
                            {
                                "id": campaign.id,
                                "name": campaign.name,
                                "type": "Player",
                                "system_type": campaign.system_type,
                                "gm_username": campaign.gm_profile.user.username,
                                "player_count": CampaignPlayer.query.filter_by(
                                    campaign_id=campaign.id, is_active=True
                                ).count(),
                            }
                        )

        if not campaigns:
            if current_user.role == "GM":
                flash(
                    "You don't have any campaigns yet. Create your first campaign!",
                    "info",
                )
                return redirect(url_for("gm.add_campaign"))
            flash("You are not assigned to any campaign yet.", "warning")
            return redirect(url_for("auth.logout"))

        return render_template("campaign_selection.html", campaigns=campaigns)
    except Exception as e:
        print(f"[ERROR] Error in select_campaign: {str(e)}")
        flash("An error occurred while loading campaigns. Please try again.", "error")
        return redirect(url_for("auth.logout"))


def load_campaign(campaign_id):
    if getattr(current_user, "role", None) == "vault_keeper":
        return redirect(url_for("admin.keys_overview"))
    try:
        campaign = Campaign.query.filter_by(id=campaign_id).first()
        if not campaign:
            flash("Campaign not found.", "error")
            return redirect(url_for("main.campaigns"))

        has_access = False

        if current_user.role == "GM":
            gm_profile = GMProfile.query.filter_by(user_id=current_user.id).first()
            has_access = (
                gm_profile is not None and campaign.gm_profile_id == gm_profile.id
            )
        else:
            player = Player.query.filter_by(user_id=current_user.id).first()
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
            return redirect(url_for("main.campaigns"))

        session["campaign_id"] = campaign_id
        session["system_type"] = campaign.system_type
        session.permanent = True
        session.modified = True

        if current_user.role == "GM":
            return redirect(url_for("gm.home"), code=303)
        return redirect(url_for("player.player_home"), code=303)

    except Exception as e:
        print(f"[ERROR] Error in load_campaign: {str(e)}")
        flash("An error occurred while loading the campaign. Please try again.", "error")
        return redirect(url_for("main.campaigns"))
