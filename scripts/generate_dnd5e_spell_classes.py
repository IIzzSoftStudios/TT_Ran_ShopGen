"""Generate SRD spell class availability from the D&D 5e API.

This is an offline maintenance helper. Runtime code imports the generated
module and never calls the public API.
"""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "app/services/character_creation/dnd5e_spell_classes.py"
API_BASE = "https://www.dnd5eapi.co"

EXTRA_CLASS_MAP = {
    "arms_of_hadar": ["warlock"],
    "banishing_smite": ["paladin"],
    "beast_sense": ["druid", "ranger"],
    "blade_ward": ["bard", "sorcerer", "warlock", "wizard"],
    "circle_of_power": ["paladin"],
    "compelled_duel": ["paladin"],
    "conjure_barrage": ["ranger"],
    "create_bonfire": ["druid", "sorcerer", "warlock", "wizard"],
    "destructive_wave": ["paladin"],
    "ensnaring_strike": ["ranger"],
    "feign_death": ["bard", "cleric", "druid", "wizard"],
    "frostbite": ["druid", "sorcerer", "warlock", "wizard"],
    "lightning_arrow": ["ranger"],
    "phantasmal_force": ["bard", "sorcerer", "wizard"],
    "searing_smite": ["paladin"],
    "thunderous_smite": ["paladin"],
    "toll_the_dead": ["cleric", "warlock", "wizard"],
    "tsunami": ["druid"],
    "word_of_radiance": ["cleric"],
    "wrathful_smite": ["paladin"],
}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name or "").strip().lower()).strip("_")


def _fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)


def main() -> None:
    listing = _fetch_json(f"{API_BASE}/api/2014/spells")
    class_map: dict[str, list[str]] = {}
    for item in sorted(listing.get("results") or [], key=lambda row: row["index"]):
        detail = _fetch_json(f"{API_BASE}{item['url']}")
        classes = [
            str(row.get("index") or row.get("name") or "").strip().lower()
            for row in detail.get("classes") or []
            if str(row.get("index") or row.get("name") or "").strip()
        ]
        class_map[_slug(detail.get("name") or item["index"])] = sorted(set(classes))
    class_map.update(EXTRA_CLASS_MAP)

    lines = [
        '"""SRD 5.1 spell class availability generated from dnd5eapi.co.',
        "",
        "The data is checked into the repository so runtime code does not call",
        "external services. Values are lowercase D&D class keys.",
        '"""',
        "",
        "SPELL_CLASSES_BY_KEY = {",
    ]
    for key, classes in sorted(class_map.items()):
        lines.append(f"    {key!r}: {classes!r},")
    lines.extend(["}", ""])
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT} ({len(class_map)} spell class rows)")


if __name__ == "__main__":
    main()
