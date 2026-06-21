<<<<<<< HEAD
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.routes.handlers.gm_cities_handler import (
    view_cities, add_city, edit_city, delete_city
)
from app.routes.handlers.gm_shops_handler import (
    view_shops,
    add_shop,
    edit_shop,
    update_shop_basic,
    delete_shop,
    view_city_shops,
    view_shop_items,
    remove_item_from_shop,
)
from app.routes.handlers.gm_items_handler import (
    view_items, add_item, edit_item, item_detail, delete_item
)
from app.routes.handlers.gm_campaigns_handler import (
    list_campaigns,
    create_campaign,
    delete_campaign,
    sync_players_to_campaign,
)
from app.routes.handlers.gm_simulation_handler import (
    home,
    seed_world,
    run_simulation_tick,
    update_simulation_speed,
    run_period_stream,
    debug_form,
)
from app.routes.handlers.gm_players_handler import (
    list_players,
=======
import traceback

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from sqlalchemy.orm import selectinload, subqueryload
from sqlalchemy.exc import IntegrityError
from flask_login import login_required, current_user

from app.extensions import db, limiter
from app.models import City, Shop, Item, ShopInventory, Region, CampaignWorldConfig, ItemFolder
from app.services import species_compendium_service
from app.services.species_compendium_service import SpeciesValidationError
from app.services.items_catalog_service import (
    ItemsCatalogError,
    ensure_srd_items_for_campaign,
    list_campaign_items,
)
from app.services.shop_inventory_service import (
    ShopInventoryError,
    bulk_delete_items,
    bulk_remove_from_shop,
    bulk_rename_items,
    bulk_stock_items,
    items_blocked_from_delete,
    parse_id_list,
    upsert_shop_inventory,
)
from app.services.item_folder_service import (
    ItemFolderError,
    bulk_move_items_to_folder,
    create_folder,
    delete_folder,
    folders_as_tree,
    list_campaign_folders,
    rename_folder,
)
from app.routes.handlers.gm_helpers import (
    city_for_campaign_or_404,
    city_for_campaign_optional,
    item_for_campaign_or_404,
    shop_for_campaign_or_404,
    region_for_campaign_or_404,
    region_table_exists,
    active_campaign_id,
    require_active_campaign,
    purge_city_dependencies,
    purge_shop_dependencies,
)
from app.routes.handlers.gm_players_handler import (
    create_npc,
>>>>>>> GCP
    view_character,
    update_character,
    equip_item,
    unequip_item,
    update_inventory,
<<<<<<< HEAD
)

gm_bp = Blueprint("gm", __name__, url_prefix="/gm") 
=======
    remove_player_from_campaign as remove_player_from_campaign_handler,
    delete_npc_player as delete_npc_player_handler,
)
from app.routes.handlers.gm_market_handler import get_market_overview_data
from app.routes.handlers.gm_maps_handler import (
    get_world_map as get_world_map_handler,
    get_city_map as get_city_map_handler,
    post_marker as post_marker_handler,
    remove_marker as remove_marker_handler,
    post_poi as post_poi_handler,
    remove_poi as remove_poi_handler,
    post_world_background as post_world_background_handler,
    post_city_background as post_city_background_handler,
    get_map_image as get_map_image_handler,
)
from app.routes.handlers.gm_species_handler import (
    create_species_compendium as create_species_compendium_handler,
    get_species_compendium as get_species_compendium_handler,
    save_species_builder as save_species_builder_handler,
    species_builder as species_builder_handler,
    update_species_compendium as update_species_compendium_handler,
)
from app.routes.handlers.gm_classes_handler import (
    create_classes_compendium as create_classes_compendium_handler,
    get_classes_compendium as get_classes_compendium_handler,
    update_classes_compendium as update_classes_compendium_handler,
)
from app.routes.handlers.gm_spells_handler import (
    create_spells_compendium as create_spells_compendium_handler,
    get_spells_compendium as get_spells_compendium_handler,
    update_spells_compendium as update_spells_compendium_handler,
)
from app.routes.handlers.gm_simulation_handler import (
    home as gm_dashboard_home,
    seed_world,
    update_simulation_speed,
    run_period_stream,
    simulation_job_status,
    debug_form as gm_debug_form_handler,
)
from app.routes.handlers.gm_shops_handler import (
    update_shop_basic as update_shop_basic_handler,
    get_shop_city_panel_context,
    get_grouped_shops,
    get_linked_shop_ids_for_item,
    build_grouped_cities_for_shop_form,
)
from app.routes.handlers.gm_campaigns_handler import (
    list_campaigns,
    create_campaign,
    delete_campaign as delete_campaign_handler,
    generate_world_form as generate_world_form_handler,
    generate_world_submit as generate_world_submit_handler,
    skip_world_generation_submit as skip_world_generation_submit_handler,
    reveal_campaign_join_code as reveal_campaign_join_code_handler,
    post_redeem_player_code as post_redeem_player_code_handler,
    log_expansion_interest as log_expansion_interest_handler,
)
from app.services.world_generator.defaults import RANGE_SETTINGS, SCHEMA_VERSION
from app.services.world_generator.generator import (
    GenerationTimeoutError,
    generate_cities_for_empty_region,
    generate_shops_onward,
)
>>>>>>> GCP



def _partial_shop_gen_settings(campaign_id: int) -> dict:
    """Ranges + seed for `generate_shops_onward`, from world config or defaults."""
    cfg = CampaignWorldConfig.query.get(campaign_id)
    if cfg and isinstance(cfg.settings_json, dict) and cfg.settings_json.get("ranges"):
        sj = cfg.settings_json
        out = {
            "ranges": sj["ranges"],
            "world_seed": sj.get("world_seed"),
            "system_type": sj.get("system_type", "dnd5e"),
        }
        if cfg.world_seed is not None:
            out["world_seed"] = int(cfg.world_seed)
        return out

    def _pair(key: str):
        _floor, _ceil, dmin, dmax = RANGE_SETTINGS[key]
        return {"min": dmin, "max": dmax}

    return {
        "schema_version": SCHEMA_VERSION,
        "system_type": "dnd5e",
        "world_seed": None,
        "ranges": {k: _pair(k) for k in RANGE_SETTINGS},
    }


def _active_campaign_or_redirect():
    """Resolve the current GM's active campaign or return a redirect response."""
    gm_profile = current_user.gm_profile
    return require_active_campaign(gm_profile)


def _redirect_after_dashboard_action(default_endpoint: str = "gm.home"):
    anchor = (request.form.get("return_anchor") or "").strip().lstrip("#")
    dashboard_panes = {
        "map-pane-content",
        "market-pane-content",
        "regions-pane-content",
        "cities-pane-content",
        "shops-pane-content",
        "items-pane-content",
        "sim-pane-content",
        "players-npcs-pane-content",
        "species-pane-content",
        "classes-pane-content",
        "spells-pane-content",
        "battle-pane-content",
        "monsters-pane-content",
    }
    if anchor in dashboard_panes:
        return redirect(url_for("gm.home", _anchor=anchor))
    return redirect(request.referrer or url_for(default_endpoint))


@gm_bp.route("/")
@login_required
<<<<<<< HEAD
def gm_home():
    """Render the GM dashboard with simulation controls and status."""
    return home()
=======
def home():
    return gm_dashboard_home()


@gm_bp.route("/campaigns/market-volatility", methods=["POST"])
@login_required
def update_campaign_market_volatility():
    """Persist market volatility (0–10) for the active campaign."""
    from app.services.world_generator.campaign_settings import update_market_volatility

    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    level = request.form.get("market_volatility", type=int)
    if level is None:
        flash("Enter a market volatility value from 0 to 10.", "warning")
        return _redirect_after_dashboard_action()
    try:
        saved, _cfg = update_market_volatility(camp.id, level)
        db.session.commit()
        flash(f"Market volatility set to {saved}.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error saving market volatility: {e}", "danger")
    return _redirect_after_dashboard_action()


@gm_bp.route("/campaigns/supply-demand/toggle", methods=["POST"])
@login_required
def toggle_campaign_supply_demand():
    """Toggle daily sales + periodic restock on simulation ticks."""
    from app.services.world_generator.campaign_settings import toggle_supply_demand

    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir

    enabled, _cfg = toggle_supply_demand(camp.id)
    db.session.commit()
    if enabled:
        flash(
            "Supply On: each game-day tick applies daily sales and shop restocks.",
            "success",
        )
    else:
        flash(
            "Supply Off: ticks update prices only (no simulated sales or restock). "
            "Click again to turn supply back on.",
            "warning",
        )
    return _redirect_after_dashboard_action()


@gm_bp.route("/campaigns/debt/toggle", methods=["POST"])
@login_required
def toggle_campaign_debt():
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir

    camp.allow_player_debt = not bool(camp.allow_player_debt)
    db.session.commit()
    flash(
        "Debt On: players can buy items even if currency goes negative."
        if camp.allow_player_debt
        else "Debt Off: players cannot buy items that would go below 0 currency.",
        "success",
    )
    return _redirect_after_dashboard_action()


@gm_bp.route("/seed_world", methods=["POST"])
@login_required
def gm_seed_world():
    return seed_world()


@gm_bp.route("/species/build", methods=["GET"])
@login_required
def species_builder():
    return species_builder_handler()


@gm_bp.route("/species/build", methods=["POST"])
@login_required
def save_species_builder():
    return save_species_builder_handler()


@gm_bp.route("/species/compendium", methods=["GET"])
@login_required
def get_species_compendium():
    return get_species_compendium_handler()


@gm_bp.route("/species/compendium", methods=["POST"])
@login_required
def create_species_compendium():
    return create_species_compendium_handler()


@gm_bp.route("/species/compendium/<string:key>", methods=["POST"])
@login_required
def update_species_compendium(key):
    return update_species_compendium_handler(key)


@gm_bp.route("/classes/compendium", methods=["GET"])
@login_required
def get_classes_compendium():
    return get_classes_compendium_handler()


@gm_bp.route("/classes/compendium", methods=["POST"])
@login_required
def create_classes_compendium():
    return create_classes_compendium_handler()


@gm_bp.route("/classes/compendium/<string:key>", methods=["POST"])
@login_required
def update_classes_compendium(key):
    return update_classes_compendium_handler(key)


@gm_bp.route("/spells/compendium", methods=["GET"])
@login_required
def get_spells_compendium():
    return get_spells_compendium_handler()


@gm_bp.route("/spells/compendium", methods=["POST"])
@login_required
def create_spells_compendium():
    return create_spells_compendium_handler()


@gm_bp.route("/spells/compendium/<string:key>", methods=["POST"])
@login_required
def update_spells_compendium(key):
    return update_spells_compendium_handler(key)


@gm_bp.route("/character-creation/settings", methods=["GET"])
@login_required
@limiter.limit("60 per hour")
def get_gm_character_creation_settings():
    from app.routes.handlers.gm_character_creation_handler import (
        get_character_creation_settings,
    )

    return get_character_creation_settings()


@gm_bp.route("/character-creation/settings", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def post_gm_character_creation_settings():
    from app.routes.handlers.gm_character_creation_handler import (
        post_character_creation_settings,
    )

    return post_character_creation_settings()

>>>>>>> GCP

# --- Seeding Route ---
@gm_bp.route("/seed_world", methods=["POST"])
@login_required
def gm_seed_world():
    """Route to trigger the seeding of the GM's world data."""
    return seed_world()

<<<<<<< HEAD

# Cities routes
@gm_bp.route("/cities/")
@login_required
def gm_view_cities():
    """View all cities for the current GM"""
    return view_cities()

@gm_bp.route("/cities/add", methods=["GET", "POST"])
@login_required
def gm_add_city():
    """Add a new city"""
    return add_city()

@gm_bp.route("/cities/edit/<int:city_id>", methods=["GET", "POST"])
@login_required
def gm_edit_city(city_id):
    """Edit an existing city"""
    return edit_city(city_id)

@gm_bp.route("/cities/delete/<int:city_id>", methods=["POST"])
@login_required
def gm_delete_city(city_id):
    """Delete a city"""
    return delete_city(city_id)
=======
def _dashboard_tab_redirect(tab_id: str):
    return redirect(url_for("gm.home", _anchor=tab_id))


@gm_bp.route("/cities/")
@login_required
def view_cities():
    _camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    return _dashboard_tab_redirect("cities-pane-content")

@gm_bp.route("/cities/add", methods=["GET", "POST"])
@login_required
def add_city():
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    campaign_regions = _campaign_regions_for_city_forms()
    if request.method == "POST":
        name = request.form.get("name")
        size = request.form.get("size")
        population = request.form.get("population")
        region_specialty = (request.form.get("region") or "").strip()
        fk_id = _validated_region_fk_from_form()

        if not name or not size or not population:
            flash("Name, size, and population are required.", "danger")
            return render_template("GM_add_city.html", campaign_regions=campaign_regions)

        if fk_id:
            region_str = None
        else:
            if not region_specialty:
                flash("Choose a campaign region or a specialty.", "danger")
                return render_template("GM_add_city.html", campaign_regions=campaign_regions)
            region_str = region_specialty

        try:
            new_city = City(
                name=name,
                size=size,
                population=int(population),
                region=region_str,
                region_id=fk_id,
                campaign_id=camp.id,
            )
            db.session.add(new_city)
            db.session.commit()
            flash(f"City '{name}' added successfully!", "success")
            return redirect(url_for("gm.view_cities"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error adding city: {e}", "danger")

    return render_template("GM_add_city.html", campaign_regions=campaign_regions)

@gm_bp.route("/cities/edit/<int:city_id>", methods=["GET", "POST"])
@login_required
def edit_city(city_id):
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    city = city_for_campaign_or_404(city_id, camp.id)
    campaign_regions = _campaign_regions_for_city_forms()
    species_population_rows = species_compendium_service.city_species_population(
        camp.id, city.city_id, int(city.population or 0)
    )

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        size = (request.form.get("size") or "").strip()
        pop_raw = request.form.get("population")

        if not name or not size or pop_raw is None or str(pop_raw).strip() == "":
            flash("Name, size, and population are required.", "danger")
            return render_template(
                "GM_edit_city.html",
                city=city,
                campaign_regions=campaign_regions,
                species_population_rows=species_population_rows,
            )
        try:
            population = int(pop_raw)
        except (TypeError, ValueError):
            flash("Population must be a valid number.", "danger")
            return render_template(
                "GM_edit_city.html",
                city=city,
                campaign_regions=campaign_regions,
                species_population_rows=species_population_rows,
            )

        species_rows = []
        for key in request.form.getlist("species_key"):
            species_rows.append(
                {
                    "key": key,
                    "name": request.form.get(f"species_{key}_name"),
                    "population": request.form.get(f"species_{key}_population"),
                }
            )
        if species_rows:
            try:
                species_population_rows, population = (
                    species_compendium_service.update_city_species_population(
                        camp.id, city.city_id, species_rows
                    )
                )
            except SpeciesValidationError as exc:
                flash(str(exc), "danger")
                return render_template(
                    "GM_edit_city.html",
                    city=city,
                    campaign_regions=campaign_regions,
                    species_population_rows=species_population_rows,
                )

        fk_id = _validated_region_fk_from_form()
        if fk_id:
            city.region_id = fk_id
            city.region = None
        else:
            city.region_id = None
            city.region = (request.form.get("region") or "").strip() or None
            if not city.region:
                flash("Choose a campaign region or a specialty.", "danger")
                return render_template(
                    "GM_edit_city.html",
                    city=city,
                    campaign_regions=campaign_regions,
                    species_population_rows=species_population_rows,
                )

        city.name = name
        city.size = size
        city.population = population

        try:
            db.session.commit()
            flash("City updated successfully!", "success")
            return redirect(url_for("gm.view_cities"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating city: {e}", "danger")

    return render_template(
        "GM_edit_city.html",
        city=city,
        campaign_regions=campaign_regions,
        species_population_rows=species_population_rows,
    )

@gm_bp.route("/cities/delete/<int:city_id>", methods=["POST"])
@login_required
def delete_city(city_id):
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    city = city_for_campaign_or_404(city_id, camp.id)
    try:
        purge_city_dependencies(city.city_id)
        db.session.delete(city)
        db.session.commit()
        flash("City deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting city: {e}", "danger")
    return redirect(request.referrer or url_for("gm.home"))


def _parse_region_axis(raw):
    try:
        v = int(raw)
    except (TypeError, ValueError):
        v = 5
    return max(0, min(10, v))


def _unassigned_cities_for_campaign(campaign_id: int):
    """Cities in this campaign with no region_id (for assigning to a Region)."""
    return (
        City.query.filter_by(campaign_id=campaign_id, region_id=None)
        .order_by(City.name)
        .all()
    )


def _campaign_regions_for_city_forms():
    if not region_table_exists():
        return []
    cid = session.get("campaign_id")
    if not cid:
        return []
    return (
        Region.query.filter_by(campaign_id=cid)
        .order_by(Region.name)
        .all()
    )


def _validated_region_fk_from_form():
    """Region PK for active campaign from form `region_id`, or None."""
    raw = (request.form.get("region_id") or "").strip()
    if not raw or not region_table_exists():
        return None
    cid = session.get("campaign_id")
    if not cid:
        return None
    try:
        rid = int(raw)
    except (TypeError, ValueError):
        return None
    reg = Region.query.filter_by(id=rid, campaign_id=cid).first()
    return reg.id if reg else None


@gm_bp.route("/regions/add", methods=["GET", "POST"])
@login_required
def add_region():
    if not region_table_exists():
        flash("Region data is not available in this database.", "warning")
        return redirect(url_for("gm.home"))

    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    campaign_id = camp.id

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        axis = _parse_region_axis(request.form.get("axis_position"))

        if not name:
            flash("Region name is required.", "danger")
            return render_template(
                "GM_edit_region.html",
                mode="create",
                region=None,
                form_name="",
                form_axis=axis,
            )

        new_region = Region(
            name=name,
            campaign_id=campaign_id,
            local_flavor={"axis_position": axis},
        )
        try:
            db.session.add(new_region)
            db.session.commit()
            flash(f"Region '{name}' created.", "success")
            return redirect(url_for("gm.edit_region", region_id=new_region.id))
        except IntegrityError:
            db.session.rollback()
            flash("A region with that name already exists in this campaign.", "danger")
            return render_template(
                "GM_edit_region.html",
                mode="create",
                region=None,
                form_name=name,
                form_axis=axis,
            )

    return render_template("GM_edit_region.html", mode="create", region=None)


@gm_bp.route("/regions/edit/<int:region_id>", methods=["GET", "POST"])
@login_required
def edit_region(region_id):
    if not region_table_exists():
        flash("Region data is not available in this database.", "warning")
        return redirect(url_for("gm.home"))

    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir

    region = region_for_campaign_or_404(region_id, camp.id)
    unassigned_cities = _unassigned_cities_for_campaign(camp.id)

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        axis = _parse_region_axis(request.form.get("axis_position"))
        assign_ids = request.form.getlist("assign_city_ids")

        if not name:
            flash("Name cannot be empty.", "danger")
        else:
            region.name = name
            region.local_flavor = {"axis_position": axis}
            try:
                skipped_city_assignments = False
                for raw_id in assign_ids:
                    try:
                        cid = int(raw_id)
                    except (TypeError, ValueError):
                        skipped_city_assignments = True
                        continue
                    city = city_for_campaign_optional(cid, camp.id)
                    if city is None:
                        skipped_city_assignments = True
                        continue
                    if city.region_id is not None:
                        continue
                    city.region_id = region.id
                    city.region = None
                db.session.commit()
                if skipped_city_assignments:
                    flash(
                        "Region updated. Some cities were skipped (invalid, unavailable, or already assigned to a region).",
                        "warning",
                    )
                else:
                    flash("Region updated successfully.", "success")
            except IntegrityError:
                db.session.rollback()
                flash("Update failed: name conflict within this campaign.", "danger")

        unassigned_cities = _unassigned_cities_for_campaign(camp.id)

    return render_template(
        "GM_edit_region.html",
        mode="edit",
        region=region,
        unassigned_cities=unassigned_cities,
    )


@gm_bp.route("/regions/delete/<int:region_id>", methods=["POST"])
@login_required
def delete_region(region_id):
    if not region_table_exists():
        flash("Region data is not available in this database.", "warning")
        return redirect(url_for("gm.home"))

    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir

    region = region_for_campaign_or_404(region_id, camp.id)
    region_name = region.name
    try:
        City.query.filter_by(campaign_id=camp.id, region_id=region.id).update(
            {"region_id": None, "region": None},
            synchronize_session=False,
        )
        db.session.delete(region)
        db.session.commit()
        flash(f"Region '{region_name}' deleted. Its cities are now unassigned.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"Error deleting region: {exc}", "danger")

    return redirect(url_for("gm.home"))


@gm_bp.route("/regions/<int:region_id>/generate_cities", methods=["POST"])
@login_required
def generate_cities_for_region(region_id):
    """Create cities in-region only when it has none (world-config ranges)."""
    if not region_table_exists():
        flash("Region data is not available in this database.", "warning")
        return redirect(url_for("gm.home"))

    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    campaign_id = camp.id

    region_for_campaign_or_404(region_id, campaign_id)

    try:
        settings = _partial_shop_gen_settings(campaign_id)
        n_new = generate_cities_for_empty_region(
            campaign_id=campaign_id,
            region_id=region_id,
            settings=settings,
        )
        db.session.commit()
        if n_new:
            flash(f"Added {n_new} cities to this region.", "success")
        else:
            flash(
                "This region already has cities; no new cities were added. "
                "Use Generate shops to add shops to cities that do not have any yet.",
                "warning",
            )
    except GenerationTimeoutError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "warning")
    except Exception as exc:
        db.session.rollback()
        traceback.print_exc()
        flash(f"City generation failed: {exc}", "danger")

    return redirect(url_for("gm.edit_region", region_id=region_id))


@gm_bp.route("/regions/<int:region_id>/generate_shops", methods=["POST"])
@login_required
def generate_shops_for_region(region_id):
    """Shops + inventory + markets for cities in this region (cities must exist)."""
    if not region_table_exists():
        flash("Region data is not available in this database.", "warning")
        return redirect(url_for("gm.home"))

    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    campaign_id = camp.id

    region_for_campaign_or_404(region_id, campaign_id)

    try:
        settings = _partial_shop_gen_settings(campaign_id)
        result = generate_shops_onward(
            campaign_id=campaign_id,
            region_id=region_id,
            settings=settings,
        )
        db.session.commit()
        flash(
            f"Generated {result.n_shops} shops with {result.n_inventory_rows} "
            f"inventory rows for {result.n_cities} cities in this region.",
            "success",
        )
    except GenerationTimeoutError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "warning")
    except Exception as exc:
        db.session.rollback()
        traceback.print_exc()
        flash(f"Shop generation failed: {exc}", "danger")

    return redirect(url_for("gm.edit_region", region_id=region_id))

>>>>>>> GCP

# Shops routes
@gm_bp.route("/shops/")
@login_required
<<<<<<< HEAD
def gm_view_shops():
    """View all shops for the current GM"""
    return view_shops()

@gm_bp.route("/shops/add", methods=["GET", "POST"])
@login_required
def gm_add_shop():
    """Add a new shop"""
    return add_shop()

@gm_bp.route("/shops/edit/<int:shop_id>", methods=["GET", "POST"])
@login_required
def gm_edit_shop(shop_id):
    """Edit an existing shop"""
    return edit_shop(shop_id)

@gm_bp.route("/shops/update-basic/<int:shop_id>", methods=["POST"])
@login_required
def gm_update_shop_basic(shop_id):
    """Inline update of shop name and type only."""
    return update_shop_basic(shop_id)

@gm_bp.route("/shops/delete/<int:shop_id>", methods=["POST"])
@login_required
def gm_delete_shop(shop_id):
    """Delete a shop"""
    return delete_shop(shop_id)

@gm_bp.route("/shops/city/<int:city_id>/shops")
@login_required
def gm_view_city_shops(city_id):
    """View all shops in a specific city"""
    return view_city_shops(city_id)
=======
def view_shops():
    ctx = get_shop_city_panel_context(
        current_user.gm_profile, include_nav_toggles=True
    )
    return render_template("GM_view_shops.html", **ctx)


@gm_bp.route("/regions/compendium")
@login_required
def regions_compendium_api():
    """Campaign-scoped region summaries for the GM dashboard compendium."""
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    if not region_table_exists():
        return jsonify({"regions": [], "total": 0})

    rows = Region.query.filter_by(campaign_id=camp.id).order_by(Region.name).all()
    city_counts = {
        region_id: count
        for region_id, count in db.session.query(City.region_id, db.func.count(City.city_id))
        .filter(City.campaign_id == camp.id, City.region_id.isnot(None))
        .group_by(City.region_id)
        .all()
    }
    payload = []
    for region in rows:
        flavor = region.local_flavor if isinstance(region.local_flavor, dict) else {}
        payload.append(
            {
                "region_id": region.id,
                "name": region.name,
                "axis_position": flavor.get("axis_position"),
                "city_count": int(city_counts.get(region.id, 0)),
                "edit_url": url_for("gm.edit_region", region_id=region.id),
            }
        )
    return jsonify({"regions": payload, "total": len(payload)})


@gm_bp.route("/cities/compendium")
@login_required
def cities_compendium_api():
    """Campaign-scoped city summaries for the GM dashboard compendium."""
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir

    query = City.query.filter_by(campaign_id=camp.id).order_by(City.name)
    if region_table_exists():
        query = query.options(subqueryload(City.region_obj))
    rows = query.all()
    payload = []
    for city in rows:
        region_name = None
        if getattr(city, "region_obj", None) is not None:
            region_name = city.region_obj.name
        region_name = region_name or city.region or "Unassigned"
        payload.append(
            {
                "city_id": city.city_id,
                "name": city.name,
                "size": city.size,
                "population": city.population or 0,
                "region": region_name,
                "shop_count": len(city.shops or []),
                "edit_url": url_for("gm.edit_city", city_id=city.city_id),
            }
        )
    return jsonify({"cities": payload, "total": len(payload)})


@gm_bp.route("/shops/compendium")
@login_required
def shops_compendium_api():
    """Campaign-scoped shop summaries for the GM dashboard compendium."""
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir

    rows = (
        Shop.query.filter_by(campaign_id=camp.id)
        .options(selectinload(Shop.cities), selectinload(Shop.inventory))
        .order_by(Shop.name)
        .all()
    )
    payload = []
    for shop in rows:
        payload.append(
            {
                "shop_id": shop.shop_id,
                "name": shop.name,
                "type": shop.type,
                "cities": [city.name for city in sorted(shop.cities or [], key=lambda c: c.name or "")],
                "inventory_count": len(shop.inventory or []),
                "next_restock_day": shop.next_restock_day,
                "edit_url": url_for("gm.edit_shop", shop_id=shop.shop_id),
                "items_url": url_for("gm.view_shop_items", shop_id=shop.shop_id),
            }
        )
    return jsonify({"shops": payload, "total": len(payload)})

@gm_bp.route("/shops/add", methods=["GET", "POST"])
@login_required
def add_shop():
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    campaign_id = camp.id

    if request.method == "POST":
        shop_name = request.form.get("name")
        shop_type = request.form.get("type")
        city_ids = request.form.getlist("city_ids")

        try:
            from app.models import Campaign as CampaignModel
            from app.services.economy.supply_demand import seed_next_restock_day
            import random as _random

            camp_row = CampaignModel.query.filter_by(id=campaign_id).first()
            game_day = int(camp_row.current_game_day or 1) if camp_row else 1

            new_shop = Shop(
                name=shop_name,
                type=shop_type,
                campaign_id=campaign_id,
            )
            seed_next_restock_day(new_shop, game_day, _random.Random())
            db.session.add(new_shop)
            db.session.flush()

            for city_id in city_ids:
                try:
                    cid = int(city_id)
                    city = City.query.filter_by(
                        city_id=cid, campaign_id=campaign_id
                    ).first()
                    if city:
                        new_shop.cities.append(city)
                    else:
                        print(f"[WARNING] City ID {city_id} not found in campaign {campaign_id}.")
                except ValueError:
                    print(f"[ERROR] Invalid city_id value: {city_id}")

            db.session.commit()
            flash(f"Shop '{shop_name}' added successfully!", "success")

        except Exception as e:
            db.session.rollback()
            print("[ERROR] Exception occurred while adding shop:")
            traceback.print_exc()
            flash(f"Error adding shop: {e}", "danger")

        return redirect(url_for("gm.view_shops"))

    q = City.query.filter_by(campaign_id=campaign_id)
    if region_table_exists():
        q = q.options(subqueryload(City.region_obj))
    cities = q.order_by(City.name).all()
    grouped_cities = build_grouped_cities_for_shop_form(cities)
    panel_ctx = get_shop_city_panel_context(current_user.gm_profile)
    return render_template(
        "GM_add_shop.html",
        cities=cities,
        grouped_cities=grouped_cities,
        campaign_regions=panel_ctx["campaign_regions"],
        region_labels=panel_ctx["region_labels"],
    )

@gm_bp.route("/shops/edit/<int:shop_id>", methods=["GET", "POST"])
@login_required
def edit_shop(shop_id):
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    campaign_id = camp.id
    shop = shop_for_campaign_or_404(shop_id, campaign_id)

    if request.method == "POST":
        shop.name = request.form["name"]
        shop.type = request.form["type"]
        city_ids = request.form.getlist("city_ids")
        new_cities = []
        for city_id in city_ids:
            try:
                cid = int(city_id)
            except ValueError:
                continue
            city = City.query.filter_by(city_id=cid, campaign_id=campaign_id).first()
            if city:
                new_cities.append(city)
        shop.cities = new_cities
        try:
            db.session.commit()
            flash("Shop updated successfully!", "success")
            return redirect(url_for("gm.edit_shop", shop_id=shop.shop_id))
        except Exception as e:
            db.session.rollback()
            db.session.refresh(shop)
            flash(f"Error updating shop: {e}", "danger")

    q = City.query.filter_by(campaign_id=campaign_id)
    if region_table_exists():
        q = q.options(subqueryload(City.region_obj))
    cities = q.order_by(City.name).all()
    grouped_cities = build_grouped_cities_for_shop_form(cities)
    linked_city_ids = {c.city_id for c in shop.cities}
    panel_ctx = get_shop_city_panel_context(current_user.gm_profile)
    return render_template(
        "GM_edit_shop.html",
        shop=shop,
        cities=cities,
        grouped_cities=grouped_cities,
        linked_city_ids=linked_city_ids,
        campaign_regions=panel_ctx["campaign_regions"],
        region_labels=panel_ctx["region_labels"],
    )


@gm_bp.route("/shops/update-basic/<int:shop_id>", methods=["POST"])
@login_required
def update_shop_basic(shop_id):
    return update_shop_basic_handler(shop_id)


@gm_bp.route("/shops/delete/<int:shop_id>", methods=["POST"])
@login_required
def delete_shop(shop_id):
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    shop = shop_for_campaign_or_404(shop_id, camp.id)
    try:
        purge_shop_dependencies(shop.shop_id)
        db.session.delete(shop)
        db.session.commit()
        flash("Shop deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting shop: {e}", "danger")
    return redirect(request.referrer or url_for("gm.home"))

@gm_bp.route("/shops/city/<int:city_id>/shops")
@login_required
def view_city_shops(city_id):
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    city = city_for_campaign_or_404(city_id, camp.id)
    shops = city.shops
    return render_template("GM_view_city_shops.html", city=city, shops=shops)
>>>>>>> GCP

# Shop items routes
@gm_bp.route("/shops/<int:shop_id>/items")
@login_required
<<<<<<< HEAD
def gm_view_shop_items(shop_id):
    """View all items in a specific shop"""
    return view_shop_items(shop_id)

@gm_bp.route("/shops/remove_item/<int:shop_id>/<int:item_id>", methods=["POST"])
@login_required
def gm_remove_item_from_shop(shop_id, item_id):
    """Remove an item from a shop's inventory"""
    return remove_item_from_shop(shop_id, item_id)
=======
def view_shop_items(shop_id):
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    shop = shop_for_campaign_or_404(shop_id, camp.id)
    city = shop.cities[0] if shop.cities else None
    if (getattr(camp, "system_type", None) or "").lower() == "dnd5e":
        try:
            ensure_srd_items_for_campaign(camp.id)
            db.session.commit()
        except ItemsCatalogError:
            db.session.rollback()
        except Exception:
            db.session.rollback()
    shop_inventory = ShopInventory.query.filter_by(
        shop_id=shop_id, campaign_id=camp.id
    ).all()
    item_ids = [inv.item_id for inv in shop_inventory]
    items = Item.query.filter(Item.item_id.in_(item_ids)).all() if item_ids else []
    grouped_shops, city_shop_meta = get_grouped_shops(current_user.gm_profile)
    return render_template(
        "GM_view_shop_items.html",
        items=items,
        shop=shop,
        city=city,
        campaign_id=camp.id,
        grouped_shops=grouped_shops,
        city_shop_meta=city_shop_meta,
    )


@gm_bp.route("/shops/<int:shop_id>/items/add", methods=["POST"])
@login_required
def add_catalog_item_to_shop(shop_id):
    """Stock an existing campaign catalog row in a shop (no duplicate Item rows)."""
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    shop = shop_for_campaign_or_404(shop_id, camp.id)
    item_id = request.form.get("item_id", type=int)
    stock = request.form.get("stock", type=int)
    dynamic_price = request.form.get("dynamic_price", type=float)
    if item_id is None:
        flash("Select a catalog item.", "warning")
        return redirect(url_for("gm.view_shop_items", shop_id=shop_id))
    item = Item.query.filter_by(item_id=item_id, campaign_id=camp.id).first()
    if not item:
        flash("Item not found in this campaign catalog.", "danger")
        return redirect(url_for("gm.view_shop_items", shop_id=shop_id))
    if stock is None:
        stock = 0
    if dynamic_price is None:
        dynamic_price = float(item.base_price or 0)
    try:
        upsert_shop_inventory(
            camp.id,
            shop_id=shop.shop_id,
            item_id=item_id,
            stock=int(stock),
            dynamic_price=dynamic_price,
        )
        db.session.commit()
        flash(f"Stocked {item.name} in {shop.name}.", "success")
    except ShopInventoryError as e:
        db.session.rollback()
        flash(str(e), "danger")
    except Exception as e:
        db.session.rollback()
        flash(f"Error stocking item: {e}", "danger")
    return redirect(url_for("gm.view_shop_items", shop_id=shop_id))

@gm_bp.route("/shops/remove_item/<int:shop_id>/<int:item_id>", methods=["POST"])
@login_required
def remove_item_from_shop(shop_id, item_id):
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    shop_for_campaign_or_404(shop_id, camp.id)
    try:
        inventory = ShopInventory.query.filter_by(
            shop_id=shop_id, item_id=item_id, campaign_id=camp.id
        ).first()
        if inventory:
            db.session.delete(inventory)
            db.session.commit()
            flash("Item removed from shop successfully!", "success")
        else:
            flash("Item not found in shop.", "warning")
    except Exception as e:
        db.session.rollback()
        flash(f"Error removing item from shop: {e}", "danger")
    return redirect(url_for("gm.view_shop_items", shop_id=shop_id))

#items routes
>>>>>>> GCP

# Items routes
@gm_bp.route("/items/")
@login_required
<<<<<<< HEAD
def gm_view_items():
    """View all items for the current GM"""
    return view_items()

@gm_bp.route("/items/add", methods=["GET", "POST"])
@login_required
def gm_add_item():
    """Add a new item"""
    return add_item()
=======
def view_items():
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    if (getattr(camp, "system_type", None) or "").lower() == "dnd5e":
        try:
            ensure_srd_items_for_campaign(camp.id)
            db.session.commit()
        except ItemsCatalogError:
            db.session.rollback()
        except Exception:
            db.session.rollback()
    q_text = (request.args.get("q") or "").strip()
    page = request.args.get("page", 1, type=int)
    limit = request.args.get("limit", 50, type=int)
    folder_filter = request.args.get("folder_id", type=int)
    uncategorized = request.args.get("uncategorized") == "1"
    query = Item.query.filter_by(campaign_id=camp.id).order_by(Item.name).options(
        selectinload(Item.inventory)
        .selectinload(ShopInventory.shop)
        .selectinload(Shop.cities),
        selectinload(Item.folder),
    )
    if folder_filter is not None:
        query = query.filter(Item.folder_id == folder_filter)
    elif uncategorized:
        query = query.filter(Item.folder_id.is_(None))
    if q_text:
        needle = f"%{q_text.lower()}%"
        query = query.filter(db.func.lower(Item.name).like(needle))
    total = query.count()
    page = max(1, page or 1)
    limit = max(1, min(100, limit or 50))
    items = query.offset((page - 1) * limit).limit(limit).all()
    for item in items:
        item.distinct_shop_count = len(
            {inv.shop_id for inv in item.inventory if inv.shop_id is not None}
        )
    pages = max(1, (total + limit - 1) // limit)
    folders = list_campaign_folders(camp.id)
    folder_tree = folders_as_tree(camp.id)
    grouped_shops, city_shop_meta = get_grouped_shops(current_user.gm_profile)
    return render_template(
        "GM_view_items.html",
        items=items,
        q=q_text,
        page=page,
        pages=pages,
        total=total,
        limit=limit,
        folders=folders,
        folder_tree=folder_tree,
        folder_filter=folder_filter,
        uncategorized=uncategorized,
        grouped_shops=grouped_shops,
        city_shop_meta=city_shop_meta,
    )


@gm_bp.route("/items/catalog")
@login_required
def items_catalog_api():
    """Paginated JSON catalog for GM item/shop pickers."""
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    if (getattr(camp, "system_type", None) or "").lower() == "dnd5e":
        try:
            ensure_srd_items_for_campaign(camp.id)
            db.session.commit()
        except ItemsCatalogError:
            db.session.rollback()
        except Exception:
            db.session.rollback()
    payload = list_campaign_items(
        camp.id,
        q=request.args.get("q") or "",
        category=request.args.get("category") or "",
        folder_id=request.args.get("folder_id", type=int),
        uncategorized_only=request.args.get("uncategorized") == "1",
        page=request.args.get("page", 1, type=int),
        limit=request.args.get("limit", 50, type=int),
    )
    return jsonify(payload)

@gm_bp.route("/items/add", methods=["GET", "POST"])
@login_required
def add_item():
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    campaign_id = camp.id

    if request.method == "POST":
        catalog_item_id = request.form.get("catalog_item_id", type=int)
        if catalog_item_id:
            existing = Item.query.filter_by(
                item_id=catalog_item_id, campaign_id=campaign_id
            ).first()
            if not existing:
                flash("Selected catalog item was not found.", "danger")
                return redirect(url_for("gm.add_item"))
            shop_ids = request.form.getlist("shop_ids")
            stock = request.form.get("stock", type=int)
            if stock is None:
                stock = 0
            dynamic_price = request.form.get("dynamic_price", type=float)
            if dynamic_price is None:
                dynamic_price = float(existing.base_price or 0)
            try:
                for shop_id in shop_ids:
                    try:
                        sid = int(shop_id)
                        shop = Shop.query.filter_by(
                            shop_id=sid, campaign_id=campaign_id
                        ).first()
                        if not shop:
                            continue
                        inv = ShopInventory.query.filter_by(
                            shop_id=sid,
                            item_id=existing.item_id,
                            campaign_id=campaign_id,
                        ).first()
                        if inv:
                            inv.stock = stock
                            inv.dynamic_price = dynamic_price
                        else:
                            db.session.add(
                                ShopInventory(
                                    shop_id=sid,
                                    item_id=existing.item_id,
                                    campaign_id=campaign_id,
                                    stock=stock,
                                    dynamic_price=dynamic_price,
                                )
                            )
                    except ValueError:
                        continue
                db.session.commit()
                flash(f"Catalog item '{existing.name}' linked to selected shops.", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Error linking catalog item: {e}", "danger")
            return redirect(url_for("gm.view_items"))

        name = request.form.get("name")
        item_type = request.form.get("type")
        rarity = request.form.get("rarity")
        base_price = request.form.get("base_price", type=float)
        description = request.form.get("description")
        shop_ids = request.form.getlist("shop_ids")

        stock = request.form.get("stock", type=int)
        if stock is None:
            stock = 0

        dynamic_price = request.form.get("dynamic_price", type=float)
        if dynamic_price is None:
            dynamic_price = 0

        try:
            import json

            stats_payload = {}
            raw_props = request.form.get("properties_json")
            if raw_props:
                try:
                    stats_payload = json.loads(raw_props)
                except json.JSONDecodeError:
                    stats_payload = {}
            new_item = Item(
                name=name,
                type=item_type,
                rarity=rarity,
                base_price=base_price,
                description=description,
                campaign_id=campaign_id,
                content_source="gm_custom",
                stats={
                    "category": "gm_custom",
                    "automation": "manual",
                    "gm_edited": True,
                    "type_data": stats_payload if isinstance(stats_payload, dict) else {},
                },
            )

            db.session.add(new_item)
            db.session.flush()

            for shop_id in shop_ids:
                try:
                    sid = int(shop_id)
                    shop = Shop.query.filter_by(
                        shop_id=sid, campaign_id=campaign_id
                    ).first()
                    if shop:
                        entry = ShopInventory(
                            shop_id=shop.shop_id,
                            item_id=new_item.item_id,
                            campaign_id=campaign_id,
                            stock=stock,
                            dynamic_price=dynamic_price,
                        )
                        db.session.add(entry)
                    else:
                        print(f"[WARNING] Shop ID {sid} not found in campaign {campaign_id}.")
                except ValueError:
                    print(f"[ERROR] Invalid shop_id: {shop_id}")

            db.session.commit()
            flash(f"Item '{name}' added successfully!", "success")

        except Exception as e:
            db.session.rollback()
            print("[ERROR] Exception while adding item:")
            traceback.print_exc()
            flash(f"Error adding item: {e}", "danger")

        return redirect(url_for("gm.view_items"))

    grouped_shops, city_shop_meta = get_grouped_shops(current_user.gm_profile)
    is_dnd5e = (getattr(camp, "system_type", None) or "").lower() == "dnd5e"
    if is_dnd5e:
        try:
            ensure_srd_items_for_campaign(campaign_id)
            db.session.commit()
        except ItemsCatalogError:
            db.session.rollback()
        except Exception:
            db.session.rollback()
    return render_template(
        "GM_add_item.html",
        grouped_shops=grouped_shops,
        city_shop_meta=city_shop_meta,
        is_dnd5e=is_dnd5e,
        campaign_id=campaign_id,
    )
>>>>>>> GCP


@gm_bp.route("/items/edit/<int:item_id>", methods=["GET", "POST"])
@login_required
<<<<<<< HEAD
def gm_edit_item(item_id):
    """Edit an existing item"""
    return edit_item(item_id)

@gm_bp.route("/items/detail/<int:item_id>")
@login_required
def gm_item_detail(item_id):
    """View detailed information about an item"""
    return item_detail(item_id)

@gm_bp.route("/items/delete/<int:item_id>", methods=["POST"])
@login_required
def gm_delete_item(item_id):
    """Delete an item"""
    return delete_item(item_id) 


# Campaign routes
@gm_bp.route("/campaigns/")
@login_required
def gm_view_campaigns():
    """View all campaigns for the current GM."""
    return list_campaigns()


@gm_bp.route("/campaigns/add", methods=["GET", "POST"])
@login_required
def gm_add_campaign():
    """Create a new campaign for the current GM."""
    return create_campaign()


@gm_bp.route("/campaigns/sync/<int:campaign_id>", methods=["POST"])
@login_required
def gm_sync_players_to_campaign(campaign_id):
    """Sync all players to a campaign."""
    return sync_players_to_campaign(campaign_id)


@gm_bp.route("/campaigns/delete/<int:campaign_id>", methods=["POST"])
@login_required
def gm_delete_campaign(campaign_id):
    """Delete a campaign."""
    return delete_campaign(campaign_id)

@gm_bp.route("/debug/form", methods=["POST"])
def gm_debug_form():
    """Debug form submission"""
    return debug_form()



# Simulation routes
@gm_bp.route("/simulation/tick", methods=["POST"])
@login_required
def gm_run_simulation_tick():
    """Execute one simulation tick manually from the GM dashboard"""
    return run_simulation_tick()

=======
def edit_item(item_id):
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    item = item_for_campaign_or_404(item_id, camp.id)

    if request.method == "POST":
        item.name = request.form.get("name")
        item.type = request.form.get("type")
        item.rarity = request.form.get("rarity")
        item.base_price = request.form.get("base_price")
        item.description = request.form.get("description")
        stats = item.stats if isinstance(item.stats, dict) else {}
        stats["gm_edited"] = True
        item.stats = stats
        if item.content_source != "srd_5_1":
            item.content_source = "gm_custom"
        
        try:
            db.session.commit()
            flash("Item updated successfully!", "success")
            return redirect(url_for("gm.view_items"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating item: {e}", "danger")

    grouped_shops, city_shop_meta = get_grouped_shops(current_user.gm_profile)
    linked_shop_ids = get_linked_shop_ids_for_item(item.item_id)
    return render_template(
        "GM_edit_item.html",
        item=item,
        grouped_shops=grouped_shops,
        city_shop_meta=city_shop_meta,
        linked_shop_ids=linked_shop_ids,
    )

@gm_bp.route("/items/detail/<int:item_id>")
@login_required
def item_detail(item_id):
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    item = item_for_campaign_or_404(item_id, camp.id)
    grouped_shops, _city_shop_meta = get_grouped_shops(current_user.gm_profile)
    linked_shop_ids = get_linked_shop_ids_for_item(item.item_id)
    return render_template(
        "GM_item_detail.html",
        item=item,
        grouped_shops=grouped_shops,
        linked_shop_ids=linked_shop_ids,
    )

@gm_bp.route("/items/delete/<int:item_id>", methods=["POST"])
@login_required
def delete_item(item_id):
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    item = item_for_campaign_or_404(item_id, camp.id)
    blocked = items_blocked_from_delete(camp.id, [item_id])
    if item_id in blocked:
        flash(blocked[item_id], "danger")
        return redirect(url_for("gm.view_items"))
    try:
        db.session.delete(item)
        db.session.commit()
        flash("Item deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting item: {e}", "danger")
    return redirect(url_for("gm.view_items"))


@gm_bp.route("/items/bulk/stock", methods=["POST"])
@login_required
def bulk_stock_items_route():
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    item_ids = parse_id_list(request.form.getlist("item_ids"))
    shop_ids = parse_id_list(request.form.getlist("shop_ids"))
    stock = request.form.get("stock", type=int)
    if stock is None:
        stock = 1
    dynamic_price = request.form.get("dynamic_price", type=float)
    try:
        result = bulk_stock_items(
            camp.id,
            item_ids=item_ids,
            shop_ids=shop_ids,
            stock=stock,
            dynamic_price=dynamic_price,
        )
        if result.errors and result.processed == 0:
            flash("; ".join(result.errors), "danger")
        else:
            db.session.commit()
            msg = f"Stocked {result.processed} shop-item link(s)."
            if result.skipped:
                msg += f" Skipped {result.skipped}."
            flash(msg, "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error stocking items: {e}", "danger")
    return redirect(request.referrer or url_for("gm.view_items"))


@gm_bp.route("/shops/<int:shop_id>/items/bulk-remove", methods=["POST"])
@login_required
def bulk_remove_shop_items(shop_id):
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    shop_for_campaign_or_404(shop_id, camp.id)
    item_ids = parse_id_list(request.form.getlist("item_ids"))
    try:
        result = bulk_remove_from_shop(camp.id, shop_id=shop_id, item_ids=item_ids)
        if result.errors and result.processed == 0:
            flash("; ".join(result.errors), "danger")
        else:
            db.session.commit()
            flash(f"Removed {result.processed} item(s) from shop.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error removing items: {e}", "danger")
    return redirect(url_for("gm.view_shop_items", shop_id=shop_id))


@gm_bp.route("/items/bulk/delete", methods=["POST"])
@login_required
def bulk_delete_items_route():
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    item_ids = parse_id_list(request.form.getlist("item_ids"))
    try:
        result = bulk_delete_items(camp.id, item_ids)
        if result.errors and result.processed == 0:
            flash("; ".join(result.errors[:5]), "danger")
        else:
            db.session.commit()
            msg = f"Deleted {result.processed} item(s)."
            if result.skipped:
                msg += f" Skipped {result.skipped} (stocked or player-owned)."
            flash(msg, "success" if result.processed else "warning")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting items: {e}", "danger")
    return redirect(request.referrer or url_for("gm.view_items"))


@gm_bp.route("/items/bulk/rename", methods=["POST"])
@login_required
def bulk_rename_items_route():
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    item_ids = parse_id_list(request.form.getlist("item_ids"))
    try:
        result = bulk_rename_items(
            camp.id,
            item_ids,
            prefix=request.form.get("prefix") or "",
            suffix=request.form.get("suffix") or "",
            find_text=request.form.get("find_text") or "",
            replace_text=request.form.get("replace_text") or "",
        )
        if result.errors and result.processed == 0:
            flash("; ".join(result.errors), "danger")
        else:
            db.session.commit()
            flash(f"Renamed {result.processed} item(s).", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error renaming items: {e}", "danger")
    return redirect(request.referrer or url_for("gm.view_items"))


@gm_bp.route("/items/folders", methods=["GET"])
@login_required
def list_item_folders_api():
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    return jsonify({"folders": folders_as_tree(camp.id)})


@gm_bp.route("/items/folders/add", methods=["POST"])
@login_required
def add_item_folder():
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    try:
        create_folder(
            camp.id,
            name=request.form.get("name") or "",
            parent_id=request.form.get("parent_id", type=int),
            sort_order=request.form.get("sort_order", type=int) or 0,
        )
        db.session.commit()
        flash("Folder created.", "success")
    except ItemFolderError as e:
        db.session.rollback()
        flash(str(e), "danger")
    except Exception as e:
        db.session.rollback()
        flash(f"Error creating folder: {e}", "danger")
    return redirect(request.referrer or url_for("gm.view_items"))


@gm_bp.route("/items/folders/<int:folder_id>/rename", methods=["POST"])
@login_required
def rename_item_folder(folder_id):
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    try:
        rename_folder(camp.id, folder_id, name=request.form.get("name") or "")
        db.session.commit()
        flash("Folder renamed.", "success")
    except ItemFolderError as e:
        db.session.rollback()
        flash(str(e), "danger")
    except Exception as e:
        db.session.rollback()
        flash(f"Error renaming folder: {e}", "danger")
    return redirect(request.referrer or url_for("gm.view_items"))


@gm_bp.route("/items/folders/<int:folder_id>/delete", methods=["POST"])
@login_required
def delete_item_folder_route(folder_id):
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    try:
        delete_folder(camp.id, folder_id)
        db.session.commit()
        flash("Folder deleted. Items moved to uncategorized.", "success")
    except ItemFolderError as e:
        db.session.rollback()
        flash(str(e), "danger")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting folder: {e}", "danger")
    return redirect(request.referrer or url_for("gm.view_items"))


@gm_bp.route("/items/bulk/move-folder", methods=["POST"])
@login_required
def bulk_move_items_folder_route():
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    item_ids = parse_id_list(request.form.getlist("item_ids"))
    raw_folder = request.form.get("folder_id")
    folder_id = None if raw_folder in (None, "", "none") else int(raw_folder)
    try:
        result = bulk_move_items_to_folder(camp.id, item_ids, folder_id)
        if result.errors and result.processed == 0:
            flash("; ".join(result.errors), "danger")
        else:
            db.session.commit()
            flash(f"Moved {result.processed} item(s) to folder.", "success")
    except (ValueError, ItemFolderError) as e:
        db.session.rollback()
        flash(str(e), "danger")
    except Exception as e:
        db.session.rollback()
        flash(f"Error moving items: {e}", "danger")
    return redirect(request.referrer or url_for("gm.view_items"))


@gm_bp.route("/items/templates", methods=["GET"])
@login_required
def item_templates_page():
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    system = (getattr(camp, "system_type", None) or "").lower()
    templates = []
    if system == "dnd5e":
        from app.services.character_creation.srd_item_manifest import SRD_ITEM_COUNT

        templates.append(
            {
                "key": "srd_5_1",
                "label": "D&D 5e SRD 5.1 (OGL)",
                "description": f"{SRD_ITEM_COUNT} weapons, armor, gear, and wondrous items.",
                "available": True,
            }
        )
    return render_template(
        "GM_item_templates.html",
        campaign=camp,
        templates=templates,
    )


@gm_bp.route("/items/templates/import", methods=["POST"])
@login_required
def import_item_template():
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    template_key = (request.form.get("template_key") or "").strip()
    if template_key != "srd_5_1":
        flash("Unknown or unsupported item template.", "danger")
        return redirect(url_for("gm.item_templates_page"))
    if (getattr(camp, "system_type", None) or "").lower() != "dnd5e":
        flash("SRD 5.1 items are only available for D&D 5e campaigns.", "warning")
        return redirect(url_for("gm.item_templates_page"))
    try:
        counts = ensure_srd_items_for_campaign(camp.id)
        db.session.commit()
        flash(
            f"Imported SRD items: {counts['inserted']} new, "
            f"{counts['updated']} updated, {counts['skipped']} skipped (GM edits preserved).",
            "success",
        )
    except ItemsCatalogError as e:
        db.session.rollback()
        flash(str(e), "danger")
    except Exception as e:
        db.session.rollback()
        flash(f"Error importing template: {e}", "danger")
    return redirect(url_for("gm.view_items"))

@gm_bp.route("/debug/form", methods=["POST"])
def gm_debug_form():
    return gm_debug_form_handler()


# Campaign routes
@gm_bp.route("/campaigns/")
@login_required
def view_campaigns():
    return list_campaigns()


@gm_bp.route("/campaigns/add", methods=["GET", "POST"])
@login_required
def add_campaign():
    return create_campaign()


@gm_bp.route("/campaigns/delete/<int:campaign_id>", methods=["POST"])
@login_required
def delete_campaign(campaign_id):
    return delete_campaign_handler(campaign_id)


@gm_bp.route("/campaigns/<int:campaign_id>/reveal-code", methods=["GET"])
@login_required
@limiter.limit("60 per hour")
def reveal_campaign_join_code(campaign_id):
    return reveal_campaign_join_code_handler(campaign_id)


@gm_bp.route("/campaigns/<int:campaign_id>/redeem_player_code", methods=["POST"])
@login_required
@limiter.limit("3 per hour")
def redeem_player_code_route(campaign_id):
    return post_redeem_player_code_handler(campaign_id)


@gm_bp.route("/expansion-interest", methods=["POST"])
@login_required
@limiter.limit("10 per hour")
def log_expansion_interest():
    return log_expansion_interest_handler()


@gm_bp.route("/players/<int:player_id>/remove-from-campaign", methods=["POST"])
@login_required
def remove_player_from_campaign(player_id):
    return remove_player_from_campaign_handler(player_id)


@gm_bp.route("/npcs/<int:player_id>/delete", methods=["POST"])
@login_required
def delete_npc_player(player_id):
    return delete_npc_player_handler(player_id)


# World generation (Phase 1) -- GM-only, rate-limited POST
@gm_bp.route("/generate_world", methods=["GET"])
@login_required
def generate_world_form():
    return generate_world_form_handler()


@gm_bp.route("/generate_world", methods=["POST"])
@login_required
@limiter.limit("3 per minute")
def generate_world_submit():
    return generate_world_submit_handler()


@gm_bp.route("/generate_world/skip", methods=["POST"])
@login_required
def skip_world_generation_submit():
    return skip_world_generation_submit_handler()


@gm_bp.route("/market-overview", methods=["GET"])
@login_required
def gm_market_overview():
    """Campaign-wide item price/stock overview for the GM dashboard."""
    return get_market_overview_data()


# GM interactive maps -- presentation/editor state only, never simulation
# state. Campaign authority always derives from the GM session.
@gm_bp.route("/maps/world", methods=["GET"])
@login_required
def gm_map_world():
    return get_world_map_handler()


@gm_bp.route("/maps/cities/<int:city_id>", methods=["GET"])
@login_required
def gm_map_city(city_id):
    return get_city_map_handler(city_id)


@gm_bp.route("/maps/markers", methods=["POST"])
@login_required
def gm_map_marker_upsert():
    return post_marker_handler()


@gm_bp.route("/maps/markers/remove", methods=["POST"])
@login_required
def gm_map_marker_remove():
    return remove_marker_handler()


@gm_bp.route("/maps/pois", methods=["POST"])
@login_required
def gm_map_poi_upsert():
    return post_poi_handler()


@gm_bp.route("/maps/pois/remove", methods=["POST"])
@login_required
def gm_map_poi_remove():
    return remove_poi_handler()


@gm_bp.route("/maps/world/background", methods=["POST"])
@login_required
@limiter.limit("10 per minute")
def gm_map_world_background():
    return post_world_background_handler()


@gm_bp.route("/maps/cities/<int:city_id>/background", methods=["POST"])
@login_required
@limiter.limit("10 per minute")
def gm_map_city_background(city_id):
    return post_city_background_handler(city_id)


@gm_bp.route("/maps/image/<int:canvas_id>", methods=["GET"])
@login_required
def gm_map_image(canvas_id):
    return get_map_image_handler(canvas_id)


# Simulation routes — Day/Week/Month/Year all flow through `run_period_stream`
# (Celery + Redis lock + ACID batch). The synchronous /simulation/tick endpoint
# was retired so every period shares one commit/rollback/lock policy; see the
# year-batch-acid and sim-unify-entrypoints todos.
>>>>>>> GCP
@gm_bp.route("/simulation/speed", methods=["POST"])
@login_required
def gm_update_simulation_speed():
    """Pause the simulation engine (period runs use the streaming endpoint)."""
    return update_simulation_speed()


@gm_bp.route("/simulation/run-period", methods=["POST"])
@login_required
def gm_simulation_run_period():
    """Run a simulation period as NDJSON (one line per game day)."""
    return run_period_stream()

<<<<<<< HEAD
=======
@gm_bp.route("/simulation/jobs/<job_id>", methods=["GET"])
@login_required
def gm_simulation_job_status(job_id: str):
    """Return background simulation job status for polling UI."""
    return simulation_job_status(job_id)

>>>>>>> GCP

# Player / Character management routes
@gm_bp.route("/players/")
@login_required
def gm_view_players():
<<<<<<< HEAD
    """List players and characters for the current campaign."""
    return list_players()
=======
    """Show the dashboard Players & NPCs pane instead of the legacy manager page."""
    return _dashboard_tab_redirect("players-npcs-pane-content")


@gm_bp.route("/npcs/create", methods=["GET", "POST"])
@login_required
def gm_create_npc():
    """Create a GM-only NPC (Player row with no User) in the active campaign."""
    return create_npc()
>>>>>>> GCP


@gm_bp.route("/characters/<int:character_id>")
@login_required
def gm_view_character(character_id):
    """View and edit a specific character as GM."""
    return view_character(character_id)


@gm_bp.route("/characters/<int:character_id>/update", methods=["POST"])
@login_required
def gm_update_character(character_id):
    """Apply GM-side updates to a character."""
    return update_character(character_id)


@gm_bp.route("/characters/<int:character_id>/equip", methods=["POST"])
@login_required
def gm_equip_item_for_character(character_id):
    """Equip an item for a character (GM-side)."""
    return equip_item(character_id)


@gm_bp.route("/characters/<int:character_id>/unequip", methods=["POST"])
@login_required
def gm_unequip_item_for_character(character_id):
    """Unequip an item from a character slot (GM-side)."""
    return unequip_item(character_id)


@gm_bp.route("/characters/<int:character_id>/inventory/update", methods=["POST"])
@login_required
def gm_update_inventory_for_character(character_id):
    """Adjust a character's player inventory (GM-side)."""
    return update_inventory(character_id)


<<<<<<< HEAD
# # Resource Node routes
# @gm_bp.route("/resource_nodes/")
# @login_required
# def view_resource_nodes():
#     nodes = ResourceNode.query.filter_by(gm_profile_id=current_user.gm_profile.id).all()
#     return render_template("GM_view_resource_nodes.html", nodes=nodes)

# @gm_bp.route("/resource_nodes/add", methods=["GET", "POST"])
# @login_required
# def add_resource_node():
#     if request.method == "POST":
#         name = request.form.get("name")
#         type = request.form.get("type")
#         production_rate = float(request.form.get("production_rate"))
#         quality = float(request.form.get("quality"))
#         city_id = int(request.form.get("city_id"))
#         item_id = int(request.form.get("item_id"))

#         if not all([name, type, production_rate, quality, city_id, item_id]):
#             flash("All fields are required!", "danger")
#             return render_template("GM_add_resource_node.html")

#         try:
#             new_node = ResourceNode(
#                 name=name,
#                 type=type,
#                 production_rate=production_rate,
#                 quality=quality,
#                 city_id=city_id,
#                 item_id=item_id,
#                 gm_profile_id=current_user.gm_profile.id
#             )
#             db.session.add(new_node)
#             db.session.commit()
#             flash(f"Resource node '{name}' added successfully!", "success")
#             return redirect(url_for("gm.view_resource_nodes"))
#         except Exception as e:
#             db.session.rollback()
#             flash(f"Error adding resource node: {e}", "danger")

#     # GET request - show form
#     cities = City.query.filter_by(gm_profile_id=current_user.gm_profile.id).all()
#     items = Item.query.filter_by(gm_profile_id=current_user.gm_profile.id).all()
#     return render_template("GM_add_resource_node.html", cities=cities, items=items)

# @gm_bp.route("/resource_nodes/edit/<int:node_id>", methods=["GET", "POST"])
# @login_required
# def edit_resource_node(node_id):
#     node = ResourceNode.query.get_or_404(node_id)
    
#     if request.method == "POST":
#         node.name = request.form.get("name")
#         node.type = request.form.get("type")
#         node.production_rate = float(request.form.get("production_rate"))
#         node.quality = float(request.form.get("quality"))
#         node.city_id = int(request.form.get("city_id"))
#         node.item_id = int(request.form.get("item_id"))
        
#         try:
#             db.session.commit()
#             flash("Resource node updated successfully!", "success")
#             return redirect(url_for("gm.view_resource_nodes"))
#         except Exception as e:
#             db.session.rollback()
#             flash(f"Error updating resource node: {e}", "danger")

#     cities = City.query.filter_by(gm_profile_id=current_user.gm_profile.id).all()
#     items = Item.query.filter_by(gm_profile_id=current_user.gm_profile.id).all()
#     return render_template("GM_edit_resource_node.html", node=node, cities=cities, items=items)

# @gm_bp.route("/resource_nodes/delete/<int:node_id>", methods=["POST"])
# @login_required
# def delete_resource_node(node_id):
#     node = ResourceNode.query.get_or_404(node_id)
#     try:
#         db.session.delete(node)
#         db.session.commit()
#         flash("Resource node deleted successfully!", "success")
#     except Exception as e:
#         db.session.rollback()
#         flash(f"Error deleting resource node: {e}", "danger")
#     return redirect(url_for("gm.view_resource_nodes"))
=======
>>>>>>> GCP
