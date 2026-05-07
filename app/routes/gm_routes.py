import traceback

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from sqlalchemy.orm import selectinload, subqueryload
from sqlalchemy.exc import IntegrityError
from flask_login import login_required, current_user

from app.extensions import db, limiter
from app.models import City, Shop, Item, ShopInventory, Region, CampaignWorldConfig
from app.routes.handlers.gm_helpers import (
    city_for_campaign_or_404,
    city_for_campaign_optional,
    item_for_campaign_or_404,
    shop_for_campaign_or_404,
    region_for_campaign_or_404,
    region_table_exists,
    active_campaign_id,
    require_active_campaign,
)
from app.routes.handlers.gm_players_handler import (
    list_players,
    create_npc,
    view_character,
    update_character,
    equip_item,
    unequip_item,
    update_inventory,
    remove_player_from_campaign as remove_player_from_campaign_handler,
    delete_npc_player as delete_npc_player_handler,
)
from app.routes.handlers.gm_simulation_handler import (
    home as gm_dashboard_home,
    seed_world,
    run_simulation_tick,
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
)
from app.services.world_generator.defaults import RANGE_SETTINGS, SCHEMA_VERSION
from app.services.world_generator.generator import (
    GenerationTimeoutError,
    generate_cities_for_empty_region,
    generate_shops_onward,
)

gm_bp = Blueprint("gm", __name__, url_prefix="/gm")


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


@gm_bp.route("/")
@login_required
def home():
    return gm_dashboard_home()


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
    return redirect(request.referrer or url_for("gm.home"))


@gm_bp.route("/seed_world", methods=["POST"])
@login_required
def gm_seed_world():
    return seed_world()

#cities routes

@gm_bp.route("/cities/")
@login_required
def view_cities():
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    cities = City.query.filter_by(campaign_id=camp.id).all()
    return render_template("GM_view_cities.html", cities=cities)

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
            )
        try:
            population = int(pop_raw)
        except (TypeError, ValueError):
            flash("Population must be a valid number.", "danger")
            return render_template(
                "GM_edit_city.html",
                city=city,
                campaign_regions=campaign_regions,
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
    )

@gm_bp.route("/cities/delete/<int:city_id>", methods=["POST"])
@login_required
def delete_city(city_id):
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    city = city_for_campaign_or_404(city_id, camp.id)
    try:
        db.session.delete(city)
        db.session.commit()
        flash("City deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting city: {e}", "danger")
    return redirect(url_for("gm.view_cities"))


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


@gm_bp.route("/shops/")
@login_required
def view_shops():
    ctx = get_shop_city_panel_context(current_user.gm_profile)
    return render_template("GM_view_shops.html", **ctx)

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
            new_shop = Shop(
                name=shop_name,
                type=shop_type,
                campaign_id=campaign_id,
            )
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
        db.session.delete(shop)
        db.session.commit()
        flash("Shop deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting shop: {e}", "danger")
    return redirect(url_for("gm.view_shops"))

@gm_bp.route("/shops/city/<int:city_id>/shops")
@login_required
def view_city_shops(city_id):
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    city = city_for_campaign_or_404(city_id, camp.id)
    shops = city.shops
    return render_template("GM_view_city_shops.html", city=city, shops=shops)

@gm_bp.route("/shops/<int:shop_id>/items")
@login_required
def view_shop_items(shop_id):
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    shop = shop_for_campaign_or_404(shop_id, camp.id)
    city = shop.cities[0] if shop.cities else None
    shop_inventory = ShopInventory.query.filter_by(
        shop_id=shop_id, campaign_id=camp.id
    ).all()
    item_ids = [inv.item_id for inv in shop_inventory]
    items = Item.query.filter(Item.item_id.in_(item_ids)).all()
    return render_template("GM_view_shop_items.html", items=items, shop=shop, city=city)

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

@gm_bp.route("/items/")
@login_required
def view_items():
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    q = Item.query.filter_by(campaign_id=camp.id).order_by(Item.name).options(
        selectinload(Item.inventory)
        .selectinload(ShopInventory.shop)
        .selectinload(Shop.cities)
    )
    items = q.all()
    for item in items:
        item.distinct_shop_count = len(
            {inv.shop_id for inv in item.inventory if inv.shop_id is not None}
        )
    return render_template("GM_view_items.html", items=items)

@gm_bp.route("/items/add", methods=["GET", "POST"])
@login_required
def add_item():
    camp, redir = _active_campaign_or_redirect()
    if redir:
        return redir
    campaign_id = camp.id

    if request.method == "POST":
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
            new_item = Item(
                name=name,
                type=item_type,
                rarity=rarity,
                base_price=base_price,
                description=description,
                campaign_id=campaign_id,
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
    return render_template(
        "GM_add_item.html",
        grouped_shops=grouped_shops,
        city_shop_meta=city_shop_meta,
    )


@gm_bp.route("/items/edit/<int:item_id>", methods=["GET", "POST"])
@login_required
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
    try:
        db.session.delete(item)
        db.session.commit()
        flash("Item deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting item: {e}", "danger")
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


# Simulation routes
@gm_bp.route("/simulation/tick", methods=["POST"])
@login_required
def gm_run_simulation_tick():
    """Execute one simulation tick manually from the GM dashboard"""
    return run_simulation_tick()

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

@gm_bp.route("/simulation/jobs/<job_id>", methods=["GET"])
@login_required
def gm_simulation_job_status(job_id: str):
    """Return background simulation job status for polling UI."""
    return simulation_job_status(job_id)


# Player / Character management routes
@gm_bp.route("/players/")
@login_required
def gm_view_players():
    """List players and characters for the current campaign."""
    return list_players()


@gm_bp.route("/npcs/create", methods=["GET", "POST"])
@login_required
def gm_create_npc():
    """Create a GM-only NPC (Player row with no User) in the active campaign."""
    return create_npc()


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


