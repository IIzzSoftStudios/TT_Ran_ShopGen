"""SRD subclass feature traits for the compendium.

Mechanical labels and sparse combat effects only — no copied book prose.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.services.character_creation.dnd5e_srd_subclasses import ALL_CORE_SUBCLASSES
from app.services.character_creation.subclasses._helpers import (
    CURRENT_SRD_SUBCLASSES_SEED_VERSION,
    trait_key_for_subclass_feature,
)

# Sparse mechanical effects keyed by trait key.
_TRAIT_EFFECTS: dict[str, dict[str, Any]] = {
    "scf-champion-improved-critical": {"crit_range": 19},
    "scf-champion-superior-critical": {"crit_range": 18},
    "scf-draconic-bloodline-draconic-resilience": {
        "unarmored_defense": True,
        "unarmored_ac_base": 13,
        "unarmored_ac_add_ability": "dex",
        "unarmored_defense_allows_shield": False,
    },
    "scf-life-domain-disciple-of-life": {"healing_bonus_per_level": 2},
}

_TRAIT_CATEGORIES: dict[str, str] = {
    "scf-champion-improved-critical": "attack",
    "scf-champion-superior-critical": "attack",
    "scf-draconic-bloodline-draconic-resilience": "defense",
    "scf-life-domain-disciple-of-life": "other",
}


def _build_trait(
    *,
    subclass_key: str,
    class_key: str,
    feature_name: str,
    summary: str,
    min_level: int,
) -> dict[str, Any]:
    key = trait_key_for_subclass_feature(subclass_key, feature_name)
    effects = deepcopy(_TRAIT_EFFECTS.get(key) or {})
    category = _TRAIT_CATEGORIES.get(key, "other")
    return {
        "key": key,
        "name": feature_name,
        "source": "base",
        "origin_template_key": key,
        "category": category,
        "effects": effects,
        "prerequisites": {
            "class_keys": [class_key],
            "subclass_keys": [subclass_key],
            "min_level": min_level,
        },
        "tags": sorted({class_key, subclass_key, "subclass-feature"}),
        "stacking": "max",
        "notes": "",
        "summary": summary[:500],
        "rules_text": "",
        "srd_reference": "SRD 5.1",
        "content_source": "srd-5.1",
        "gm_edited": False,
        "srd_seed_version": CURRENT_SRD_SUBCLASSES_SEED_VERSION,
    }


def build_srd_subclass_traits() -> tuple[dict[str, Any], ...]:
    """All SRD subclass feature traits."""
    by_key: dict[str, dict[str, Any]] = {}
    for subclass in ALL_CORE_SUBCLASSES:
        subclass_key = str(subclass.get("key") or "")
        class_key = str(subclass.get("class_key") or "")
        for grant in subclass.get("feature_grants") or []:
            if not isinstance(grant, dict):
                continue
            name = str(grant.get("name") or "").strip()
            if not name:
                continue
            try:
                min_level = max(1, int(grant.get("level") or 1))
            except (TypeError, ValueError):
                min_level = 1
            summary = str(grant.get("summary") or f"{name} (subclass feature).")
            trait_key = trait_key_for_subclass_feature(subclass_key, name)
            by_key[trait_key] = _build_trait(
                subclass_key=subclass_key,
                class_key=class_key,
                feature_name=name,
                summary=summary,
                min_level=min_level,
            )
    return tuple(by_key[k] for k in sorted(by_key.keys()))


SRD_SUBCLASS_TRAITS: tuple[dict[str, Any], ...] = ()
SRD_SUBCLASS_TRAITS_BY_KEY: dict[str, dict[str, Any]] = {}


def _refresh_srd_subclass_traits_cache() -> None:
    global SRD_SUBCLASS_TRAITS, SRD_SUBCLASS_TRAITS_BY_KEY
    SRD_SUBCLASS_TRAITS = build_srd_subclass_traits()
    SRD_SUBCLASS_TRAITS_BY_KEY = {row["key"]: row for row in SRD_SUBCLASS_TRAITS}


_refresh_srd_subclass_traits_cache()
