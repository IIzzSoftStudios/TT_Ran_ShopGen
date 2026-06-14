"""Campaign-scoped shop inventory upsert, bulk stock/remove, and bulk item actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

from sqlalchemy.orm.attributes import flag_modified

from app.extensions import db
from app.models import Item, PlayerInventory, Shop, ShopInventory


class ShopInventoryError(ValueError):
    """Raised when shop inventory operations fail validation."""


@dataclass
class BulkActionResult:
    """Summary counters for bulk GM item/inventory operations."""

    processed: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


def _parse_positive_ints(raw_ids: Iterable[str | int]) -> list[int]:
    out: list[int] = []
    for raw in raw_ids:
        try:
            val = int(raw)
            if val > 0:
                out.append(val)
        except (TypeError, ValueError):
            continue
    return out


def _campaign_shop_ids(campaign_id: int, shop_ids: Sequence[int]) -> set[int]:
    if not shop_ids:
        return set()
    rows = (
        Shop.query.filter(
            Shop.campaign_id == campaign_id,
            Shop.shop_id.in_(list(shop_ids)),
        )
        .with_entities(Shop.shop_id)
        .all()
    )
    return {row[0] for row in rows}


def _campaign_item_ids(campaign_id: int, item_ids: Sequence[int]) -> set[int]:
    if not item_ids:
        return set()
    rows = (
        Item.query.filter(
            Item.campaign_id == campaign_id,
            Item.item_id.in_(list(item_ids)),
        )
        .with_entities(Item.item_id)
        .all()
    )
    return {row[0] for row in rows}


def upsert_shop_inventory(
    campaign_id: int,
    *,
    shop_id: int,
    item_id: int,
    stock: int = 0,
    dynamic_price: float | None = None,
) -> ShopInventory:
    """Upsert one ``ShopInventory`` row for an existing campaign catalog item."""
    if shop_id not in _campaign_shop_ids(campaign_id, [shop_id]):
        raise ShopInventoryError("Shop not found in this campaign.")
    if item_id not in _campaign_item_ids(campaign_id, [item_id]):
        raise ShopInventoryError("Item not found in this campaign catalog.")

    item = Item.query.filter_by(item_id=item_id, campaign_id=campaign_id).first()
    if item is None:
        raise ShopInventoryError("Item not found in this campaign catalog.")
    if dynamic_price is None:
        dynamic_price = float(item.base_price or 0)

    inv = ShopInventory.query.filter_by(
        shop_id=shop_id,
        item_id=item_id,
        campaign_id=campaign_id,
    ).first()
    if inv:
        inv.stock = int(stock)
        inv.dynamic_price = float(dynamic_price)
    else:
        inv = ShopInventory(
            shop_id=shop_id,
            item_id=item_id,
            campaign_id=campaign_id,
            stock=int(stock),
            dynamic_price=float(dynamic_price),
        )
        db.session.add(inv)
    return inv


def bulk_stock_items(
    campaign_id: int,
    *,
    item_ids: Sequence[int],
    shop_ids: Sequence[int],
    stock: int = 1,
    dynamic_price: float | None = None,
) -> BulkActionResult:
    """Stock multiple catalog items into multiple shops (upsert, one commit)."""
    result = BulkActionResult()
    valid_items = _campaign_item_ids(campaign_id, item_ids)
    valid_shops = _campaign_shop_ids(campaign_id, shop_ids)
    if not valid_items:
        result.errors.append("No valid catalog items selected.")
        return result
    if not valid_shops:
        result.errors.append("No valid shops selected.")
        return result

    price_cache: dict[int, float] = {}
    for item_id in sorted(valid_items):
        item = Item.query.filter_by(item_id=item_id, campaign_id=campaign_id).first()
        if item is None:
            result.skipped += 1
            continue
        price_cache[item_id] = (
            float(dynamic_price)
            if dynamic_price is not None
            else float(item.base_price or 0)
        )
        for shop_id in sorted(valid_shops):
            upsert_shop_inventory(
                campaign_id,
                shop_id=shop_id,
                item_id=item_id,
                stock=stock,
                dynamic_price=price_cache[item_id],
            )
            result.processed += 1
    return result


def bulk_remove_from_shop(
    campaign_id: int,
    *,
    shop_id: int,
    item_ids: Sequence[int],
) -> BulkActionResult:
    """Remove selected items from one shop's inventory."""
    result = BulkActionResult()
    if shop_id not in _campaign_shop_ids(campaign_id, [shop_id]):
        result.errors.append("Shop not found in this campaign.")
        return result
    valid_items = _campaign_item_ids(campaign_id, item_ids)
    if not valid_items:
        result.errors.append("No valid catalog items selected.")
        return result

    rows = ShopInventory.query.filter(
        ShopInventory.campaign_id == campaign_id,
        ShopInventory.shop_id == shop_id,
        ShopInventory.item_id.in_(list(valid_items)),
    ).all()
    for row in rows:
        db.session.delete(row)
        result.processed += 1
    result.skipped = len(valid_items) - result.processed
    return result


def items_blocked_from_delete(campaign_id: int, item_ids: Sequence[int]) -> dict[int, str]:
    """Return item_id -> reason for items that cannot be deleted safely."""
    valid = _campaign_item_ids(campaign_id, item_ids)
    blocked: dict[int, str] = {}
    if not valid:
        return blocked

    stocked = {
        row[0]
        for row in db.session.query(ShopInventory.item_id)
        .filter(
            ShopInventory.campaign_id == campaign_id,
            ShopInventory.item_id.in_(list(valid)),
        )
        .distinct()
        .all()
    }
    for item_id in stocked:
        blocked[item_id] = "Item is stocked in at least one shop."

    owned = {
        row[0]
        for row in db.session.query(PlayerInventory.item_id)
        .filter(PlayerInventory.item_id.in_(list(valid)))
        .distinct()
        .all()
    }
    for item_id in owned:
        if item_id not in blocked:
            blocked[item_id] = "Item is held by at least one player."
    return blocked


def bulk_delete_items(campaign_id: int, item_ids: Sequence[int]) -> BulkActionResult:
    """Delete catalog items not stocked or player-owned."""
    result = BulkActionResult()
    valid = _campaign_item_ids(campaign_id, item_ids)
    if not valid:
        result.errors.append("No valid catalog items selected.")
        return result

    blocked = items_blocked_from_delete(campaign_id, list(valid))
    for item_id in sorted(valid):
        if item_id in blocked:
            result.skipped += 1
            result.errors.append(f"Item {item_id}: {blocked[item_id]}")
            continue
        item = Item.query.filter_by(item_id=item_id, campaign_id=campaign_id).first()
        if item is None:
            result.skipped += 1
            continue
        db.session.delete(item)
        result.processed += 1
    return result


def bulk_rename_items(
    campaign_id: int,
    item_ids: Sequence[int],
    *,
    prefix: str = "",
    suffix: str = "",
    find_text: str = "",
    replace_text: str = "",
) -> BulkActionResult:
    """Apply prefix/suffix and optional find/replace to selected item names."""
    result = BulkActionResult()
    valid = _campaign_item_ids(campaign_id, item_ids)
    if not valid:
        result.errors.append("No valid catalog items selected.")
        return result

    prefix = (prefix or "").strip()
    suffix = (suffix or "").strip()
    find_text = find_text or ""
    replace_text = replace_text or ""

    if not any([prefix, suffix, find_text]):
        result.errors.append("Provide a prefix, suffix, or find/replace pattern.")
        return result

    for item_id in sorted(valid):
        item = Item.query.filter_by(item_id=item_id, campaign_id=campaign_id).first()
        if item is None:
            result.skipped += 1
            continue
        name = item.name or ""
        if find_text:
            name = name.replace(find_text, replace_text)
        if prefix:
            name = f"{prefix}{name}"
        if suffix:
            name = f"{name}{suffix}"
        item.name = name[:100]
        stats = dict(item.stats) if isinstance(item.stats, dict) else {}
        stats["gm_edited"] = True
        item.stats = stats
        flag_modified(item, "stats")
        if item.content_source != "srd_5_1":
            item.content_source = "gm_custom"
        result.processed += 1
    return result


def parse_id_list(form_values: Iterable[str]) -> list[int]:
    """Parse checkbox/form id lists from request."""
    return _parse_positive_ints(form_values)
