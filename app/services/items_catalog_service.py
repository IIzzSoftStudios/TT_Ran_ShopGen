"""Idempotent SRD item seeding into relational Item catalog rows."""

from __future__ import annotations

from typing import Any

from app.extensions import db
from app.models import Campaign, Item
from app.services.character_creation.dnd5e_items import CORE_ITEMS, item_to_stats


class ItemsCatalogError(ValueError):
    """Raised when item catalog operations fail validation."""


def _core_entry_to_item_fields(entry: dict[str, Any], campaign_id: int) -> dict[str, Any]:
    stats = item_to_stats(entry)
    return {
        "name": str(entry["name"])[:100],
        "type": str(entry.get("type") or "General")[:50],
        "rarity": str(entry.get("rarity") or "Common")[:50],
        "base_price": max(0, int(entry.get("base_price_copper") or 0)),
        "description": str(entry.get("summary") or "")[:500],
        "range": entry.get("range"),
        "damage": entry.get("damage"),
        "min_str": entry.get("min_str"),
        "notes": str(entry.get("srd_reference") or "SRD 5.1")[:500],
        "campaign_id": campaign_id,
        "stats": stats,
        "origin_srd_key": str(entry.get("origin_srd_key") or entry["key"])[:80],
        "content_source": "srd_5_1",
        "axis_position": 5,
    }


def ensure_srd_items_for_campaign(campaign_id: int, *, refresh_seed: bool = False) -> dict[str, int]:
    """Insert missing SRD items for a D&D 5e campaign. Returns counts."""
    campaign = Campaign.query.filter_by(id=campaign_id).first()
    if campaign is None:
        raise ItemsCatalogError("Campaign not found.")
    if (getattr(campaign, "system_type", None) or "").lower() != "dnd5e":
        return {"inserted": 0, "updated": 0, "skipped": len(CORE_ITEMS)}

    existing = {
        row.origin_srd_key: row
        for row in Item.query.filter_by(campaign_id=campaign_id).all()
        if row.origin_srd_key
    }
    inserted = 0
    updated = 0
    skipped = 0

    for entry in CORE_ITEMS:
        key = str(entry.get("origin_srd_key") or entry["key"])
        fields = _core_entry_to_item_fields(entry, campaign_id)
        row = existing.get(key)
        if row is None:
            db.session.add(Item(**fields))
            inserted += 1
            continue
        stats = row.stats if isinstance(row.stats, dict) else {}
        if stats.get("gm_edited") and not refresh_seed:
            skipped += 1
            continue
        if refresh_seed or row.content_source == "srd_5_1":
            row.name = fields["name"]
            row.type = fields["type"]
            row.rarity = fields["rarity"]
            if not stats.get("gm_edited"):
                row.base_price = fields["base_price"]
                row.description = fields["description"]
                row.range = fields["range"]
                row.damage = fields["damage"]
                row.min_str = fields["min_str"]
                row.stats = fields["stats"]
            row.content_source = "srd_5_1"
            updated += 1
        else:
            skipped += 1

    db.session.flush()
    return {"inserted": inserted, "updated": updated, "skipped": skipped}


def list_campaign_items(
    campaign_id: int,
    *,
    q: str = "",
    category: str = "",
    folder_id: int | None = None,
    uncategorized_only: bool = False,
    page: int = 1,
    limit: int = 50,
) -> dict[str, Any]:
    """Paginated campaign item catalog for GM picker flows."""
    page = max(1, int(page or 1))
    limit = max(1, min(100, int(limit or 50)))
    query = Item.query.filter_by(campaign_id=campaign_id)
    if folder_id is not None:
        query = query.filter(Item.folder_id == folder_id)
    elif uncategorized_only:
        query = query.filter(Item.folder_id.is_(None))
    if q:
        needle = f"%{q.strip().lower()}%"
        query = query.filter(db.func.lower(Item.name).like(needle))
    rows_all = query.order_by(Item.name.asc()).all()
    if category:
        cat = category.strip().lower()
        rows_all = [
            row
            for row in rows_all
            if isinstance(row.stats, dict)
            and str(row.stats.get("category") or "").lower() == cat
        ]
    total = len(rows_all)
    start = (page - 1) * limit
    rows = rows_all[start : start + limit]
    return {
        "items": [
            {
                "item_id": row.item_id,
                "name": row.name,
                "type": row.type,
                "rarity": row.rarity,
                "base_price": row.base_price,
                "origin_srd_key": row.origin_srd_key,
                "content_source": row.content_source,
                "category": (row.stats or {}).get("category") if isinstance(row.stats, dict) else None,
                "folder_id": row.folder_id,
            }
            for row in rows
        ],
        "page": page,
        "limit": limit,
        "total": total,
        "pages": max(1, (total + limit - 1) // limit),
    }
