"""GM campaign CRUD and player sync."""

import hashlib
import json
import logging
import sys
import time
import traceback

from flask import render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import login_required, current_user
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError, OperationalError

from app.extensions import db
from app.models import (
    GMProfile,
    Player,
    Campaign,
    CampaignWorldConfig,
    City,
    DemandModifier,
    GlobalMarket,
    Item,
    MarketEvent,
    ModifierTarget,
    PlayerEquipment,
    PlayerCharacterSheet,
    PlayerInventory,
    DeletedCampaignSimSnapshot,
    GMWorldState,
    PriceHistory,
    RegionalMarket,
    ResourceTransform,
    Shop,
    ShopInventory,
    SimulationLog,
    SimulationState,
    SimRule,
    shop_cities,
)
from app.scripts.seeder import seed_gm_data
from app.services.billing_rules import (
    can_create_campaign,
    get_gm_limits,
)
from app.services.world_generator import (
    defaults as wg_defaults,
    generator as wg_generator,
    validator as wg_validator,
)
from app.services.world_generator.generator import GenerationTimeoutError
from app.services.world_generator.validator import ValidationError
from app.services.user_capabilities import has_gm_capability
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


@login_required
def list_campaigns():
    gm_profile = GMProfile.query.filter_by(user_id=current_user.id).first()
    if not gm_profile:
        flash("GM profile not found.", "error")
        return redirect(url_for("main.campaigns"))

    campaigns = Campaign.query.filter_by(gm_profile_id=gm_profile.id).order_by(
        Campaign.created_at.asc()
    ).all()

    _campaign_cap, seat_cap, _label = get_gm_limits(gm_profile.user)

    campaigns_with_info = []
    for campaign in campaigns:
        member_count = (
            db.session.query(Player)
            .filter(
                Player.campaign_id == campaign.id,
                Player.is_npc.is_(False),
            )
            .count()
        )
        campaigns_with_info.append(
            {
                "campaign": campaign,
                "member_count": member_count,
                "seat_cap": seat_cap,
            }
        )

    try:
        active_campaign_id = int(session.get("campaign_id")) if session.get("campaign_id") else None
    except (TypeError, ValueError):
        active_campaign_id = None

    return render_template(
        "GM_view_campaigns.html",
        campaigns_info=campaigns_with_info,
        active_campaign_id=active_campaign_id,
    )


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
                    f"Campaign '{name}' created successfully with preseeded entities. "
                    "Players can join with the campaign code.",
                    "success",
                )
            except Exception as e:
                flash(
                    f"Campaign '{name}' created, but seeding encountered an error: {str(e)}",
                    "warning",
                )
        elif world_setup == "preset":
            flash(
                f"Campaign '{name}' created. Preset worlds are coming soon! "
                "Players can join with the campaign code.",
                "info",
            )
        else:
            flash(
                f"Campaign '{name}' created successfully with a blank slate. "
                "Players can join with the campaign code.",
                "success",
            )

        return redirect(url_for("main.campaigns"))

    return render_template("GM_add_campaign.html")


def _snapshot_campaign_for_analytics(campaign: Campaign) -> DeletedCampaignSimSnapshot:
    """Archive a Campaign's final simulation usage metrics before deletion.

    The snapshot row is added to the active session but not committed; it
    must commit atomically with the parent ``Campaign`` delete so a failed
    delete also rolls back the snapshot. Sourced exclusively from the
    server-side Campaign object (never from request input) to keep the
    write trustworthy regardless of caller context.
    """

    # Query directly — do not load ``campaign.simulation_state``. A loaded
    # one-to-one child makes SQLAlchemy emit ``UPDATE … SET campaign_id = NULL``
    # before the parent delete, which fails on NOT NULL ``campaign_id``.
    sim = None
    try:
        sim = SimulationState.query.filter_by(campaign_id=campaign.id).first()
    except OperationalError:
        log.debug(
            "simulation_state unavailable for delete snapshot (campaign_id=%s)",
            campaign.id,
            exc_info=True,
        )
    snapshot = DeletedCampaignSimSnapshot(
        gm_profile_id=campaign.gm_profile_id,
        campaign_id=campaign.id,
        campaign_name=campaign.name,
        system_type=campaign.system_type or "generic",
        campaign_created_at=getattr(campaign, "created_at", None),
        current_game_day=int(campaign.current_game_day or 1),
        days_simulated=max(0, int((campaign.current_game_day or 1) - 1)),
        sim_clicks_day=int(getattr(sim, "sim_clicks_day", 0) or 0) if sim else 0,
        sim_clicks_week=int(getattr(sim, "sim_clicks_week", 0) or 0) if sim else 0,
        sim_clicks_month=int(getattr(sim, "sim_clicks_month", 0) or 0) if sim else 0,
        sim_clicks_year=int(getattr(sim, "sim_clicks_year", 0) or 0) if sim else 0,
        sim_clicks_pause=int(getattr(sim, "sim_clicks_pause", 0) or 0) if sim else 0,
        last_tick_time=getattr(sim, "last_tick_time", None) if sim else None,
    )
    db.session.add(snapshot)
    return snapshot


def _purge_campaign_dependencies(campaign_id: int) -> None:
    """Remove campaign-scoped rows that block parent delete on legacy Postgres.

    ``shop_cities`` and several shop/item FKs were created without
    ``ON DELETE CASCADE``; simulated worlds also accumulate ``price_history``,
    markets, and logs. Bulk-delete by ``campaign_id`` (and junction rows by
    shop/city membership) before ``session.delete(campaign)``.
    """
    cid = campaign_id
    shop_ids = db.session.query(Shop.shop_id).filter(Shop.campaign_id == cid)
    city_ids = db.session.query(City.city_id).filter(City.campaign_id == cid)
    db.session.execute(
        shop_cities.delete().where(
            or_(
                shop_cities.c.shop_id.in_(shop_ids),
                shop_cities.c.city_id.in_(city_ids),
            )
        )
    )
    for model in (
        SimulationLog,
        SimRule,
        PriceHistory,
        ShopInventory,
        RegionalMarket,
        GlobalMarket,
        ModifierTarget,
        DemandModifier,
        MarketEvent,
        ResourceTransform,
        SimulationState,
        GMWorldState,
        CampaignWorldConfig,
    ):
        db.session.query(model).filter_by(campaign_id=cid).delete(
            synchronize_session=False
        )


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

    deleting_active_campaign = session.get("campaign_id") == campaign_id

    snapshot = None
    try:
        snapshot = _snapshot_campaign_for_analytics(campaign)
        campaign_item_ids = db.session.query(Item.item_id).filter(
            Item.campaign_id == campaign.id
        )
        PlayerInventory.query.filter(
            PlayerInventory.item_id.in_(campaign_item_ids)
        ).delete(synchronize_session=False)
        PlayerEquipment.query.filter(
            PlayerEquipment.item_id.in_(campaign_item_ids)
        ).update({PlayerEquipment.item_id: None}, synchronize_session=False)
        PlayerCharacterSheet.query.filter_by(campaign_id=campaign.id).delete(
            synchronize_session=False
        )
        Player.query.filter_by(campaign_id=campaign.id).update(
            {Player.campaign_id: None}, synchronize_session=False
        )
        _purge_campaign_dependencies(campaign.id)
        db.session.expire(campaign, ["simulation_state", "world_state"])
        db.session.delete(campaign)
        db.session.commit()
    except (IntegrityError, OperationalError) as exc:
        db.session.rollback()
        pg_detail = getattr(getattr(exc, "orig", None), "diag", None)
        constraint = getattr(pg_detail, "constraint_name", None) if pg_detail else None
        log.exception(
            "Campaign delete failed | campaign_id=%s gm_profile_id=%s "
            "constraint=%s detail=%s",
            campaign_id,
            gm_profile.id,
            constraint,
            getattr(exc, "orig", exc),
        )
        flash(
            "Could not delete this campaign. If it has been simulated or has players, "
            "contact support with the campaign name. "
            f"({type(exc).__name__})",
            "error",
        )
        return redirect(url_for("gm.view_campaigns"))
    except Exception:
        db.session.rollback()
        log.exception(
            "Campaign delete failed | campaign_id=%s gm_profile_id=%s",
            campaign_id,
            gm_profile.id,
        )
        flash("Could not delete this campaign. Please try again.", "error")
        return redirect(url_for("gm.view_campaigns"))

    logging.getLogger(__name__).info(
        "Campaign deleted | campaign_id=%s name=%r gm_profile_id=%s "
        "snapshot_id=%s days_simulated=%s",
        campaign_id,
        snapshot.campaign_name if snapshot else "?",
        snapshot.gm_profile_id if snapshot else gm_profile.id,
        getattr(snapshot, "snapshot_id", None),
        getattr(snapshot, "days_simulated", None),
    )
    if deleting_active_campaign:
        session.pop("campaign_id", None)
        session.pop("system_type", None)
        session.modified = True
        flash("Campaign deleted.", "success")
        return redirect(url_for("main.campaigns"))
    flash("Campaign deleted.", "success")
    return redirect(url_for("gm.view_campaigns"))


# ---------------------------------------------------------------------------
# World generation form (GET)
# ---------------------------------------------------------------------------
_RANGE_LABELS = {
    "num_cities": "Number of Cities",
    "num_regions": "Number of Regions",
    "global_item_pool_size": "Global Item Pool Size",
    "city_size_variation": "City Size Variation",
    "items_per_shop": "Items per Shop",
    "tech_magic_balance": "Magic <-> Tech Balance",
}

_SETTING_HINTS = {
    "num_regions": (
        "How many world regions are generated. Each region gets its own name and "
        "a rolled position on the magic–tech axis. The final count is random "
        "between your min and max."
    ),
    "num_cities": (
        "Towns and cities placed across those regions. More cities add travel "
        "hubs and shop locations but increase generation time and database size."
    ),
    "global_item_pool_size": (
        "Size of the master item catalog built once for the campaign. Every shop "
        "draws stock from this pool; a larger pool means more unique gear "
        "world-wide."
    ),
    "city_size_variation": (
        "Dual range (1–20): lower values bias toward hamlets and villages, "
        "higher values toward cities and megaplexes. Shop count per settlement "
        "comes from the catalog shops_per_size table for the rolled tier."
    ),
    "items_per_shop": (
        "How many items each shop stocks. Together with cities and shops per "
        "city, this drives the shop-inventory estimate shown below."
    ),
    "tech_magic_balance": (
        "Range for the fused magic-vs-technology axis (0 = high magic, "
        "10 = post-apocalyptic tech). Each region, item, and shop roll picks a "
        "value within your min–max; it affects naming, stats, and which items "
        "feel native vs imported in a city."
    ),
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

    from app.services.shop_roll.catalog import get_catalog

    catalog = get_catalog()
    return {
        "ranges": ranges,
        "labels": _RANGE_LABELS,
        "setting_hints": _SETTING_HINTS,
        "system_types": wg_defaults.SYSTEM_TYPES,
        "shop_inventory_cap": wg_defaults.SHOP_INVENTORY_CAP,
        "max_shops_per_city": catalog.max_shops_per_city(),
        "defaults_json": defaults_json,
        "form_values": {
            "campaign_name": override.get("campaign_name", ""),
            "system_type": override.get("system_type", "dnd5e"),
            "world_seed": override.get("world_seed", ""),
            "inventory_mode": override.get("inventory_mode", "axis"),
        },
    }


@login_required
def generate_world_form():
    """GET handler for `/gm/generate_world`.

    Only GMs may render this page. Anyone else is redirected to the
    main campaign selection screen.
    """
    if not has_gm_capability(current_user):
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
    if not has_gm_capability(current_user):
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

            result = wg_generator.generate(
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
        # psycopg2 attaches diagnostic data to exc.orig.diag — surfacing the
        # constraint name + table makes future "name conflict" reports
        # actionable without needing a debugger.
        diag = getattr(getattr(exc, "orig", None), "diag", None)
        constraint_name = getattr(diag, "constraint_name", None) if diag else None
        table_name = getattr(diag, "table_name", None) if diag else None
        pgcode = getattr(getattr(exc, "orig", None), "pgcode", None)
        log.warning(
            "world_generation_integrity_error gm=%s pgcode=%s table=%s constraint=%s err=%s",
            gm_profile.id,
            pgcode,
            table_name,
            constraint_name,
            exc,
        )
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
        "regions=%d cities=%d shops=%d items=%d inv=%d",
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
    if not has_gm_capability(current_user):
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
        "Players can join with the campaign code.",
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
    if not has_gm_capability(current_user):
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
    if not has_gm_capability(current_user):
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
