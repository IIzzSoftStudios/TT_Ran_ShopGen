"""Immutable Demo world snapshots: export from a campaign, restore into a new one.

Runtime Demo visitors restore from a versioned JSON file — they never read the
live operator template campaign.
"""

from __future__ import annotations

import copy
import json
import logging
from pathlib import Path
from typing import Any

from flask import current_app

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
from app.services.demo_world_clone import _remap_generation_json
from app.services.world_setup_state import SETUP_STAGE_COMPLETE

log = logging.getLogger(__name__)

SNAPSHOT_SCHEMA_VERSION = 1
DEFAULT_SNAPSHOT_REL = Path("app") / "data" / "demo_snapshots" / "demo_template_v1.json"


def default_snapshot_path() -> Path:
    """Packaged snapshot path relative to the TT_Ran_ShopGen project root."""
    # app/services/demo_snapshot.py → parents[2] = TT_Ran_ShopGen
    root = Path(__file__).resolve().parents[2]
    return root / DEFAULT_SNAPSHOT_REL


def resolve_snapshot_path() -> Path:
    raw = (current_app.config.get("DEMO_SNAPSHOT_PATH") or "").strip()
    if raw:
        path = Path(raw)
        if not path.is_absolute():
            root = Path(__file__).resolve().parents[2]
            path = root / path
        return path
    return default_snapshot_path()


def export_campaign_snapshot(campaign_id: int) -> dict[str, Any]:
    """Serialize a campaign graph into a JSON-serializable snapshot dict."""
    campaign = Campaign.query.filter_by(id=campaign_id).first()
    if campaign is None:
        raise ValueError(f"Campaign {campaign_id} not found")

    config = CampaignWorldConfig.query.filter_by(campaign_id=campaign_id).first()
    regions = Region.query.filter_by(campaign_id=campaign_id).order_by(Region.id).all()
    cities = City.query.filter_by(campaign_id=campaign_id).order_by(City.city_id).all()
    shops = Shop.query.filter_by(campaign_id=campaign_id).order_by(Shop.shop_id).all()

    shop_ids = [s.shop_id for s in shops]
    city_ids = [c.city_id for c in cities]
    links = []
    if shop_ids:
        rows = db.session.execute(
            shop_cities.select().where(shop_cities.c.shop_id.in_(shop_ids))
        ).fetchall()
        for row in rows:
            links.append({"shop_id": int(row.shop_id), "city_id": int(row.city_id)})

    folders = (
        ItemFolder.query.filter_by(campaign_id=campaign_id)
        .order_by(ItemFolder.folder_id)
        .all()
    )
    items = Item.query.filter_by(campaign_id=campaign_id).order_by(Item.item_id).all()
    inventory = ShopInventory.query.filter_by(campaign_id=campaign_id).all()
    regional = RegionalMarket.query.filter_by(campaign_id=campaign_id).all()
    global_markets = GlobalMarket.query.filter_by(campaign_id=campaign_id).all()
    canvases = (
        MapCanvas.query.filter_by(campaign_id=campaign_id).order_by(MapCanvas.id).all()
    )
    markers = MapMarker.query.filter_by(campaign_id=campaign_id).all()
    pois = MapPointOfInterest.query.filter_by(campaign_id=campaign_id).all()

    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "source_campaign_id": campaign_id,
        "campaign": {
            "name": campaign.name,
            "system_type": campaign.system_type,
            "allow_player_debt": bool(campaign.allow_player_debt),
            "current_game_day": int(campaign.current_game_day or 1),
        },
        "world_config": None
        if config is None
        else {
            "settings_json": copy.deepcopy(config.settings_json or {}),
            "schema_version": config.schema_version,
            "world_seed": config.world_seed,
        },
        "regions": [
            {
                "id": r.id,
                "name": r.name,
                "local_flavor": copy.deepcopy(r.local_flavor)
                if r.local_flavor is not None
                else None,
                "main_color": r.main_color,
                "secondary_color": r.secondary_color,
            }
            for r in regions
        ],
        "cities": [
            {
                "city_id": c.city_id,
                "name": c.name,
                "government_type": c.government_type,
                "size": c.size,
                "population": c.population,
                "region": c.region,
                "region_id": c.region_id,
            }
            for c in cities
        ],
        "shops": [
            {
                "shop_id": s.shop_id,
                "type": s.type,
                "name": s.name,
                "preferred_region": s.preferred_region,
                "next_restock_day": s.next_restock_day,
            }
            for s in shops
        ],
        "shop_cities": links,
        "item_folders": [
            {
                "folder_id": f.folder_id,
                "name": f.name,
                "parent_id": f.parent_id,
                "sort_order": int(f.sort_order or 0),
            }
            for f in folders
        ],
        "items": [
            {
                "item_id": i.item_id,
                "name": i.name,
                "type": i.type,
                "rarity": i.rarity,
                "base_price": i.base_price,
                "description": i.description,
                "range": i.range,
                "damage": i.damage,
                "rate_of_fire": i.rate_of_fire,
                "min_str": i.min_str,
                "notes": i.notes,
                "preferred_regions": copy.deepcopy(i.preferred_regions)
                if i.preferred_regions is not None
                else None,
                "stats": copy.deepcopy(i.stats) if i.stats is not None else None,
                "axis_position": i.axis_position,
                "origin_srd_key": i.origin_srd_key,
                "content_source": i.content_source,
                "folder_id": i.folder_id,
            }
            for i in items
        ],
        "shop_inventory": [
            {
                "shop_id": inv.shop_id,
                "item_id": inv.item_id,
                "stock": inv.stock,
                "dynamic_price": inv.dynamic_price,
                "sourcing_preference": inv.sourcing_preference,
            }
            for inv in inventory
        ],
        "regional_markets": [
            {
                "city_id": rm.city_id,
                "item_id": rm.item_id,
                "total_supply": rm.total_supply,
                "total_demand": rm.total_demand,
                "average_price": rm.average_price,
            }
            for rm in regional
        ],
        "global_markets": [
            {
                "item_id": gm.item_id,
                "total_supply": gm.total_supply,
                "total_demand": gm.total_demand,
                "average_price": gm.average_price,
                "baseline_avg_stock": getattr(gm, "baseline_avg_stock", None),
            }
            for gm in global_markets
        ],
        "map_canvases": [
            {
                "id": canvas.id,
                "city_id": canvas.city_id,
                "shop_id": canvas.shop_id,
                "scope": canvas.scope,
                "source_type": canvas.source_type,
                "image_path": canvas.image_path,
                "underlay_path": canvas.underlay_path,
                "generation_json": copy.deepcopy(canvas.generation_json)
                if canvas.generation_json is not None
                else None,
                "width": canvas.width,
                "height": canvas.height,
            }
            for canvas in canvases
        ],
        "map_markers": [
            {
                "canvas_id": m.canvas_id,
                "entity_type": m.entity_type,
                "city_id": m.city_id,
                "shop_id": m.shop_id,
                "x": m.x,
                "y": m.y,
            }
            for m in markers
        ],
        "map_pois": [
            {
                "canvas_id": p.canvas_id,
                "label": p.label,
                "note": p.note,
                "x": p.x,
                "y": p.y,
                "visible_to_players": bool(p.visible_to_players),
            }
            for p in pois
        ],
        "include_empty_gm_world_state": GMWorldState.query.filter_by(
            campaign_id=campaign_id
        ).first()
        is not None,
    }


def write_snapshot_file(snapshot: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_snapshot_file(path: Path | None = None) -> dict[str, Any]:
    target = path or resolve_snapshot_path()
    if not target.is_file():
        raise FileNotFoundError(f"Demo snapshot not found: {target}")
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Demo snapshot root must be an object")
    if int(data.get("schema_version") or 0) != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported demo snapshot schema_version={data.get('schema_version')}"
        )
    return data


def restore_demo_snapshot(
    snapshot: dict[str, Any],
    *,
    gm_profile_id: int,
    name: str | None = None,
) -> Campaign:
    """Materialize ``snapshot`` as a new Campaign. Does not commit."""
    meta = snapshot.get("campaign") or {}
    new_campaign = Campaign(
        gm_profile_id=gm_profile_id,
        name=name or meta.get("name") or "Demo World",
        system_type=meta.get("system_type") or "dnd5e",
        is_active=True,
        is_free_tier=True,
        allow_player_debt=bool(meta.get("allow_player_debt")),
        current_game_day=int(meta.get("current_game_day") or 1),
    )
    db.session.add(new_campaign)
    db.session.flush()

    src_config = snapshot.get("world_config")
    if isinstance(src_config, dict):
        settings = copy.deepcopy(src_config.get("settings_json") or {})
        if isinstance(settings, dict):
            settings["pending_generation"] = False
            settings["setup_stage"] = SETUP_STAGE_COMPLETE
            settings["campaign_name"] = new_campaign.name
        db.session.add(
            CampaignWorldConfig(
                campaign_id=new_campaign.id,
                settings_json=settings,
                schema_version=int(src_config.get("schema_version") or 1),
                world_seed=src_config.get("world_seed"),
            )
        )

    region_id_map: dict[int, int] = {}
    for region in snapshot.get("regions") or []:
        old_id = int(region["id"])
        clone = Region(
            name=region["name"],
            campaign_id=new_campaign.id,
            local_flavor=copy.deepcopy(region.get("local_flavor")),
            main_color=region.get("main_color"),
            secondary_color=region.get("secondary_color"),
            ruler_player_id=None,
        )
        db.session.add(clone)
        db.session.flush()
        region_id_map[old_id] = clone.id

    city_id_map: dict[int, int] = {}
    for city in snapshot.get("cities") or []:
        old_id = int(city["city_id"])
        old_region = city.get("region_id")
        new_region_id = (
            region_id_map.get(int(old_region)) if old_region is not None else None
        )
        clone = City(
            name=city["name"],
            government_type=city.get("government_type"),
            size=city.get("size"),
            population=city.get("population"),
            region=city.get("region"),
            region_id=new_region_id,
            owner_player_id=None,
            campaign_id=new_campaign.id,
        )
        db.session.add(clone)
        db.session.flush()
        city_id_map[old_id] = clone.city_id

    shop_id_map: dict[int, int] = {}
    for shop in snapshot.get("shops") or []:
        old_id = int(shop["shop_id"])
        clone = Shop(
            type=shop["type"],
            name=shop["name"],
            campaign_id=new_campaign.id,
            preferred_region=shop.get("preferred_region"),
            next_restock_day=shop.get("next_restock_day"),
            owner_player_id=None,
        )
        db.session.add(clone)
        db.session.flush()
        shop_id_map[old_id] = clone.shop_id

    for link in snapshot.get("shop_cities") or []:
        new_shop = shop_id_map.get(int(link["shop_id"]))
        new_city = city_id_map.get(int(link["city_id"]))
        if new_shop is None or new_city is None:
            continue
        db.session.execute(
            shop_cities.insert().values(shop_id=new_shop, city_id=new_city)
        )

    folder_id_map: dict[int, int] = {}
    folders = list(snapshot.get("item_folders") or [])
    pending = list(folders)
    guard = 0
    while pending and guard < len(folders) + 5:
        guard += 1
        next_pending = []
        for folder in pending:
            parent_old = folder.get("parent_id")
            if parent_old is not None and int(parent_old) not in folder_id_map:
                next_pending.append(folder)
                continue
            parent_new = (
                folder_id_map.get(int(parent_old)) if parent_old is not None else None
            )
            clone = ItemFolder(
                campaign_id=new_campaign.id,
                name=folder["name"],
                parent_id=parent_new,
                sort_order=int(folder.get("sort_order") or 0),
            )
            db.session.add(clone)
            db.session.flush()
            folder_id_map[int(folder["folder_id"])] = clone.folder_id
        if len(next_pending) == len(pending):
            for folder in next_pending:
                clone = ItemFolder(
                    campaign_id=new_campaign.id,
                    name=folder["name"],
                    parent_id=None,
                    sort_order=int(folder.get("sort_order") or 0),
                )
                db.session.add(clone)
                db.session.flush()
                folder_id_map[int(folder["folder_id"])] = clone.folder_id
            break
        pending = next_pending

    item_id_map: dict[int, int] = {}
    for item in snapshot.get("items") or []:
        old_id = int(item["item_id"])
        folder_old = item.get("folder_id")
        clone = Item(
            name=item["name"],
            type=item["type"],
            rarity=item["rarity"],
            base_price=item["base_price"],
            description=item.get("description"),
            range=item.get("range"),
            damage=item.get("damage"),
            rate_of_fire=item.get("rate_of_fire"),
            min_str=item.get("min_str"),
            notes=item.get("notes"),
            campaign_id=new_campaign.id,
            preferred_regions=copy.deepcopy(item.get("preferred_regions")),
            stats=copy.deepcopy(item.get("stats")),
            axis_position=item.get("axis_position"),
            origin_srd_key=item.get("origin_srd_key"),
            content_source=item.get("content_source"),
            folder_id=folder_id_map.get(int(folder_old)) if folder_old else None,
        )
        db.session.add(clone)
        db.session.flush()
        item_id_map[old_id] = clone.item_id

    for inv in snapshot.get("shop_inventory") or []:
        new_shop = shop_id_map.get(int(inv["shop_id"])) if inv.get("shop_id") else None
        item_old = inv.get("item_id")
        new_item = item_id_map.get(int(item_old)) if item_old else None
        if new_shop is None or (item_old and new_item is None):
            continue
        db.session.add(
            ShopInventory(
                shop_id=new_shop,
                item_id=new_item,
                campaign_id=new_campaign.id,
                stock=inv.get("stock") or 0,
                dynamic_price=inv["dynamic_price"],
                sourcing_preference=inv.get("sourcing_preference") or "hybrid",
            )
        )

    for rm in snapshot.get("regional_markets") or []:
        new_city = city_id_map.get(int(rm["city_id"]))
        new_item = item_id_map.get(int(rm["item_id"]))
        if new_city is None or new_item is None:
            continue
        db.session.add(
            RegionalMarket(
                city_id=new_city,
                item_id=new_item,
                total_supply=rm.get("total_supply") or 0,
                total_demand=rm.get("total_demand") or 0,
                average_price=rm.get("average_price") or 0,
                campaign_id=new_campaign.id,
            )
        )

    for gm in snapshot.get("global_markets") or []:
        new_item = item_id_map.get(int(gm["item_id"]))
        if new_item is None:
            continue
        row = GlobalMarket(
            item_id=new_item,
            total_supply=gm.get("total_supply") or 0,
            total_demand=gm.get("total_demand") or 0,
            average_price=gm.get("average_price") or 0,
            campaign_id=new_campaign.id,
        )
        if gm.get("baseline_avg_stock") is not None and hasattr(
            row, "baseline_avg_stock"
        ):
            row.baseline_avg_stock = gm["baseline_avg_stock"]
        db.session.add(row)

    canvas_id_map: dict[int, int] = {}
    for canvas in snapshot.get("map_canvases") or []:
        old_id = int(canvas["id"])
        city_old = canvas.get("city_id")
        shop_old = canvas.get("shop_id")
        clone = MapCanvas(
            campaign_id=new_campaign.id,
            city_id=city_id_map.get(int(city_old)) if city_old else None,
            shop_id=shop_id_map.get(int(shop_old)) if shop_old else None,
            scope=canvas.get("scope") or "world",
            source_type=canvas.get("source_type") or "generated",
            image_path=canvas.get("image_path"),
            underlay_path=canvas.get("underlay_path"),
            generation_json=_remap_generation_json(
                canvas.get("generation_json"), region_id_map
            )
            if canvas.get("generation_json") is not None
            else None,
            width=int(canvas.get("width") or 1024),
            height=int(canvas.get("height") or 1024),
        )
        db.session.add(clone)
        db.session.flush()
        canvas_id_map[old_id] = clone.id

    for marker in snapshot.get("map_markers") or []:
        new_canvas = canvas_id_map.get(int(marker["canvas_id"]))
        if new_canvas is None:
            continue
        city_old = marker.get("city_id")
        shop_old = marker.get("shop_id")
        db.session.add(
            MapMarker(
                canvas_id=new_canvas,
                campaign_id=new_campaign.id,
                entity_type=marker["entity_type"],
                city_id=city_id_map.get(int(city_old)) if city_old else None,
                shop_id=shop_id_map.get(int(shop_old)) if shop_old else None,
                x=marker["x"],
                y=marker["y"],
            )
        )

    for poi in snapshot.get("map_pois") or []:
        new_canvas = canvas_id_map.get(int(poi["canvas_id"]))
        if new_canvas is None:
            continue
        db.session.add(
            MapPointOfInterest(
                canvas_id=new_canvas,
                campaign_id=new_campaign.id,
                label=poi["label"],
                note=poi.get("note"),
                x=poi["x"],
                y=poi["y"],
                visible_to_players=bool(poi.get("visible_to_players")),
            )
        )

    db.session.add(
        SimulationState(
            campaign_id=new_campaign.id,
            current_tick=0,
            speed="pause",
        )
    )
    if snapshot.get("include_empty_gm_world_state"):
        db.session.add(
            GMWorldState(
                campaign_id=new_campaign.id,
                state_json={},
                tick_seq=0,
            )
        )

    db.session.flush()
    log.info(
        "demo_snapshot_restore campaign=%s regions=%d cities=%d shops=%d canvases=%d",
        new_campaign.id,
        len(region_id_map),
        len(city_id_map),
        len(shop_id_map),
        len(canvas_id_map),
    )
    return new_campaign
