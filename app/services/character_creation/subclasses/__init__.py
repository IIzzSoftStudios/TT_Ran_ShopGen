"""SRD 5.1 subclass seeds grouped by parent class."""

from __future__ import annotations

from typing import Any

from app.services.character_creation.subclasses import (
    barbarian,
    bard,
    cleric,
    druid,
    fighter,
    monk,
    paladin,
    ranger,
    rogue,
    sorcerer,
    warlock,
    wizard,
)
from app.services.character_creation.subclasses._helpers import CURRENT_SRD_SUBCLASSES_SEED_VERSION

_CLASS_MODULES = (
    barbarian,
    bard,
    cleric,
    druid,
    fighter,
    monk,
    paladin,
    ranger,
    rogue,
    sorcerer,
    warlock,
    wizard,
)

_by_class: dict[str, list[dict[str, Any]]] = {}
for _mod in _CLASS_MODULES:
    for _entry in _mod.SUBCLASSES:
        _class_key = str(_entry.get("class_key") or "").strip().lower()
        if _class_key:
            _by_class.setdefault(_class_key, []).append(_entry)

CORE_SUBCLASSES_BY_CLASS: dict[str, tuple[dict[str, Any], ...]] = {
    key: tuple(entries) for key, entries in _by_class.items()
}

ALL_CORE_SUBCLASSES: tuple[dict[str, Any], ...] = tuple(
    entry for entries in CORE_SUBCLASSES_BY_CLASS.values() for entry in entries
)

__all__ = [
    "ALL_CORE_SUBCLASSES",
    "CORE_SUBCLASSES_BY_CLASS",
    "CURRENT_SRD_SUBCLASSES_SEED_VERSION",
]
