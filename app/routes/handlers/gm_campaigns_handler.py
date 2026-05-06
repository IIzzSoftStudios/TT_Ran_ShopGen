"""GM campaign CRUD and player sync."""

import hashlib
import json
import logging
import sys
import time
import traceback

from flask import render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError, OperationalError

from app.extensions import db
from app.models import (
    GMProfile, Player, Campaign, CampaignPlayer, CampaignWorldConfig, PlayerCharacterSheet,
)
from app.scripts.seeder import seed_gm_data
from app.services.billing_rules import can_create_campaign, can_add_player_to_campaign
from app.services.world_generator import (
    defaults as wg_defaults,
    generator as wg_generator,
    validator as wg_validator,
)
from app.services.world_generator.generator import GenerationTimeoutError
from app.services.world_generator.validator import ValidationError
from app.services.join_codes import (
    reveal_campaign_code_for_gm,
    log_reveal,
    redeem_player_code,
    CodeGenerationExhausted,
    InvalidCodeError,
    SeatCapError,
    CrossGMError,
    JoinCodeError,
)

log = logging.getLogger(__name__)


def _non_npc_players_for_gm(gm_profile_id: int):
    return (
        Player.query.filter_by(gm_profile_id=gm_profile_id)
        .filter(Player.is_npc.is_(False))
        .all()
    )


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
        player_count = (
            db.session.query(CampaignPlayer)
            .join(Player, Player.id == CampaignPlayer.player_id)
            .filter(
                CampaignPlayer.campaign_id == campaign.id,
                CampaignPlayer.is_active.is_(True),
                Player.is_npc.is_(False),
            )
            .count()
        )
        total_players = Player.query.filter_by(gm_profile_id=gm_profile.id).filter(
            Player.is_npc.is_(False)
        ).count()
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

        existing_players = _non_npc_players_for_gm(gm_profile.id)
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
                    campaign_id=campaign.id,
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

    existing_players = _non_npc_players_for_gm(gm_profile.id)
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

    # Character sheets are campaign-scoped and should be purged with campaign delete.
    PlayerCharacterSheet.query.filter_by(campaign_id=campaign.id).delete(
        synchronize_session=False
    )
    db.session.delete(campaign)
    db.session.commit()
    if session.get("campaign_id") == campaign_id:
        session.pop("campaign_id", None)
        session.modified = True
    flash("Campaign deleted.", "success")
    return redirect(url_for("gm.view_campaigns"))


# ---------------------------------------------------------------------------
# World generation form (GET)
# ---------------------------------------------------------------------------
_RANGE_LABELS = {
    "num_cities": "Number of Cities",
    "num_regions": "Number of Regions",
    "global_item_pool_size": "Global Item Pool Size",
    "shops_per_city": "Shops per City",
    "items_per_shop": "Items per Shop",
    "tech_magic_balance": "Magic <-> Tech Balance",
}


def _build_defaults_payload(form_override=None):
    """Assemble the template context for `GM_generate_world.html`.

    `form_override` (optional) is used when re-rendering after a
    validation failure so the GM's previous entries are preserved.
    """
    override = form_override or {}

    ranges = {}
    for key, (floor, ceiling, d_min, d_max) in wg_defaults.RANGE_SETTINGS.items():
        lo = override.get(f"{key}_min", d_min)
        hi = override.get(f"{key}_max", d_max)
        try:
            lo_i = int(lo)
            hi_i = int(hi)
        except (TypeError, ValueError):
            lo_i, hi_i = d_min, d_max
        ranges[key] = {
            "floor": floor,
            "ceiling": ceiling,
            "min": max(floor, min(ceiling, lo_i)),
            "max": max(floor, min(ceiling, hi_i)),
        }

    defaults_json = {
        "ranges": {
            k: {"min": v[2], "max": v[3]}
            for k, v in wg_defaults.RANGE_SETTINGS.items()
        },
        "system_type": "dnd5e",
    }

    return {
        "ranges": ranges,
        "labels": _RANGE_LABELS,
        "system_types": wg_defaults.SYSTEM_TYPES,
        "shop_inventory_cap": wg_defaults.SHOP_INVENTORY_CAP,
        "defaults_json": defaults_json,
        "form_values": {
            "campaign_name": override.get("campaign_name", ""),
            "system_type": override.get("system_type", "dnd5e"),
            "world_seed": override.get("world_seed", ""),
        },
    }


@login_required
def generate_world_form():
    """GET handler for `/gm/generate_world`.

    Only GMs may render this page. Anyone else is redirected to the
    main campaign selection screen.
    """
    if getattr(current_user, "role", None) != "GM":
        flash("Only GMs can create campaigns.", "error")
        return redirect(url_for("main.campaigns"))

    gm_profile = GMProfile.query.filter_by(user_id=current_user.id).first()
    if not gm_profile:
        flash("GM profile not found.", "error")
        return redirect(url_for("main.campaigns"))

    ctx = _build_defaults_payload()
    return render_template("GM_generate_world.html", **ctx)


# ---------------------------------------------------------------------------
# World generation submit (POST)
# ---------------------------------------------------------------------------
def _flash_and_reshow(form, category, message):
    flash(message, category)
    ctx = _build_defaults_payload(form)
    return render_template("GM_generate_world.html", **ctx)


@login_required
def generate_world_submit():
    """POST handler for `/gm/generate_world`.

    Pipeline:
      1. Role + GM profile re-check.
      2. Validate form -> normalized settings dict.
      3. Billing: can_create_campaign.
      4. Open transaction -> create Campaign + CampaignWorldConfig ->
         generator.generate() -> commit.
      5. Redirect to GM dashboard (`gm.home`) with session campaign set.

    All failures roll back and re-render the form with a flash message.
    """
    if getattr(current_user, "role", None) != "GM":
        flash("Only GMs can create campaigns.", "error")
        return redirect(url_for("main.campaigns")), 403

    gm_profile = GMProfile.query.filter_by(user_id=current_user.id).first()
    if not gm_profile:
        flash("GM profile not found.", "error")
        return redirect(url_for("main.campaigns")), 403

    form = request.form.to_dict(flat=True)
    log.info(
        "world_generation_post_received user_id=%s gm_profile_id=%s",
        current_user.id,
        gm_profile.id,
    )
    print(
        f"[TT Shop Gen] world_generation POST started user_id={current_user.id} "
        f"gm_profile_id={gm_profile.id} (this line means the server is handling your click)",
        file=sys.stderr,
        flush=True,
    )

    # -- Step 1: Validate --------------------------------------------------
    try:
        settings = wg_validator.validate(form)
    except ValidationError as exc:
        return _flash_and_reshow(form, "error", f"{exc.field}: {exc.message}"), 400

    # -- Step 2: Billing ---------------------------------------------------
    allowed, message = can_create_campaign(gm_profile)
    if not allowed:
        log.info(
            "world_generation_billing_denied gm_profile_id=%s reason=%s",
            gm_profile.id,
            message[:200] if message else "",
        )
        print(
            "[TT Shop Gen] world_generation blocked (HTTP 402): " + (message or "billing"),
            file=sys.stderr,
            flush=True,
        )
        return _flash_and_reshow(form, "system", message), 402

    # -- Step 3: Transactional world build --------------------------------
    campaign_name = settings["campaign_name"]
    system_type = settings["system_type"]
    started_at = time.monotonic()

    try:
        with db.session.no_autoflush:
            campaign = Campaign(
                gm_profile_id=gm_profile.id,
                name=campaign_name,
                system_type=system_type,
                is_active=True,
            )
            db.session.add(campaign)
            db.session.flush()  # assign campaign.id

            config = CampaignWorldConfig(
                campaign_id=campaign.id,
                settings_json=settings,
                schema_version=settings.get("schema_version", 1),
                world_seed=settings.get("world_seed"),
            )
            db.session.add(config)
            db.session.flush()

            # Add existing players to the new campaign up to the seat cap.
            existing_players = _non_npc_players_for_gm(gm_profile.id)
            players_added = 0
            for player in existing_players:
                can_add, _seat_msg = can_add_player_to_campaign(campaign)
                if not can_add:
                    break
                membership = CampaignPlayer(
                    campaign_id=campaign.id,
                    player_id=player.id,
                    status="active",
                    is_active=True,
                )
                db.session.add(membership)
                players_added += 1

            result = wg_generator.generate(
                gm_profile_id=gm_profile.id,
                campaign_id=campaign.id,
                settings=settings,
            )

            # Persist resolved seed back onto the config row.
            config.world_seed = result.effective_seed
            # Update settings_json with the resolved seed so round-trips reflect it.
            settings["world_seed"] = result.effective_seed
            config.settings_json = settings

        db.session.commit()

    except ValidationError as exc:
        db.session.rollback()
        return _flash_and_reshow(form, "error", f"{exc.field}: {exc.message}"), 400
    except GenerationTimeoutError as exc:
        db.session.rollback()
        log.warning("world_generation_timeout gm=%s err=%s", gm_profile.id, exc)
        return _flash_and_reshow(
            form,
            "error",
            "Generation timed out. Try a smaller world (reduce cities, shops, or items).",
        ), 503
    except IntegrityError as exc:
        db.session.rollback()
        log.warning("world_generation_integrity_error gm=%s err=%s", gm_profile.id, exc)
        return _flash_and_reshow(
            form, "error", "Name conflict detected, please retry with a different seed or name."
        ), 409
    except OperationalError as exc:
        db.session.rollback()
        log.error("world_generation_operational_error gm=%s err=%s", gm_profile.id, exc)
        return _flash_and_reshow(
            form, "error", "Database temporarily unavailable. Please try again."
        ), 503
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        log.exception("world_generation_unexpected_error gm=%s", gm_profile.id)
        _ = traceback.format_exc()
        return _flash_and_reshow(
            form, "error", f"Unexpected error during world generation: {exc}"
        ), 500

    elapsed = time.monotonic() - started_at

    # Audit log (no PII).
    settings_digest = hashlib.sha256(
        json.dumps(settings, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:12]
    log.info(
        "world_generated gm_profile_id=%s campaign_id=%s "
        "settings_digest=%s seed=%s elapsed=%.2fs "
        "regions=%d cities=%d shops=%d items=%d inv=%d players_added=%d",
        gm_profile.id,
        campaign.id,
        settings_digest,
        result.effective_seed,
        elapsed,
        result.n_regions,
        result.n_cities,
        result.n_shops,
        result.n_items,
        result.n_inventory_rows,
        players_added,
    )

    flash(
        f"Campaign '{campaign_name}' generated in {elapsed:.1f}s "
        f"(seed {result.effective_seed}, {result.n_cities} cities, "
        f"{result.n_shops} shops, {result.n_items} items).",
        "success",
    )

    session["campaign_id"] = campaign.id
    session["system_type"] = campaign.system_type
    session.permanent = True
    session.modified = True

    return redirect(url_for("gm.home"), code=303)


@login_required
def skip_world_generation_submit():
    """Create a campaign without running procedural world generation."""
    if getattr(current_user, "role", None) != "GM":
        flash("Only GMs can create campaigns.", "error")
        return redirect(url_for("main.campaigns")), 403

    gm_profile = GMProfile.query.filter_by(user_id=current_user.id).first()
    if not gm_profile:
        flash("GM profile not found.", "error")
        return redirect(url_for("main.campaigns")), 403

    form = request.form.to_dict(flat=True)
    campaign_name = (form.get("campaign_name") or "").strip()
    system_type = (form.get("system_type") or "dnd5e").strip()

    if not campaign_name:
        return _flash_and_reshow(form, "error", "campaign_name: is required"), 400
    if len(campaign_name) > 120:
        return _flash_and_reshow(
            form, "error", "campaign_name: must be 120 characters or fewer"
        ), 400
    if system_type not in wg_defaults.SYSTEM_TYPES:
        return _flash_and_reshow(form, "error", "system_type: is invalid"), 400

    allowed, message = can_create_campaign(gm_profile)
    if not allowed:
        return _flash_and_reshow(form, "system", message), 402

    try:
        campaign = Campaign(
            gm_profile_id=gm_profile.id,
            name=campaign_name,
            system_type=system_type,
            is_active=True,
        )
        db.session.add(campaign)
        db.session.flush()

        # Keep a config row so downstream tooling can detect this was intentionally skipped.
        config = CampaignWorldConfig(
            campaign_id=campaign.id,
            settings_json={
                "generation_skipped": True,
                "campaign_name": campaign_name,
                "system_type": system_type,
            },
            schema_version=1,
            world_seed=None,
        )
        db.session.add(config)

        existing_players = _non_npc_players_for_gm(gm_profile.id)
        players_added = 0
        for player in existing_players:
            can_add, _seat_msg = can_add_player_to_campaign(campaign)
            if not can_add:
                break
            membership = CampaignPlayer(
                campaign_id=campaign.id,
                player_id=player.id,
                status="active",
                is_active=True,
            )
            db.session.add(membership)
            players_added += 1

        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _flash_and_reshow(
            form, "error", "Name conflict detected, please choose a different campaign name."
        ), 409
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        log.exception("skip_world_generation_unexpected_error gm=%s", gm_profile.id)
        return _flash_and_reshow(
            form, "error", f"Unexpected error while skipping generation: {exc}"
        ), 500

    flash(
        f"Campaign '{campaign_name}' created without auto-generation. "
        f"Added {players_added} player(s).",
        "success",
    )

    session["campaign_id"] = campaign.id
    session["system_type"] = campaign.system_type
    session.permanent = True
    session.modified = True

    return redirect(url_for("gm.home"), code=303)


@login_required
def reveal_campaign_join_code(campaign_id: int):
    """JSON: lazy-fetch campaign join code for authorized GM."""
    if getattr(current_user, "role", None) != "GM":
        return jsonify(error="forbidden"), 403
    gm_profile = GMProfile.query.filter_by(user_id=current_user.id).first()
    if not gm_profile:
        return jsonify(error="forbidden"), 403
    try:
        join_code = reveal_campaign_code_for_gm(
            gm_profile_id=gm_profile.id, campaign_id=campaign_id
        )
        db.session.commit()
        log_reveal(
            user_id=current_user.id,
            action="REVEAL_CAMPAIGN_CODE",
            target_id=campaign_id,
            ip=request.remote_addr or "",
        )
        return jsonify(code=join_code, join_code=join_code, campaign_id=campaign_id)
    except InvalidCodeError:
        db.session.rollback()
        return jsonify(error="not_found"), 404
    except CodeGenerationExhausted:
        db.session.rollback()
        log.warning(
            "campaign join_code generation exhausted campaign_id=%s gm=%s",
            campaign_id,
            gm_profile.id,
        )
        return jsonify(error="code_generation_failed"), 503


@login_required
def post_redeem_player_code(campaign_id: int):
    """POST: GM pastes a PLY- code to seat a player on this campaign."""
    if getattr(current_user, "role", None) != "GM":
        flash("Only GMs can add players by code.", "error")
        return redirect(url_for("main.campaigns"))
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
    raw = (request.form.get("player_join_code") or "").strip()
    if not raw:
        flash("Enter a player code (PLY-…).", "warning")
        return redirect(url_for("gm.view_campaigns"))
    try:
        redeem_player_code(
            gm_profile_id=gm_profile.id,
            campaign=campaign,
            raw_code=raw,
            _commit=True,
        )
        flash("Player added to this campaign.", "success")
    except (InvalidCodeError, SeatCapError, CrossGMError, JoinCodeError) as e:
        flash(
            (e.args[0] if getattr(e, "args", None) else None)
            or "Could not add player with that code.",
            "danger",
        )
    return redirect(url_for("gm.view_campaigns"))
