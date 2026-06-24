"""Build SRD 5.1 subclass seed modules from dnd5eapi.co (offline maintenance).

Fetches the 12 SRD subclasses (whitelist), writes a cached JSON snapshot, and
validates that per-class seed modules under app/services/character_creation/subclasses/
match the API feature levels. Re-run after SRD updates; runtime never calls the API.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SOURCE = ROOT / "scripts" / "_srd_subclasses_source.json"
API_BASE = "https://www.dnd5eapi.co"

# SRD 5.1 subclass indices on dnd5eapi (2014 ruleset).
SRD_SUBCLASS_INDICES = frozenset(
    {
        "berserker",
        "lore",
        "life",
        "land",
        "champion",
        "open-hand",
        "devotion",
        "hunter",
        "thief",
        "draconic",
        "fiend",
        "evocation",
    }
)


def _fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)


def fetch_subclass_details() -> list[dict]:
    listing = _fetch_json(f"{API_BASE}/api/2014/subclasses")
    rows: list[dict] = []
    for item in sorted(listing.get("results") or [], key=lambda row: row["index"]):
        index = str(item.get("index") or "")
        if index not in SRD_SUBCLASS_INDICES:
            continue
        detail = _fetch_json(f"{API_BASE}{item['url']}")
        features: list[dict] = []
        for level_block in detail.get("subclass_levels") or []:
            if not isinstance(level_block, dict):
                continue
            try:
                level = int(level_block.get("level") or 0)
            except (TypeError, ValueError):
                continue
            for feat in level_block.get("features") or []:
                if isinstance(feat, dict):
                    name = str(feat.get("name") or "").strip()
                else:
                    name = str(feat or "").strip()
                if name:
                    features.append({"level": level, "name": name})
        rows.append(
            {
                "index": index,
                "name": detail.get("name"),
                "class": (detail.get("class") or {}).get("index"),
                "features": features,
            }
        )
    return rows


def validate_against_seeds(api_rows: list[dict]) -> list[str]:
    from app.services.character_creation.dnd5e_srd_subclasses import ALL_CORE_SUBCLASSES

    errors: list[str] = []
    api_by_index = {str(row["index"]): row for row in api_rows}
    index_map = {
        "path-of-the-berserker": "berserker",
        "college-of-lore": "lore",
        "life-domain": "life",
        "circle-of-the-land": "land",
        "champion": "champion",
        "way-of-the-open-hand": "open-hand",
        "oath-of-devotion": "devotion",
        "hunter": "hunter",
        "thief": "thief",
        "draconic-bloodline": "draconic",
        "the-fiend": "fiend",
        "school-of-evocation": "evocation",
    }
    for entry in ALL_CORE_SUBCLASSES:
        key = str(entry.get("key") or "")
        api_index = index_map.get(key)
        if not api_index or api_index not in api_by_index:
            errors.append(f"Missing API row for seed subclass {key!r}")
            continue
        api_feats = {
            (int(f["level"]), re.sub(r"\s+", " ", f["name"]).strip().lower())
            for f in api_by_index[api_index].get("features") or []
        }
        seed_feats = set()
        for grant in entry.get("feature_grants") or []:
            try:
                lvl = int(grant.get("level") or 0)
            except (TypeError, ValueError):
                continue
            name = re.sub(r"\s+", " ", str(grant.get("name") or "")).strip().lower()
            seed_feats.add((lvl, name))
        missing = api_feats - seed_feats
        if missing:
            errors.append(f"{key}: seed missing API features {sorted(missing)}")
    return errors


def main() -> None:
    try:
        rows = fetch_subclass_details()
    except Exception as exc:
        if SOURCE.exists():
            rows = json.loads(SOURCE.read_text(encoding="utf-8"))
            print(f"API fetch failed ({exc}); using cached {SOURCE}")
        else:
            raise
    else:
        SOURCE.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print(f"Wrote {SOURCE} ({len(rows)} subclasses)")

    errors = validate_against_seeds(rows)
    if errors:
        print("Validation warnings (seed modules may need updates):")
        for err in errors:
            print(f"  - {err}")
    else:
        print("Seed modules match API feature levels for all 12 SRD subclasses.")


if __name__ == "__main__":
    main()
