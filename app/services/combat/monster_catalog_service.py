"""Idempotent SRD monster seeding into campaign monster compendium rows."""

from __future__ import annotations

from typing import Any

from app.extensions import db
from app.models import Campaign, MonsterCompendiumEntry
from app.services.character_creation.dnd5e_monsters import CORE_MONSTERS, monster_to_stat_json
from app.services.combat.monster_compendium_service import _validated_stats


class MonsterCatalogError(ValueError):
    """Raised when monster catalog operations fail validation."""


def seed_srd_monsters_if_dnd5e(campaign_id: int, system_type: str | None) -> dict[str, int] | None:
    """Seed SRD monsters when ``system_type`` is dnd5e; no-op otherwise."""
    if (system_type or "").lower() != "dnd5e":
        return None
    return ensure_srd_monsters_for_campaign(campaign_id)


def ensure_srd_monsters_for_campaign(
    campaign_id: int, *, refresh_seed: bool = False
) -> dict[str, int]:
    """Insert missing SRD monsters for a D&D 5e campaign. Returns counts."""
    campaign = Campaign.query.filter_by(id=campaign_id).first()
    if campaign is None:
        raise MonsterCatalogError("Campaign not found.")
    if (getattr(campaign, "system_type", None) or "").lower() != "dnd5e":
        return {"inserted": 0, "updated": 0, "skipped": len(CORE_MONSTERS)}

    existing = {
        row.origin_srd_key: row
        for row in MonsterCompendiumEntry.query.filter_by(campaign_id=campaign_id).all()
        if row.origin_srd_key
    }
    inserted = 0
    updated = 0
    skipped = 0

    for entry in CORE_MONSTERS:
        key = str(entry.get("origin_srd_key") or entry["key"])
        row = existing.get(key)
        stats = monster_to_stat_json(entry)
        if row is None:
            db.session.add(
                MonsterCompendiumEntry(
                    campaign_id=campaign_id,
                    name=str(entry["name"])[:120],
                    source="srd_5_1",
                    origin_srd_key=key[:80],
                    challenge_rating=entry.get("challenge_rating"),
                    stat_json=_validated_stats(stats),
                )
            )
            inserted += 1
            continue

        row_stats = row.stat_json if isinstance(row.stat_json, dict) else {}
        if row_stats.get("gm_edited") and not refresh_seed:
            skipped += 1
            continue
        if refresh_seed or row.source == "srd_5_1":
            row.name = str(entry["name"])[:120]
            row.source = "srd_5_1"
            row.origin_srd_key = key[:80]
            row.challenge_rating = entry.get("challenge_rating")
            if not row_stats.get("gm_edited"):
                row.stat_json = _validated_stats(stats)
            updated += 1
        else:
            skipped += 1

    db.session.flush()
    return {"inserted": inserted, "updated": updated, "skipped": skipped}
