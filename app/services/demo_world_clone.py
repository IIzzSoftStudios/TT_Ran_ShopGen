"""Deep-clone a template Campaign into a private Demo copy.

Does not commit — caller owns the transaction. Never copies players,
redemptions, or the template ``join_code``.
"""

from __future__ import annotations

import copy
import logging
from typing import Any

from app.extensions import db
from app.models import (
    Campaign,
    CampaignWorldConfig,
    City,
    GlobalMarket,
    GMWorldState,
    Item,
    ItemFolder,
    MapCanvas,
    MapMarker,
    MapPointOfInterest,
    Region,
    RegionalMarket,
    Shop,
    ShopInventory,
    SimulationState,
    shop_cities,
)

log = logging.getLogger(__name__)


def _remap_generation_json(payload: Any, region_id_map: dict[int, int]) -> Any:
    """Deep-copy map generation JSON and rewrite ``region_id`` references."""
    data = copy.deepcopy(payload)
    if not isinstance(data, dict):
        return data

    features = data.get("features")
    if isinstance(features, list):
        for feat in features:
            if not isinstance(feat, dict):
                continue
            rid = feat.get("region_id")
            if rid is None:
                continue
            try:
                old = int(rid)
            except (TypeError, ValueError):
                continue
            if old in region_id_map:
                feat["region_id"] = region_id_map[old]

    # Hex / region tint layers sometimes nest region ids similarly.
    for key in ("region_tints", "regions", "boundaries"):
        block = data.get(key)
        if isinstance(block, list):
            for entry in block:
                if not isinstance(entry, dict):
                    continue
                rid = entry.get("region_id")
                if rid is None:
                    continue
                try:
                    old = int(rid)
                except (TypeError, ValueError):
                    continue
                if old in region_id_map:
                    entry["region_id"] = region_id_map[old]
        elif isinstance(block, dict):
            for _k, entry in list(block.items()):
                if not isinstance(entry, dict):
                    continue
                rid = entry.get("region_id")
                if rid is None:
                    continue
                try:
                    old = int(rid)
                except (TypeError, ValueError):
                    continue
                if old in region_id_map:
                    entry["region_id"] = region_id_map[old]
    return data


def clone_campaign_for_demo(
    template: Campaign,
    *,
    gm_profile_id: int,
    name: str | None = None,
) -> Campaign:
    """Return a new Campaign owned by ``gm_profile_id`` cloned from ``template``.

    Caller must ``db.session.commit()`` (or rollback) after return.
    """
    if template is None:
        raise ValueError("template campaign is required")

    new_campaign = Campaign(
        gm_profile_id=gm_profile_id,
        name=name or f"{template.name} (Demo)",
        system_type=template.system_type,
        is_active=True,
        is_free_tier=True,
        allow_player_debt=bool(template.allow_player_debt),
        current_game_day=int(template.current_game_day or 1),
        # join_code minted by before_insert listener
    )
    db.session.add(new_campaign)
    db.session.flush()

    src_config = CampaignWorldConfig.query.filter_by(campaign_id=template.id).first()
    if src_config is not None:
        settings = copy.deepcopy(src_config.settings_json or {})
        if isinstance(settings, dict):
            settings["pending_generation"] = False
            settings["setup_stage"] = "complete"
            settings["campaign_name"] = new_campaign.name
        db.session.add(
            CampaignWorldConfig(
                campaign_id=new_campaign.id,
                settings_json=settings,
                schema_version=src_config.schema_version,
                world_seed=src_config.world_seed,
            )
        )

    region_id_map: dict[int, int] = {}
    for region in Region.query.filter_by(campaign_id=template.id).order_by(Region.id).all():
        clone = Region(
            name=region.name,
            campaign_id=new_campaign.id,
            local_flavor=copy.deepcopy(region.local_flavor)
            if region.local_flavor is not None
            else None,
            main_color=region.main_color,
            secondary_color=region.secondary_color,
            ruler_player_id=None,
        )
        db.session.add(clone)
        db.session.flush()
        region_id_map[region.id] = clone.id

    city_id_map: dict[int, int] = {}
    for city in City.query.filter_by(campaign_id=template.id).order_by(City.city_id).all():
        new_region_id = None
        if city.region_id is not None:
            new_region_id = region_id_map.get(int(city.region_id))
        clone = City(
            name=city.name,
            government_type=city.government_type,
            size=city.size,
            population=city.population,
            region=city.region,
            region_id=new_region_id,
            owner_player_id=None,
            campaign_id=new_campaign.id,
        )
        db.session.add(clone)
        db.session.flush()
        city_id_map[city.city_id] = clone.city_id

    shop_id_map: dict[int, int] = {}
    for shop in Shop.query.filter_by(campaign_id=template.id).order_by(Shop.shop_id).all():
        clone = Shop(
            type=shop.type,
            name=shop.name,
            campaign_id=new_campaign.id,
            preferred_region=shop.preferred_region,
            next_restock_day=shop.next_restock_day,
            owner_player_id=None,
        )
        db.session.add(clone)
        db.session.flush()
        shop_id_map[shop.shop_id] = clone.shop_id

    # Remap shop_cities association rows.
    src_shop_ids = list(shop_id_map.keys())
    if src_shop_ids:
        rows = db.session.execute(
            shop_cities.select().where(shop_cities.c.shop_id.in_(src_shop_ids))
        ).fetchall()
        for row in rows:
            old_shop_id = int(row.shop_id)
            old_city_id = int(row.city_id)
            new_shop_id = shop_id_map.get(old_shop_id)
            new_city_id = city_id_map.get(old_city_id)
            if new_shop_id is None or new_city_id is None:
                continue
            db.session.execute(
                shop_cities.insert().values(shop_id=new_shop_id, city_id=new_city_id)
            )

    # Optional catalog (may be empty on the demo template).
    folder_id_map: dict[int, int] = {}
    folders = (
        ItemFolder.query.filter_by(campaign_id=template.id)
        .order_by(ItemFolder.folder_id)
        .all()
    )
    # Parents before children: repeat until all mapped (small trees).
    pending = list(folders)
    guard = 0
    while pending and guard < len(folders) + 5:
        guard += 1
        next_pending = []
        for folder in pending:
            if folder.parent_id is not None and folder.parent_id not in folder_id_map:
                next_pending.append(folder)
                continue
            parent_new = (
                folder_id_map.get(folder.parent_id) if folder.parent_id else None
            )
            clone = ItemFolder(
                campaign_id=new_campaign.id,
                name=folder.name,
                parent_id=parent_new,
                sort_order=int(folder.sort_order or 0),
            )
            db.session.add(clone)
            db.session.flush()
            folder_id_map[folder.folder_id] = clone.folder_id
        if len(next_pending) == len(pending):
            # Cycle or missing parent — attach remaining under root.
            for folder in next_pending:
                clone = ItemFolder(
                    campaign_id=new_campaign.id,
                    name=folder.name,
                    parent_id=None,
                    sort_order=int(folder.sort_order or 0),
                )
                db.session.add(clone)
                db.session.flush()
                folder_id_map[folder.folder_id] = clone.folder_id
            break
        pending = next_pending

    item_id_map: dict[int, int] = {}
    for item in Item.query.filter_by(campaign_id=template.id).order_by(Item.item_id).all():
        clone = Item(
            name=item.name,
            type=item.type,
            rarity=item.rarity,
            base_price=item.base_price,
            description=item.description,
            range=item.range,
            damage=item.damage,
            rate_of_fire=item.rate_of_fire,
            min_str=item.min_str,
            notes=item.notes,
            campaign_id=new_campaign.id,
            preferred_regions=copy.deepcopy(item.preferred_regions)
            if item.preferred_regions is not None
            else None,
            stats=copy.deepcopy(item.stats) if item.stats is not None else None,
            axis_position=item.axis_position,
            origin_srd_key=item.origin_srd_key,
            content_source=item.content_source,
            folder_id=folder_id_map.get(item.folder_id) if item.folder_id else None,
        )
        db.session.add(clone)
        db.session.flush()
        item_id_map[item.item_id] = clone.item_id

    for inv in ShopInventory.query.filter_by(campaign_id=template.id).all():
        new_shop = shop_id_map.get(inv.shop_id)
        new_item = item_id_map.get(inv.item_id) if inv.item_id else None
        if new_shop is None or (inv.item_id and new_item is None):
            continue
        db.session.add(
            ShopInventory(
                shop_id=new_shop,
                item_id=new_item,
                campaign_id=new_campaign.id,
                stock=inv.stock,
                dynamic_price=inv.dynamic_price,
                sourcing_preference=inv.sourcing_preference,
            )
        )

    for rm in RegionalMarket.query.filter_by(campaign_id=template.id).all():
        new_city = city_id_map.get(rm.city_id)
        new_item = item_id_map.get(rm.item_id)
        if new_city is None or new_item is None:
            continue
        db.session.add(
            RegionalMarket(
                city_id=new_city,
                item_id=new_item,
                total_supply=rm.total_supply,
                total_demand=rm.total_demand,
                average_price=rm.average_price,
                campaign_id=new_campaign.id,
            )
        )

    for gm in GlobalMarket.query.filter_by(campaign_id=template.id).all():
        new_item = item_id_map.get(gm.item_id)
        if new_item is None:
            continue
        row = GlobalMarket(
            item_id=new_item,
            total_supply=gm.total_supply,
            total_demand=gm.total_demand,
            average_price=gm.average_price,
            campaign_id=new_campaign.id,
        )
        if hasattr(gm, "baseline_avg_stock"):
            row.baseline_avg_stock = gm.baseline_avg_stock
        db.session.add(row)

    # Skip PriceHistory — fresh demo clock.

    canvas_id_map: dict[int, int] = {}
    canvases = (
        MapCanvas.query.filter_by(campaign_id=template.id)
        .order_by(MapCanvas.id)
        .all()
    )
    for canvas in canvases:
        clone = MapCanvas(
            campaign_id=new_campaign.id,
            city_id=city_id_map.get(canvas.city_id) if canvas.city_id else None,
            shop_id=shop_id_map.get(canvas.shop_id) if canvas.shop_id else None,
            scope=canvas.scope,
            source_type=canvas.source_type,
            image_path=canvas.image_path,
            underlay_path=canvas.underlay_path,
            generation_json=_remap_generation_json(
                canvas.generation_json, region_id_map
            )
            if canvas.generation_json is not None
            else None,
            width=canvas.width,
            height=canvas.height,
        )
        db.session.add(clone)
        db.session.flush()
        canvas_id_map[canvas.id] = clone.id

    for marker in MapMarker.query.filter_by(campaign_id=template.id).all():
        new_canvas = canvas_id_map.get(marker.canvas_id)
        if new_canvas is None:
            continue
        db.session.add(
            MapMarker(
                canvas_id=new_canvas,
                campaign_id=new_campaign.id,
                entity_type=marker.entity_type,
                city_id=city_id_map.get(marker.city_id) if marker.city_id else None,
                shop_id=shop_id_map.get(marker.shop_id) if marker.shop_id else None,
                x=marker.x,
                y=marker.y,
            )
        )

    for poi in MapPointOfInterest.query.filter_by(campaign_id=template.id).all():
        new_canvas = canvas_id_map.get(poi.canvas_id)
        if new_canvas is None:
            continue
        db.session.add(
            MapPointOfInterest(
                canvas_id=new_canvas,
                campaign_id=new_campaign.id,
                label=poi.label,
                note=poi.note,
                x=poi.x,
                y=poi.y,
                visible_to_players=poi.visible_to_players,
            )
        )

    db.session.add(
        SimulationState(
            campaign_id=new_campaign.id,
            current_tick=0,
            speed="pause",
        )
    )

    # Empty dual-write snapshot; first tick can repopulate.
    if GMWorldState.query.filter_by(campaign_id=template.id).first() is not None:
        db.session.add(
            GMWorldState(
                campaign_id=new_campaign.id,
                state_json={},
                tick_seq=0,
            )
        )

    db.session.flush()
    log.info(
        "demo_clone template=%s -> campaign=%s regions=%d cities=%d shops=%d items=%d canvases=%d",
        template.id,
        new_campaign.id,
        len(region_id_map),
        len(city_id_map),
        len(shop_id_map),
        len(item_id_map),
        len(canvas_id_map),
    )
    return new_campaign
