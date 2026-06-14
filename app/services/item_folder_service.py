"""Campaign-scoped item folder CRUD and bulk move operations."""

from __future__ import annotations

from typing import Any

from app.extensions import db
from app.models import Item, ItemFolder
from app.services.shop_inventory_service import BulkActionResult, _campaign_item_ids


class ItemFolderError(ValueError):
    """Raised when folder operations fail validation."""


def list_campaign_folders(campaign_id: int) -> list[ItemFolder]:
    return (
        ItemFolder.query.filter_by(campaign_id=campaign_id)
        .order_by(ItemFolder.sort_order.asc(), ItemFolder.name.asc())
        .all()
    )


def folder_for_campaign_or_none(campaign_id: int, folder_id: int | None) -> ItemFolder | None:
    if folder_id is None:
        return None
    return ItemFolder.query.filter_by(
        folder_id=folder_id,
        campaign_id=campaign_id,
    ).first()


def create_folder(
    campaign_id: int,
    *,
    name: str,
    parent_id: int | None = None,
    sort_order: int = 0,
) -> ItemFolder:
    name = (name or "").strip()
    if not name:
        raise ItemFolderError("Folder name is required.")
    if len(name) > 100:
        raise ItemFolderError("Folder name must be 100 characters or fewer.")
    if parent_id is not None:
        parent = folder_for_campaign_or_none(campaign_id, parent_id)
        if parent is None:
            raise ItemFolderError("Parent folder not found in this campaign.")
    row = ItemFolder(
        campaign_id=campaign_id,
        name=name,
        parent_id=parent_id,
        sort_order=int(sort_order or 0),
    )
    db.session.add(row)
    db.session.flush()
    return row


def rename_folder(campaign_id: int, folder_id: int, *, name: str) -> ItemFolder:
    row = folder_for_campaign_or_none(campaign_id, folder_id)
    if row is None:
        raise ItemFolderError("Folder not found.")
    name = (name or "").strip()
    if not name:
        raise ItemFolderError("Folder name is required.")
    row.name = name[:100]
    return row


def delete_folder(campaign_id: int, folder_id: int) -> None:
    row = folder_for_campaign_or_none(campaign_id, folder_id)
    if row is None:
        raise ItemFolderError("Folder not found.")
    Item.query.filter_by(campaign_id=campaign_id, folder_id=folder_id).update(
        {"folder_id": None},
        synchronize_session=False,
    )
    ItemFolder.query.filter_by(campaign_id=campaign_id, parent_id=folder_id).update(
        {"parent_id": None},
        synchronize_session=False,
    )
    db.session.delete(row)


def bulk_move_items_to_folder(
    campaign_id: int,
    item_ids: list[int],
    folder_id: int | None,
) -> BulkActionResult:
    result = BulkActionResult()
    valid = _campaign_item_ids(campaign_id, item_ids)
    if not valid:
        result.errors.append("No valid catalog items selected.")
        return result
    if folder_id is not None and folder_for_campaign_or_none(campaign_id, folder_id) is None:
        result.errors.append("Target folder not found in this campaign.")
        return result

    for item_id in sorted(valid):
        item = Item.query.filter_by(item_id=item_id, campaign_id=campaign_id).first()
        if item is None:
            result.skipped += 1
            continue
        item.folder_id = folder_id
        result.processed += 1
    return result


def folders_as_tree(campaign_id: int) -> list[dict[str, Any]]:
    """Nested folder dicts for GM UI rendering."""
    rows = list_campaign_folders(campaign_id)
    by_id = {row.folder_id: row for row in rows}
    nodes: dict[int, dict[str, Any]] = {
        row.folder_id: {
            "folder_id": row.folder_id,
            "name": row.name,
            "parent_id": row.parent_id,
            "sort_order": row.sort_order,
            "children": [],
        }
        for row in rows
    }
    roots: list[dict[str, Any]] = []
    for row in rows:
        node = nodes[row.folder_id]
        if row.parent_id and row.parent_id in nodes:
            nodes[row.parent_id]["children"].append(node)
        else:
            roots.append(node)
    return roots
