"""Campaign selection and session loading."""

import time

from flask import render_template, redirect, url_for, flash, session, request
from flask_login import current_user

from app.extensions import db
from app.models import GMProfile, Player, Campaign, CampaignPlayer
from app.services.join_codes import (
    redeem_campaign_code,
    InvalidCodeError,
    SeatCapError,
    WrongRoleError,
    JoinCodeError,
)
from app.services.player_resolution import all_player_ids_for_user


def _redeem_failures_in_window():
    now = time.time()
    lst = [t for t in session.get("_campaign_redeem_fails", []) if now - t < 3600]
    session["_campaign_redeem_fails"] = lst
    session.modified = True
    return lst


def _register_redeem_failure():
    lst = _redeem_failures_in_window()
    lst.append(time.time())
    session["_campaign_redeem_fails"] = lst
    session.modified = True


def _clear_redeem_failures():
    session.pop("_campaign_redeem_fails", None)
    session.modified = True


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
            pl_ids = all_player_ids_for_user(current_user)
            seen_cids = set()
            if pl_ids:
                memberships = (
                    CampaignPlayer.query.filter(
                        CampaignPlayer.player_id.in_(pl_ids),
                        CampaignPlayer.is_active.is_(True),
                    ).all()
                )
                for membership in memberships:
                    campaign = membership.campaign
                    if (
                        not campaign
                        or campaign.id in seen_cids
                        or not campaign.gm_profile
                        or not campaign.gm_profile.user
                    ):
                        continue
                    seen_cids.add(campaign.id)
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
                return redirect(url_for("gm.generate_world_form"))
            return render_template(
                "campaign_selection.html",
                campaigns=[],
                show_redeem_only=True,
            )

        return render_template(
            "campaign_selection.html",
            campaigns=campaigns,
            show_redeem_only=False,
        )
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
            player = Player.query.filter_by(
                user_id=current_user.id,
                gm_profile_id=campaign.gm_profile_id,
                is_npc=False,
            ).first()
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


def redeem_campaign_post():
    """POST /campaigns/redeem — logged-in player pastes a CAMP- code."""
    if getattr(current_user, "role", None) != "Player":
        flash("Only players can redeem a campaign code.", "warning")
        return redirect(url_for("main.campaigns"))

    code = (request.form.get("campaign_code") or "").strip()
    if not code:
        flash("Enter a campaign code.", "warning")
        return redirect(url_for("main.campaigns"))

    fails = _redeem_failures_in_window()
    if len(fails) >= 3:
        flash("Too many invalid code attempts. Try again in up to one hour.", "danger")
        return redirect(url_for("main.campaigns"))

    try:
        redeem_campaign_code(current_user, code, _commit=True)
        _clear_redeem_failures()
        flash("You joined the campaign.", "success")
    except (InvalidCodeError, SeatCapError, WrongRoleError, JoinCodeError) as e:
        _register_redeem_failure()
        flash(
            (e.args[0] if getattr(e, "args", None) else None)
            or "Could not join with that code.",
            "danger",
        )
    return redirect(url_for("main.campaigns"))
