"""D&D 5e SRD 5.1 monster seed catalog (CC-BY-4.0 mechanical shells).

Attribution: System Reference Document 5.1, Wizards of the Coast LLC,
available under Creative Commons Attribution 4.0 International (CC-BY-4.0).
Product Identity names are excluded.
"""

from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.services.combat.srd_monster_manifest import SRD_MONSTER_COUNT

_DATA_PATH = Path(__file__).resolve().parents[1] / "combat" / "data" / "srd_monsters_5_1.json"


@lru_cache(maxsize=1)
def _load_catalog() -> list[dict[str, Any]]:
    payload = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    rows = payload.get("monsters") or []
    if len(rows) != SRD_MONSTER_COUNT:
        raise RuntimeError(
            f"SRD monster catalog mismatch: manifest={SRD_MONSTER_COUNT}, data={len(rows)}"
        )
    return rows


CORE_MONSTERS: list[dict[str, Any]] = _load_catalog()


def monster_to_stat_json(entry: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy of the compendium stat block for persistence."""
    return deepcopy(entry.get("stat_json") or {})
