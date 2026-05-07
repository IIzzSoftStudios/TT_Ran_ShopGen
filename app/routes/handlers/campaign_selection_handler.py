"""Campaign selection and session loading."""

import time

from flask import render_template, redirect, url_for, flash, session, request
from flask_login import current_user

from app.extensions import db
from app.models import (
    Campaign,
    GMProfile,
    Player,
    PlayerCharacterSheet,
    PlayerEquipment,
    PlayerInventory,
)
from app.services.join_codes import (
    redeem_campaign_code,
    InvalidCodeError,
    SeatCapError,
    WrongRoleError,
    JoinCodeError,
)
from app.services.player_resolution import (
    all_player_ids_for_user,
    list_user_characters,
)
from app.services import character_sheet_service


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


def _build_solo_characters_for_user(user):
    """Return display rows for the user's solo Player characters (no campaign).

    Pulled from the vault sheet (campaign_id NULL) so the campaign-selection
    page can offer a direct "load my dashboard" link without requiring the
    player to also pick a campaign first. Only non-NPC rows belonging to
    ``user`` are returned, so this never leaks other accounts' characters.
    """
    if user is None or getattr(user, "role", None) != "Player":
        return []
    rows = []
    for p in list_user_characters(user):
        if p.campaign_id is not None:
            continue
        sheet = character_sheet_service.get_or_default_sheet(p, None)
        rows.append(
            {
                "id": p.id,
                "name": (sheet.get("name") or "").strip()
                or f"Character #{p.id}",
                "system_type": sheet.get("system_type") or "generic",
                "level": sheet.get("level"),
            }
        )
    return rows


def select_campaign():
    if getattr(current_user, "role", None) == "vault_keeper":
        return redirect(url_for("admin.keys_overview"))
    try:
        campaigns = []
        solo_characters = []

        if current_user.role == "GM":
            gm_profile = GMProfile.query.filter_by(user_id=current_user.id).first()
            if gm_profile:
                gm_campaigns = Campaign.query.filter_by(
                    gm_profile_id=gm_profile.id
                ).all()
                for campaign in gm_campaigns:
                    player_count = Player.query.filter_by(
                        campaign_id=campaign.id, is_npc=False
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
            seen_cids = set()
            joined_players = (
                Player.query.filter(
                    Player.user_id == current_user.id,
                    Player.is_npc.is_(False),
                    Player.campaign_id.isnot(None),
                ).all()
            )
            for player in joined_players:
                campaign = player.campaign
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
                        "player_count": Player.query.filter_by(
                            campaign_id=campaign.id, is_npc=False
                        ).count(),
                    }
                )
            solo_characters = _build_solo_characters_for_user(current_user)

        if not campaigns and not solo_characters:
            if current_user.role == "GM":
                flash(
                    "You don't have any campaigns yet. Create your first campaign!",
                    "info",
                )
                return redirect(url_for("gm.generate_world_form"))
            return render_template(
                "campaign_selection.html",
                campaigns=[],
                solo_characters=[],
                show_redeem_only=True,
            )

        return render_template(
            "campaign_selection.html",
            campaigns=campaigns,
            solo_characters=solo_characters,
            show_redeem_only=False,
        )
    except Exception as e:
        print(f"[ERROR] Error in select_campaign: {str(e)}")
        flash("An error occurred while loading campaigns. Please try again.", "error")
        return redirect(url_for("auth.logout"))


def _player_character_rows_for_campaign(user, campaign):
    """Display rows for the user's characters in ``campaign`` (chooser UI).

    Order is stable (oldest character first by id) so the chooser doesn't
    shuffle between requests.
    """
    if user is None or getattr(user, "role", None) != "Player" or campaign is None:
        return []
    players = (
        Player.query.filter(
            Player.user_id == user.id,
            Player.is_npc.is_(False),
            Player.campaign_id == campaign.id,
        )
        .order_by(Player.id.asc())
        .all()
    )
    rows = []
    for p in players:
        sheet = character_sheet_service.get_or_default_sheet(p, campaign)
        rows.append(
            {
                "id": p.id,
                "name": (sheet.get("name") or "").strip()
                or f"Character #{p.id}",
                "system_type": sheet.get("system_type")
                or campaign.system_type
                or "generic",
                "level": sheet.get("level"),
                "class_name": (sheet.get("class_name") or "").strip() or None,
                "species": (sheet.get("species") or "").strip() or None,
            }
        )
    return rows


def _commit_active_session(campaign, player):
    """Pin ``campaign`` (and optionally ``player``) into the session."""
    session["campaign_id"] = campaign.id
    session["system_type"] = campaign.system_type
    if player is not None:
        session["player_id"] = player.id
    else:
        session.pop("player_id", None)
    session.permanent = True
    session.modified = True


def load_campaign(campaign_id):
    """GET /campaigns/load/<id>: enter a campaign.

    Behavior depends on how many of the current user's characters are joined
    to ``campaign_id``:

      * **GM**: load straight through (no character concept on the GM side).
      * **Player, 0 characters**: 403 — you do not have access.
      * **Player, 1 character**: pin both ``campaign_id`` and ``player_id``,
        redirect to the player home.
      * **Player, 2+ characters**: render the character chooser. The user
        commits a pick via :func:`load_campaign_character`.
    """
    if getattr(current_user, "role", None) == "vault_keeper":
        return redirect(url_for("admin.keys_overview"))
    try:
        campaign = Campaign.query.filter_by(id=campaign_id).first()
        if not campaign:
            flash("Campaign not found.", "error")
            return redirect(url_for("main.campaigns"))

        if current_user.role == "GM":
            gm_profile = GMProfile.query.filter_by(user_id=current_user.id).first()
            has_access = (
                gm_profile is not None and campaign.gm_profile_id == gm_profile.id
            )
            if not has_access:
                flash("You do not have access to this campaign.", "error")
                return redirect(url_for("main.campaigns"))
            _commit_active_session(campaign, None)
            return redirect(url_for("gm.home"), code=303)

        characters = (
            Player.query.filter(
                Player.user_id == current_user.id,
                Player.is_npc.is_(False),
                Player.campaign_id == campaign.id,
            )
            .order_by(Player.id.asc())
            .all()
        )

        if not characters:
            flash("You do not have access to this campaign.", "error")
            return redirect(url_for("main.campaigns"))

        if len(characters) == 1:
            _commit_active_session(campaign, characters[0])
            return redirect(url_for("player.player_home"), code=303)

        rows = _player_character_rows_for_campaign(current_user, campaign)
        return render_template(
            "campaign_character_select.html",
            campaign={
                "id": campaign.id,
                "name": campaign.name,
                "system_type": campaign.system_type,
                "gm_username": (
                    campaign.gm_profile.user.username
                    if campaign.gm_profile and campaign.gm_profile.user
                    else "—"
                ),
            },
            characters=rows,
        )

    except Exception as e:
        print(f"[ERROR] Error in load_campaign: {str(e)}")
        flash("An error occurred while loading the campaign. Please try again.", "error")
        return redirect(url_for("main.campaigns"))


def load_campaign_character(campaign_id, player_id):
    """GET /campaigns/load/<cid>/character/<pid>: commit a chosen character.

    Refuses to set the session unless the ``Player`` row belongs to
    ``current_user``, is non-NPC, and is joined to the requested campaign.
    Anything else returns the user to campaign selection without changing
    state — this is the IDOR guard for the chooser flow.
    """
    if getattr(current_user, "role", None) == "vault_keeper":
        return redirect(url_for("admin.keys_overview"))
    if getattr(current_user, "role", None) != "Player":
        flash("Only players choose a character.", "warning")
        return redirect(url_for("main.campaigns"))

    campaign = Campaign.query.filter_by(id=campaign_id).first()
    if not campaign:
        flash("Campaign not found.", "error")
        return redirect(url_for("main.campaigns"))

    player = (
        Player.query.filter(
            Player.id == player_id,
            Player.user_id == current_user.id,
            Player.is_npc.is_(False),
            Player.campaign_id == campaign.id,
        )
        .first()
    )
    if player is None:
        flash("That character is not available in this campaign.", "warning")
        return redirect(url_for("main.campaigns"))

    _commit_active_session(campaign, player)
    return redirect(url_for("player.player_home"), code=303)


def delete_campaign_character(campaign_id, player_id):
    """POST /campaigns/load/<cid>/character/<pid>/delete.

    Deletes one campaign-bound character owned by the current player. This is
    intentionally scoped by user_id + campaign_id + player_id so the chooser
    cannot be used to remove another player's character.
    """
    if getattr(current_user, "role", None) != "Player":
        flash("Only players can delete their own characters.", "warning")
        return redirect(url_for("main.campaigns"))

    campaign = Campaign.query.filter_by(id=campaign_id).first()
    if not campaign:
        flash("Campaign not found.", "error")
        return redirect(url_for("main.campaigns"))

    player = (
        Player.query.filter(
            Player.id == player_id,
            Player.user_id == current_user.id,
            Player.is_npc.is_(False),
            Player.campaign_id == campaign.id,
        )
        .first()
    )
    if player is None:
        flash("That character is not available in this campaign.", "warning")
        return redirect(url_for("main.load_campaign_route", campaign_id=campaign.id))

    deleting_active_character = (
        session.get("campaign_id") == campaign.id
        and session.get("player_id") == player.id
    )

    try:
        PlayerCharacterSheet.query.filter_by(player_id=player.id).delete(
            synchronize_session=False
        )
        PlayerInventory.query.filter_by(player_id=player.id).delete(
            synchronize_session=False
        )
        PlayerEquipment.query.filter_by(player_id=player.id).delete(
            synchronize_session=False
        )
        db.session.delete(player)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        flash(f"Could not delete character: {exc}", "error")
        return redirect(url_for("main.load_campaign_route", campaign_id=campaign.id))

    if deleting_active_character:
        session.pop("player_id", None)
        session.pop("campaign_id", None)
        session.pop("system_type", None)
        session.modified = True

    flash("Character deleted.", "success")
    return redirect(url_for("main.load_campaign_route", campaign_id=campaign.id))


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
