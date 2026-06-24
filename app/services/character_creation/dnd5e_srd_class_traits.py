"""SRD class feature traits for the compendium and level progression trait_keys.

Mechanical labels and sparse combat effects only — no copied book prose.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

CURRENT_SRD_CLASS_TRAITS_SEED_VERSION = 3

_SHARED_TRAIT_KEYS: dict[str, str] = {
    "Extra Attack": "cf-extra-attack",
    "Extra Attack (2)": "cf-extra-attack-2",
    "Extra Attack (3)": "cf-extra-attack-3",
    "Fighting Style": "cf-fighting-style",
    "Spellcasting": "cf-spellcasting",
    "Channel Divinity": "cf-channel-divinity",
    "Expertise": "cf-expertise",
    "Evasion": "cf-evasion",
}

# Extra tags beyond class_key and class-feature.
_TRAIT_TAGS: dict[str, list[str]] = {
    "cf-barbarian-rage": ["rage"],
}

# Sparse mechanical effects keyed by trait key (combat profile / AC rules).
_TRAIT_EFFECTS: dict[str, dict[str, Any]] = {
    "cf-barbarian-unarmored-defense": {
        "unarmored_defense": True,
        "unarmored_ac_add_ability": "con",
        "unarmored_defense_allows_shield": True,
    },
    "cf-barbarian-fast-movement": {"speed_bonus_ft": 10},
    "cf-barbarian-relentless-rage": {"relentless_rage": True},
    "cf-monk-unarmored-defense": {
        "unarmored_defense": True,
        "unarmored_ac_add_ability": "wis",
        "unarmored_defense_allows_shield": False,
    },
    "cf-monk-unarmored-movement": {"speed_bonus_ft": 10},
    "cf-extra-attack": {"extra_attacks_per_action": 2},
    "cf-extra-attack-2": {"extra_attacks_per_action": 3},
    "cf-extra-attack-3": {"extra_attacks_per_action": 4},
    "cf-fighter-action-surge": {
        "action_surge": True,
        "action_surge_additional_actions": 1,
    },
}

_TRAIT_SUMMARIES: dict[str, str] = {
    "cf-barbarian-rage": "Bonus action rage; resistance to B/P/S while raging.",
    "cf-barbarian-unarmored-defense": "AC 10 + DEX + CON when not wearing armor (shield OK).",
    "cf-barbarian-reckless-attack": "Advantage on melee attacks; attacks against you have advantage.",
    "cf-barbarian-danger-sense": "Advantage on DEX saves against effects you can see.",
    "cf-barbarian-fast-movement": "+10 ft speed while not wearing heavy armor.",
    "cf-barbarian-relentless-rage": "DC 10 CON save to stay at 1 HP when dropped to 0 while raging.",
    "cf-monk-unarmored-defense": "AC 10 + DEX + WIS when unarmored (no shield).",
    "cf-monk-martial-arts": "Unarmed strikes and monk weapons use Martial Arts die.",
    "cf-monk-ki": "Spend ki points for Flurry, Patient Defense, Step of the Wind.",
    "cf-extra-attack": "Attack twice when you take the Attack action.",
    "cf-extra-attack-2": "Attack three times when you take the Attack action.",
    "cf-extra-attack-3": "Attack four times when you take the Attack action.",
    "cf-fighting-style": "Choose a fighting style (player pick).",
    "cf-spellcasting": "Cast spells using class spellcasting rules.",
    "cf-fighter-second-wind": "Bonus action regain 1d10 + level HP (short rest recharge).",
    "cf-fighter-action-surge": "Take one additional action on your turn (short rest recharge).",
    "cf-rogue-sneak-attack": "Extra damage once per turn when conditions are met.",
    "cf-warlock-otherworldly-patron": "Choose a patron that grants expanded spell list options and features.",
    "cf-warlock-pact-magic": "Cast warlock spells using pact slots that recharge on a short rest.",
    "cf-warlock-eldritch-invocations": "Choose invocations that customize your pact magic.",
    "cf-warlock-pact-boon": "Choose a boon: blade, chain, or tome.",
    "cf-warlock-eldritch-master": "Recover all pact slots once per long rest.",
}

_TRAIT_CATEGORIES: dict[str, str] = {
    "cf-barbarian-rage": "resource",
    "cf-barbarian-unarmored-defense": "defense",
    "cf-monk-unarmored-defense": "defense",
    "cf-extra-attack": "attack",
    "cf-extra-attack-2": "attack",
    "cf-extra-attack-3": "attack",
    "cf-fighting-style": "other",
    "cf-spellcasting": "other",
    "cf-rogue-sneak-attack": "attack",
    "cf-fighter-second-wind": "resource",
    "cf-fighter-action-surge": "resource",
}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(name or "").strip().lower()).strip("-")[:60]


def trait_key_for_feature(class_key: str, feature_name: str) -> str:
    """Stable trait key for an SRD class feature label."""
    name = str(feature_name or "").strip()
    if not name:
        return ""
    shared = _SHARED_TRAIT_KEYS.get(name)
    if shared:
        return shared
    return f"cf-{class_key}-{_slug(name)}"


def _class_feature_names() -> dict[str, set[str]]:
    from app.services.character_creation.dnd5e_srd_class_progression import (
        SRD_CLASS_PROGRESSIONS,
    )

    out: dict[str, set[str]] = {}
    for class_key, bundle in SRD_CLASS_PROGRESSIONS.items():
        names: set[str] = set()
        for row in bundle.get("level_progression") or []:
            for feat in row.get("features") or []:
                if isinstance(feat, dict):
                    label = str(feat.get("name") or "").strip()
                else:
                    label = str(feat or "").strip()
                if label and not _is_asi_label(label):
                    names.add(label)
        out[class_key] = names
    return out


def _is_asi_label(name: str) -> bool:
    lowered = name.lower()
    return "ability score" in lowered and ("improvement" in lowered or "increase" in lowered)


def _build_trait(class_key: str, feature_name: str) -> dict[str, Any]:
    key = trait_key_for_feature(class_key, feature_name)
    effects = deepcopy(_TRAIT_EFFECTS.get(key) or {})
    tags = [class_key, "class-feature", *(_TRAIT_TAGS.get(key) or [])]
    category = _TRAIT_CATEGORIES.get(key, "other")
    return {
        "key": key,
        "name": feature_name,
        "source": "base",
        "origin_template_key": key,
        "category": category,
        "effects": effects,
        "prerequisites": {"class_keys": [class_key]},
        "tags": sorted(set(tags)),
        "stacking": "max",
        "notes": "",
        "summary": _TRAIT_SUMMARIES.get(key, f"{feature_name} (class feature).")[:500],
        "rules_text": "",
        "srd_reference": "",
        "content_source": "srd-5.1",
        "gm_edited": False,
        "srd_seed_version": CURRENT_SRD_CLASS_TRAITS_SEED_VERSION,
    }


def build_srd_class_traits() -> tuple[dict[str, Any], ...]:
    """All unique SRD class feature traits across the twelve base classes."""
    by_key: dict[str, dict[str, Any]] = {}
    for class_key, names in _class_feature_names().items():
        for name in sorted(names):
            trait = _build_trait(class_key, name)
            existing = by_key.get(trait["key"])
            if existing is None:
                by_key[trait["key"]] = trait
                continue
            # Shared trait — widen class prerequisites.
            prereqs = dict(existing.get("prerequisites") or {})
            class_keys = set(prereqs.get("class_keys") or [])
            class_keys.add(class_key)
            prereqs["class_keys"] = sorted(class_keys)
            existing["prerequisites"] = prereqs
            tags = set(existing.get("tags") or [])
            tags.add(class_key)
            existing["tags"] = sorted(tags)
    return tuple(by_key[k] for k in sorted(by_key.keys()))


SRD_CLASS_TRAITS: tuple[dict[str, Any], ...] = ()
SRD_CLASS_TRAITS_BY_KEY: dict[str, dict[str, Any]] = {}


def _refresh_srd_class_traits_cache() -> None:
    global SRD_CLASS_TRAITS, SRD_CLASS_TRAITS_BY_KEY
    SRD_CLASS_TRAITS = build_srd_class_traits()
    SRD_CLASS_TRAITS_BY_KEY = {row["key"]: row for row in SRD_CLASS_TRAITS}


def trait_keys_for_features(class_key: str, feature_names: list[str]) -> list[str]:
    """Map feature labels on a progression row to compendium trait keys."""
    keys: list[str] = []
    seen: set[str] = set()
    for raw in feature_names:
        label = str(raw or "").strip()
        if not label or _is_asi_label(label):
            continue
        key = trait_key_for_feature(class_key, label)
        if key and key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def enrich_progression_trait_keys(class_key: str, level_progression: list[dict[str, Any]]) -> None:
    """Fill trait_keys on each row from feature names (in-place)."""
    for row in level_progression:
        if not isinstance(row, dict):
            continue
        names = [
            str(f.get("name") or "").strip()
            for f in (row.get("features") or [])
            if isinstance(f, dict) and str(f.get("name") or "").strip()
        ]
        row["trait_keys"] = trait_keys_for_features(class_key, names)
