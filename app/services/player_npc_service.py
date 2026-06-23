"""Player-facing known NPC profiles and personal notes."""

from __future__ import annotations

from app.extensions import db
from app.models import City, Player, PlayerNpcNote, Region, Shop
from app.services import character_sheet_service


def _background_display(campaign_id: int, sheet: dict) -> str | None:
    creation = sheet.get("creation") if isinstance(sheet.get("creation"), dict) else {}
    key = str(creation.get("background_key") or "").strip().lower()
    if not key:
        return None
    try:
        from app.services.character_creation.campaign_settings import (
            get_character_options,
        )
        from app.services.character_creation.creation_service import catalog_entry_by_key
        from app.services.character_creation.dnd5e_catalog import build_catalog

        catalog = build_catalog(character_options=get_character_options(campaign_id))
        entry = catalog_entry_by_key(catalog, "backgrounds", key)
        if entry and entry.get("name"):
            return str(entry["name"]).strip()
    except Exception:
        pass
    return key.replace("_", " ").title()


def _npc_locations(npc_id: int, campaign_id: int) -> list[dict]:
    locations: list[dict] = []
    for region in Region.query.filter_by(
        campaign_id=campaign_id, ruler_player_id=npc_id
    ).order_by(Region.name.asc()):
        locations.append({"kind": "ruler", "label": f"Ruler of {region.name}"})
    for city in City.query.filter_by(
        campaign_id=campaign_id, owner_player_id=npc_id
    ).order_by(City.name.asc()):
        locations.append({"kind": "city_owner", "label": f"Owner of {city.name}"})
    for shop in Shop.query.filter_by(
        campaign_id=campaign_id, owner_player_id=npc_id
    ).order_by(Shop.name.asc()):
        locations.append({"kind": "shop_owner", "label": f"Owner of {shop.name}"})
    return locations


def build_npc_lore_profile(npc: Player, campaign) -> dict:
    """Soft lore fields for player NPC detail — no combat stats."""
    sheet = character_sheet_service.get_or_default_sheet(npc, campaign)
    name = (sheet.get("name") or "").strip() or f"NPC #{npc.id}"
    species = (sheet.get("species") or "").strip() or None
    class_name = (sheet.get("class_name") or "").strip() or None
    level = sheet.get("level")
    background = _background_display(npc.campaign_id, sheet)
    about = (sheet.get("notes") or "").strip() or None
    locations = _npc_locations(npc.id, npc.campaign_id)
    location_summary = ", ".join(row["label"] for row in locations) or None
    return {
        "id": npc.id,
        "name": name,
        "species": species,
        "class_name": class_name,
        "level": level,
        "background": background,
        "about": about,
        "locations": locations,
        "location_summary": location_summary,
    }


def get_player_npc_notes(viewer_player_id: int, npc_player_id: int) -> str:
    row = PlayerNpcNote.query.filter_by(
        viewer_player_id=viewer_player_id,
        npc_player_id=npc_player_id,
    ).first()
    return (row.notes or "").strip() if row else ""


def save_player_npc_notes(
    *,
    campaign_id: int,
    viewer_player_id: int,
    npc_player_id: int,
    notes: str,
) -> str:
    cleaned = (notes or "").strip()
    row = PlayerNpcNote.query.filter_by(
        viewer_player_id=viewer_player_id,
        npc_player_id=npc_player_id,
    ).first()
    if not cleaned:
        if row is not None:
            db.session.delete(row)
        db.session.flush()
        return ""
    if row is None:
        row = PlayerNpcNote(
            campaign_id=campaign_id,
            viewer_player_id=viewer_player_id,
            npc_player_id=npc_player_id,
            notes=cleaned,
        )
        db.session.add(row)
    else:
        row.campaign_id = campaign_id
        row.notes = cleaned
    db.session.flush()
    return cleaned
