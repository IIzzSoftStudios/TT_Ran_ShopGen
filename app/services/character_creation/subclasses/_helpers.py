"""Shared helpers for SRD subclass seed entries."""

from __future__ import annotations

import re
from typing import Any

CURRENT_SRD_SUBCLASSES_SEED_VERSION = 1


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(name or "").strip().lower()).strip("-")[:60]


def trait_key_for_subclass_feature(subclass_key: str, feature_name: str) -> str:
    return f"scf-{slug(subclass_key)}-{slug(feature_name)}"


def subclass_entry(
    *,
    key: str,
    name: str,
    class_key: str,
    pick_level: int,
    tagline: str = "",
    summary: str = "",
    grants: list[tuple[int, str, str]],
) -> dict[str, Any]:
    """Build a subclass compendium seed entry.

    ``grants`` is a list of (level, feature_name, feature_summary) tuples.
    """
    feature_grants: list[dict[str, Any]] = []
    for level, feat_name, feat_summary in grants:
        feature_grants.append(
            {
                "level": level,
                "name": feat_name,
                "summary": feat_summary[:500],
                "trait_keys": [trait_key_for_subclass_feature(key, feat_name)],
            }
        )
    return {
        "key": key,
        "name": name,
        "source": "base",
        "tagline": tagline[:120],
        "summary": summary[:500],
        "class_key": class_key,
        "pick_level": pick_level,
        "feature_grants": feature_grants,
        "is_hidden": False,
        "secret": False,
        "visible_to_owner": True,
        "srd_seed_version": CURRENT_SRD_SUBCLASSES_SEED_VERSION,
        "gm_edited": False,
    }
