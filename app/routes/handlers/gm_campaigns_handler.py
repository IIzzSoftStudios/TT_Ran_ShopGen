"""GM campaign CRUD and player sync."""

from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app.extensions import db
from app.models import GMProfile, Player, Campaign, CampaignPlayer
from app.scripts.seeder import seed_gm_data
from app.services.billing_rules import can_create_campaign, can_add_player_to_campaign


@login_required
def list_campaigns():
    gm_profile = GMProfile.query.filter_by(user_id=current_user.id).first()
    if not gm_profile:
        flash("GM profile not found.", "error")
        return redirect(url_for("main.campaigns"))

    campaigns = Campaign.query.filter_by(gm_profile_id=gm_profile.id).order_by(
        Campaign.created_at.asc()
    ).all()

    campaigns_with_info = []
    for campaign in campaigns:
        player_count = CampaignPlayer.query.filter_by(
            campaign_id=campaign.id, is_active=True
        ).count()
        total_players = Player.query.filter_by(gm_profile_id=gm_profile.id).count()
        campaigns_with_info.append(
            {
                "campaign": campaign,
                "player_count": player_count,
                "total_players": total_players,
            }
        )

    return render_template("GM_view_campaigns.html", campaigns_info=campaigns_with_info)


@login_required
def create_campaign():
    gm_profile = GMProfile.query.filter_by(user_id=current_user.id).first()
    if not gm_profile:
        flash("GM profile not found.", "error")
        return redirect(url_for("main.campaigns"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        system_type = request.form.get("system_type", "generic").strip() or "generic"
        world_setup = request.form.get("world_setup", "blank").strip() or "blank"

        if not name:
            flash("Campaign name is required.", "error")
            return render_template("GM_add_campaign.html")

        allowed, message = can_create_campaign(gm_profile)
        if not allowed:
            flash(message, "system")
            return render_template("GM_add_campaign.html")

        campaign = Campaign(
            gm_profile_id=gm_profile.id,
            name=name,
            system_type=system_type,
            is_active=True,
        )
        db.session.add(campaign)
        db.session.flush()

        existing_players = Player.query.filter_by(gm_profile_id=gm_profile.id).all()
        players_added = 0
        for player in existing_players:
            can_add, seat_message = can_add_player_to_campaign(campaign)
            if can_add:
                existing_membership = CampaignPlayer.query.filter_by(
                    campaign_id=campaign.id,
                    player_id=player.id,
                ).first()
                if not existing_membership:
                    membership = CampaignPlayer(
                        campaign_id=campaign.id,
                        player_id=player.id,
                        status="active",
                        is_active=True,
                    )
                    db.session.add(membership)
                    players_added += 1
            else:
                flash(
                    f"Note: {seat_message} Only added {players_added} players to the campaign.",
                    "system",
                )
                break

        db.session.commit()

        if world_setup == "preseeded":
            try:
                seed_gm_data(
                    gm_profile.id,
                    num_cities=10,
                    num_shops_per_city=10,
                    num_global_items=50,
                    num_items_per_shop=10,
                )
                flash(
                    f"Campaign '{name}' created successfully with preseeded entities. Added {players_added} player(s).",
                    "success",
                )
            except Exception as e:
                flash(
                    f"Campaign '{name}' created with {players_added} player(s), but seeding encountered an error: {str(e)}",
                    "warning",
                )
        elif world_setup == "preset":
            flash(
                f"Campaign '{name}' created. Added {players_added} player(s). Preset worlds are coming soon!",
                "info",
            )
        else:
            flash(
                f"Campaign '{name}' created successfully with a blank slate. Added {players_added} player(s).",
                "success",
            )

        return redirect(url_for("main.campaigns"))

    return render_template("GM_add_campaign.html")


@login_required
def sync_players_to_campaign(campaign_id: int):
    gm_profile = GMProfile.query.filter_by(user_id=current_user.id).first()
    if not gm_profile:
        flash("GM profile not found.", "error")
        return redirect(url_for("gm.view_campaigns"))

    campaign = Campaign.query.filter_by(
        id=campaign_id, gm_profile_id=gm_profile.id
    ).first()
    if not campaign:
        flash("Campaign not found.", "error")
        return redirect(url_for("gm.view_campaigns"))

    existing_players = Player.query.filter_by(gm_profile_id=gm_profile.id).all()
    players_added = 0
    players_skipped = 0

    for player in existing_players:
        existing_membership = CampaignPlayer.query.filter_by(
            campaign_id=campaign.id,
            player_id=player.id,
        ).first()

        if existing_membership:
            players_skipped += 1
            continue

        can_add, _ = can_add_player_to_campaign(campaign)
        if can_add:
            membership = CampaignPlayer(
                campaign_id=campaign.id,
                player_id=player.id,
                status="active",
                is_active=True,
            )
            db.session.add(membership)
            players_added += 1
        else:
            flash(
                f"Reached seat limit for campaign '{campaign.name}'. Added {players_added} player(s), skipped {players_skipped} already in campaign.",
                "system",
            )
            db.session.commit()
            return redirect(url_for("gm.view_campaigns"))

    db.session.commit()
    flash(
        f"Synced players to campaign '{campaign.name}'. Added {players_added} player(s), {players_skipped} were already in the campaign.",
        "success",
    )
    return redirect(url_for("gm.view_campaigns"))


@login_required
def delete_campaign(campaign_id: int):
    gm_profile = GMProfile.query.filter_by(user_id=current_user.id).first()
    if not gm_profile:
        flash("GM profile not found.", "error")
        return redirect(url_for("main.campaigns"))

    campaign = Campaign.query.filter_by(
        id=campaign_id, gm_profile_id=gm_profile.id
    ).first()
    if not campaign:
        flash("Campaign not found.", "error")
        return redirect(url_for("gm.view_campaigns"))

    db.session.delete(campaign)
    db.session.commit()
    flash("Campaign deleted.", "success")
    return redirect(url_for("gm.view_campaigns"))
