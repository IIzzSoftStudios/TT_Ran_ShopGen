"""Tests for SRD item catalog seeding, GM routes, equipment slots, and combat snapshots."""

from __future__ import annotations

import re

from werkzeug.datastructures import MultiDict

import pytest

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import (
    BattleEncounter,
    Campaign,
    City,
    Item,
    ItemFolder,
    Player,
    PlayerCharacterSheet,
    PlayerEquipment,
    PlayerInventory,
    Region,
    Shop,
    ShopInventory,
    User,
)
from app.services.character_creation.dnd5e_items import CORE_ITEMS, item_slug
from app.services.character_creation.srd_item_manifest import (
    SRD_ITEM_COUNT,
    SRD_ITEMS_BY_CATEGORY,
)
from app.services.combat import encounter_service
from app.services.equipment.slots import ALL_EQUIPMENT_SLOTS, normalize_slot
from app.services.items_catalog_service import ensure_srd_items_for_campaign, list_campaign_items
from app.services.user_capabilities import ensure_gm_profile
from tests.session_helpers import seed_client_session

_LORE_DENY = re.compile(
    r"\b(vecna|blackrazor|whelm|wave|kwalish|mordenkainen|nystul)\b",
    re.I,
)

_REQUIRED_FIELDS = (
    "key",
    "name",
    "category",
    "summary",
    "origin_srd_key",
    "type_data",
)


@pytest.fixture(autouse=True)
def _db_tables():
    flask_app.config["WTF_CSRF_ENABLED"] = False
    with flask_app.app_context():
        db.create_all()
        yield
        db.session.rollback()
        db.drop_all()


def _make_gm_with_campaign(username: str = "gm-items") -> tuple[User, Campaign]:
    user = User(username=username, password="x", role="GM")
    user.set_password("Secret1!")
    db.session.add(user)
    db.session.commit()
    ensure_gm_profile(user)
    db.session.commit()
    db.session.refresh(user)
    campaign = Campaign(
        gm_profile_id=user.gm_profile.id,
        name="Item Camp",
        system_type="dnd5e",
        is_active=True,
        current_game_day=1,
        join_code="CAMP-ITEMS-01",
    )
    db.session.add(campaign)
    db.session.commit()
    return user, campaign


def test_core_items_matches_srd_manifest():
    assert len(CORE_ITEMS) == SRD_ITEM_COUNT == 428
    manifest_pairs = {
        (category, name)
        for category, names in SRD_ITEMS_BY_CATEGORY.items()
        for name in names
    }
    core_pairs = {(item["category"], item["name"]) for item in CORE_ITEMS}
    assert core_pairs == manifest_pairs


def test_core_items_unique_keys_guardrails_and_deck():
    keys = [item["key"] for item in CORE_ITEMS]
    names = [item["name"] for item in CORE_ITEMS]
    assert len(keys) == len(set(keys))
    assert len(names) == len(set(names))
    for item in CORE_ITEMS:
        assert item_slug(item["name"]) == item["key"]
        for field in _REQUIRED_FIELDS:
            assert item.get(field) not in (None, "")
        assert len(str(item.get("summary") or "")) <= 300
        assert not _LORE_DENY.search(item["name"])
    assert any(item["name"] == "Deck of Many Things" for item in CORE_ITEMS)
    assert not any("Kwalish" in item["name"] for item in CORE_ITEMS)
    longsword = next(item for item in CORE_ITEMS if item["key"] == "longsword")
    assert longsword["type_data"]["damage_dice"] == "1d8"
    leather = next(item for item in CORE_ITEMS if item["key"] == "leather_armor")
    assert leather["type_data"]["ac_base"] == 11


def test_ensure_srd_items_idempotent_and_preserves_gm_edits():
    _, campaign = _make_gm_with_campaign()
    first = ensure_srd_items_for_campaign(campaign.id)
    db.session.commit()
    assert first["inserted"] == len(CORE_ITEMS)
    assert first["updated"] == 0

    row = Item.query.filter_by(
        campaign_id=campaign.id, origin_srd_key="longsword"
    ).first()
    assert row is not None
    assert row.content_source == "srd_5_1"
    assert isinstance(row.stats, dict)
    assert row.stats.get("category") == "martial_weapon"

    row.name = "GM Longsword"
    stats = dict(row.stats or {})
    stats["gm_edited"] = True
    row.stats = stats
    row.description = "Custom campaign text"
    db.session.commit()

    second = ensure_srd_items_for_campaign(campaign.id)
    db.session.commit()
    assert second["inserted"] == 0
    db.session.refresh(row)
    assert row.name == "GM Longsword"
    assert row.description == "Custom campaign text"
    assert second["skipped"] >= 1

    third = ensure_srd_items_for_campaign(campaign.id)
    db.session.commit()
    assert third["inserted"] == 0
    assert Item.query.filter_by(campaign_id=campaign.id).count() == len(CORE_ITEMS)
    assert ShopInventory.query.filter_by(campaign_id=campaign.id).count() == 0


def test_list_campaign_items_pagination_and_filter():
    _, campaign = _make_gm_with_campaign("gm-items-page")
    ensure_srd_items_for_campaign(campaign.id)
    db.session.commit()
    payload = list_campaign_items(campaign.id, q="longsword", page=1, limit=10)
    assert payload["total"] >= 1
    assert any(row["name"] == "Longsword" for row in payload["items"])
    payload2 = list_campaign_items(campaign.id, category="martial_weapon", limit=5)
    assert payload2["limit"] == 5
    assert payload2["pages"] >= 1


def test_gm_items_catalog_route(client):
    user, campaign = _make_gm_with_campaign("gm-items-route")
    seed_client_session(client, user, campaign_id=campaign.id)
    resp = client.get("/gm/items/catalog?q=shield")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] >= 1
    assert any("Shield" in row["name"] for row in data["items"])


def test_gm_view_items_seeds_catalog(client):
    user, campaign = _make_gm_with_campaign("gm-items-view")
    seed_client_session(client, user, campaign_id=campaign.id)
    resp = client.get("/gm/items/")
    assert resp.status_code == 200
    assert Item.query.filter_by(campaign_id=campaign.id).count() == len(CORE_ITEMS)


def test_gm_dashboard_has_world_item_compendium_tab(client):
    user, campaign = _make_gm_with_campaign("gm-items-dashboard")
    seed_client_session(client, user, campaign_id=campaign.id)
    resp = client.get("/gm/")
    assert resp.status_code == 200
    assert b"Item Compendium" in resp.data
    assert b'data-target="items-pane-content"' in resp.data
    assert b'id="items-compendium-body"' in resp.data
    assert b"Nation Compendium" in resp.data
    assert b'data-target="regions-pane-content"' in resp.data
    assert b'id="regions-compendium-body"' in resp.data
    assert b"City Compendium" in resp.data
    assert b'data-target="cities-pane-content"' in resp.data
    assert b'id="cities-compendium-body"' in resp.data
    assert b"Shop Compendium" in resp.data
    assert b'data-target="shops-pane-content"' in resp.data
    assert b'id="shops-compendium-body"' in resp.data
    assert b"volatility-form" in resp.data
    assert b'name="return_anchor" value="market-pane-content"' in resp.data
    assert b"Open full manager" not in resp.data
    assert b"Open city list" not in resp.data
    assert b"activateDashboardHash" in resp.data
    market_pane_start = resp.data.index(b'id="market-pane-content"')
    market_table_start = resp.data.index(b'id="market-table-body"')
    market_pane = resp.data[market_pane_start:market_table_start]
    assert b"market-simulation-controls" in market_pane
    assert b"market-meta-summary" in market_pane
    assert b"Run day" in market_pane
    assert b"Run week" in market_pane
    assert b"Run month" in market_pane
    assert b"Run year" in market_pane
    assert b"Pause" in market_pane
    assert b"Volatility applies on the next simulation tick" in resp.data


def test_legacy_dashboard_section_routes_redirect_to_panes(client):
    user, campaign = _make_gm_with_campaign("gm-dashboard-pane-redirects")
    seed_client_session(client, user, campaign_id=campaign.id)

    players = client.get("/gm/players/")
    cities = client.get("/gm/cities/")

    assert players.status_code == 302
    assert players.headers["Location"].endswith("/gm/#players-npcs-pane-content")
    assert cities.status_code == 302
    assert cities.headers["Location"].endswith("/gm/#cities-pane-content")


def test_market_quick_nav_posts_return_to_market_pane(client):
    user, campaign = _make_gm_with_campaign("gm-market-pane-posts")
    seed_client_session(client, user, campaign_id=campaign.id)

    volatility = client.post(
        "/gm/campaigns/market-volatility",
        data={"market_volatility": "8", "return_anchor": "market-pane-content"},
    )
    supply = client.post(
        "/gm/campaigns/supply-demand/toggle",
        data={"return_anchor": "market-pane-content"},
    )
    debt = client.post(
        "/gm/campaigns/debt/toggle",
        data={"return_anchor": "market-pane-content"},
    )

    for resp in (volatility, supply, debt):
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/gm/#market-pane-content")


def test_world_compendium_apis(client):
    user, campaign = _make_gm_with_campaign("gm-world-comp-api")
    region = Region(
        name="Northreach",
        campaign_id=campaign.id,
        local_flavor={"axis_position": 4},
    )
    db.session.add(region)
    db.session.flush()
    city = City(
        name="Frostford",
        size="Town",
        population=1200,
        region_id=region.id,
        campaign_id=campaign.id,
    )
    shop = Shop(name="Frostford Forge", campaign_id=campaign.id, type="Smithy")
    db.session.add_all([city, shop])
    db.session.flush()
    shop.cities.append(city)
    db.session.commit()

    seed_client_session(client, user, campaign_id=campaign.id)
    regions = client.get("/gm/regions/compendium").get_json()
    cities = client.get("/gm/cities/compendium").get_json()
    shops = client.get("/gm/shops/compendium").get_json()

    assert regions["total"] == 1
    assert regions["regions"][0]["name"] == "Northreach"
    assert regions["regions"][0]["city_count"] == 1
    assert cities["total"] == 1
    assert cities["cities"][0]["region"] == "Northreach"
    assert cities["cities"][0]["shop_count"] == 1
    assert shops["total"] == 1
    assert shops["shops"][0]["name"] == "Frostford Forge"
    assert shops["shops"][0]["cities"] == ["Frostford"]


def test_add_catalog_item_to_shop_without_duplicate_item_row(client):
    user, campaign = _make_gm_with_campaign("gm-items-shop")
    ensure_srd_items_for_campaign(campaign.id)
    db.session.commit()
    shop = Shop(name="Test Shop", campaign_id=campaign.id, type="General")
    db.session.add(shop)
    db.session.commit()
    catalog_row = Item.query.filter_by(
        campaign_id=campaign.id, origin_srd_key="dagger"
    ).first()
    assert catalog_row is not None
    before_count = Item.query.filter_by(campaign_id=campaign.id).count()
    seed_client_session(client, user, campaign_id=campaign.id)
    resp = client.post(
        f"/gm/shops/{shop.shop_id}/items/add",
        data={"item_id": catalog_row.item_id, "stock": 3, "dynamic_price": 50},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert Item.query.filter_by(campaign_id=campaign.id).count() == before_count
    inv = ShopInventory.query.filter_by(
        shop_id=shop.shop_id, item_id=catalog_row.item_id
    ).first()
    assert inv is not None
    assert inv.stock == 3


def test_equipment_slots_expanded():
    assert "main_hand" in ALL_EQUIPMENT_SLOTS
    assert "ring_1" in ALL_EQUIPMENT_SLOTS
    assert normalize_slot("weapon") == "main_hand"
    assert normalize_slot("armor") == "torso"


def test_player_equip_uses_srd_slot(client):
    user, campaign = _make_gm_with_campaign("gm-items-equip")
    ensure_srd_items_for_campaign(campaign.id)
    db.session.commit()
    player_user = User(username="pc-items", password="x", role="Player")
    player_user.set_password("Secret1!")
    db.session.add(player_user)
    db.session.commit()
    player = Player(user_id=player_user.id, campaign_id=campaign.id, currency=0)
    db.session.add(player)
    db.session.commit()
    leather = Item.query.filter_by(
        campaign_id=campaign.id, origin_srd_key="leather_armor"
    ).first()
    db.session.add(
        PlayerInventory(player_id=player.id, item_id=leather.item_id, quantity=1)
    )
    db.session.commit()

    seed_client_session(client, player_user, campaign_id=campaign.id, player_id=player.id)

    resp = client.post(f"/player/equip/{leather.item_id}", follow_redirects=True)
    assert resp.status_code == 200
    eq = PlayerEquipment.query.filter_by(player_id=player.id).first()
    assert eq is not None
    assert normalize_slot(eq.slot) == "torso"


def test_combat_snapshot_uses_equipped_weapon():
    _, campaign = _make_gm_with_campaign("gm-items-combat")
    ensure_srd_items_for_campaign(campaign.id)
    db.session.commit()
    player_user = User(username="pc-combat", password="x", role="Player")
    player_user.set_password("Secret1!")
    db.session.add(player_user)
    db.session.commit()
    player = Player(user_id=player_user.id, campaign_id=campaign.id, currency=0)
    db.session.add(player)
    db.session.commit()
    db.session.add(
        PlayerCharacterSheet(
            player_id=player.id,
            campaign_id=campaign.id,
            sheet_json={
                "level": 3,
                "abilities": {"str": 16, "dex": 14, "con": 12, "int": 10, "wis": 10, "cha": 8},
                "defenses": {"hp_max": 20, "hp_current": 20, "ac": 10},
            },
        )
    )
    longsword = Item.query.filter_by(
        campaign_id=campaign.id, origin_srd_key="longsword"
    ).first()
    db.session.add(
        PlayerEquipment(player_id=player.id, slot="main_hand", item_id=longsword.item_id)
    )
    db.session.commit()

    encounter = encounter_service.create_encounter(campaign.id)
    combatant = encounter_service.add_player_combatant(encounter, player, campaign)
    db.session.commit()

    attacks = (combatant.action_data_json or {}).get("attacks") or []
    assert any(a.get("damage") == "1d8+3" for a in attacks)
    assert combatant.ac >= 12
    equipment = (combatant.action_data_json or {}).get("equipment") or {}
    assert equipment.get("items")

    # Snapshot is stable when catalog row changes later.
    longsword.stats = {"category": "martial_weapon", "type_data": {"damage_dice": "2d6"}}
    db.session.commit()
    db.session.refresh(combatant)
    attacks_after = (combatant.action_data_json or {}).get("attacks") or []
    assert any(a.get("damage") == "1d8+3" for a in attacks_after)


def test_gm_view_items_has_bulk_toolbar(client):
    user, campaign = _make_gm_with_campaign("gm-items-bulk-ui")
    seed_client_session(client, user, campaign_id=campaign.id)
    resp = client.get("/gm/items/")
    assert resp.status_code == 200
    assert b"select-all-items" in resp.data
    assert b"bulk-delete-btn" in resp.data
    assert b"Import Templates" in resp.data
    assert b"Folders" in resp.data


def test_bulk_stock_items_route(client):
    user, campaign = _make_gm_with_campaign("gm-items-bulk-stock")
    ensure_srd_items_for_campaign(campaign.id)
    db.session.commit()
    shop_a = Shop(name="Shop A", campaign_id=campaign.id, type="General")
    shop_b = Shop(name="Shop B", campaign_id=campaign.id, type="General")
    db.session.add_all([shop_a, shop_b])
    db.session.commit()
    dagger = Item.query.filter_by(
        campaign_id=campaign.id, origin_srd_key="dagger"
    ).first()
    longsword = Item.query.filter_by(
        campaign_id=campaign.id, origin_srd_key="longsword"
    ).first()
    seed_client_session(client, user, campaign_id=campaign.id)
    resp = client.post(
        "/gm/items/bulk/stock",
        data={
            "item_ids": [dagger.item_id, longsword.item_id],
            "shop_ids": [shop_a.shop_id, shop_b.shop_id],
            "stock": 4,
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert ShopInventory.query.filter_by(campaign_id=campaign.id).count() == 4
    inv = ShopInventory.query.filter_by(
        shop_id=shop_a.shop_id, item_id=dagger.item_id
    ).first()
    assert inv is not None
    assert inv.stock == 4


def test_bulk_delete_skips_stocked_items(client):
    user, campaign = _make_gm_with_campaign("gm-items-bulk-del")
    ensure_srd_items_for_campaign(campaign.id)
    db.session.commit()
    shop = Shop(name="Del Shop", campaign_id=campaign.id, type="General")
    db.session.add(shop)
    db.session.commit()
    stocked = Item.query.filter_by(
        campaign_id=campaign.id, origin_srd_key="dagger"
    ).first()
    free = Item.query.filter_by(
        campaign_id=campaign.id, origin_srd_key="longsword"
    ).first()
    assert stocked is not None and free is not None
    db.session.add(
        ShopInventory(
            shop_id=shop.shop_id,
            item_id=stocked.item_id,
            campaign_id=campaign.id,
            stock=1,
            dynamic_price=10,
        )
    )
    db.session.commit()
    seed_client_session(client, user, campaign_id=campaign.id)
    resp = client.post(
        "/gm/items/bulk/delete",
        data=MultiDict(
            [
                ("item_ids", str(stocked.item_id)),
                ("item_ids", str(free.item_id)),
            ]
        ),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert Item.query.filter_by(item_id=stocked.item_id).first() is not None
    assert Item.query.filter_by(item_id=free.item_id).first() is None


def test_bulk_rename_items_route(client):
    user, campaign = _make_gm_with_campaign("gm-items-bulk-rename")
    ensure_srd_items_for_campaign(campaign.id)
    db.session.commit()
    row = Item.query.filter_by(
        campaign_id=campaign.id, origin_srd_key="dagger"
    ).first()
    seed_client_session(client, user, campaign_id=campaign.id)
    resp = client.post(
        "/gm/items/bulk/rename",
        data={"item_ids": [row.item_id], "prefix": "Enchanted "},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.expire_all()
    row = Item.query.filter_by(item_id=row.item_id).first()
    assert row.name.startswith("Enchanted")


def test_item_folder_create_and_move(client):
    user, campaign = _make_gm_with_campaign("gm-items-folder")
    ensure_srd_items_for_campaign(campaign.id)
    db.session.commit()
    seed_client_session(client, user, campaign_id=campaign.id)
    resp = client.post(
        "/gm/items/folders/add",
        data={"name": "Weapons"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    folder = ItemFolder.query.filter_by(campaign_id=campaign.id, name="Weapons").first()
    assert folder is not None
    dagger = Item.query.filter_by(
        campaign_id=campaign.id, origin_srd_key="dagger"
    ).first()
    resp2 = client.post(
        "/gm/items/bulk/move-folder",
        data={"item_ids": [dagger.item_id], "folder_id": folder.folder_id},
        follow_redirects=True,
    )
    assert resp2.status_code == 200
    db.session.refresh(dagger)
    assert dagger.folder_id == folder.folder_id
    resp3 = client.get(f"/gm/items/?folder_id={folder.folder_id}")
    assert resp3.status_code == 200
    assert b"Dagger" in resp3.data


def test_item_template_import_route(client):
    user, campaign = _make_gm_with_campaign("gm-items-template")
    seed_client_session(client, user, campaign_id=campaign.id)
    resp = client.get("/gm/items/templates")
    assert resp.status_code == 200
    assert b"SRD 5.1" in resp.data
    before = Item.query.filter_by(campaign_id=campaign.id).count()
    resp2 = client.post(
        "/gm/items/templates/import",
        data={"template_key": "srd_5_1"},
        follow_redirects=True,
    )
    assert resp2.status_code == 200
    assert Item.query.filter_by(campaign_id=campaign.id).count() == len(CORE_ITEMS)
    assert before < len(CORE_ITEMS)


def test_bulk_remove_shop_items(client):
    user, campaign = _make_gm_with_campaign("gm-items-bulk-remove")
    ensure_srd_items_for_campaign(campaign.id)
    db.session.commit()
    shop = Shop(name="Remove Shop", campaign_id=campaign.id, type="General")
    db.session.add(shop)
    db.session.commit()
    dagger = Item.query.filter_by(
        campaign_id=campaign.id, origin_srd_key="dagger"
    ).first()
    club = Item.query.filter_by(
        campaign_id=campaign.id, origin_srd_key="club"
    ).first()
    for item in (dagger, club):
        db.session.add(
            ShopInventory(
                shop_id=shop.shop_id,
                item_id=item.item_id,
                campaign_id=campaign.id,
                stock=2,
                dynamic_price=5,
            )
        )
    db.session.commit()
    seed_client_session(client, user, campaign_id=campaign.id)
    resp = client.post(
        f"/gm/shops/{shop.shop_id}/items/bulk-remove",
        data={"item_ids": [dagger.item_id]},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert ShopInventory.query.filter_by(
        shop_id=shop.shop_id, item_id=dagger.item_id
    ).first() is None
    assert ShopInventory.query.filter_by(
        shop_id=shop.shop_id, item_id=club.item_id
    ).first() is not None

