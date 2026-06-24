"""SRD 5.1 multiattack parsing and class Extra Attack resolution."""

from __future__ import annotations

import re
from typing import Any

_COUNT_WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
}


def _parse_count(token: str) -> int | None:
    cleaned = str(token or "").strip().lower()
    if not cleaned:
        return None
    if cleaned.isdigit():
        value = int(cleaned)
        return value if value > 0 else None
    return _COUNT_WORDS.get(cleaned)


def attack_token_map(attacks: list[dict[str, Any]]) -> dict[str, str]:
    """Map normalized weapon tokens to attack keys."""
    mapping: dict[str, str] = {}
    for attack in attacks or []:
        if not isinstance(attack, dict):
            continue
        key = str(attack.get("key") or "").strip()
        if not key:
            continue
        name = str(attack.get("name") or "").strip().lower().rstrip(".")
        slug = re.sub(r"[^a-z0-9]+", "_", name).strip("_")
        for token in (key, slug, slug.rstrip("s")):
            if token:
                mapping[token] = key
    return mapping


def _weapon_to_key(weapon: str, token_map: dict[str, str]) -> str | None:
    weapon = str(weapon or "").strip().lower().rstrip(".")
    if not weapon:
        return None
    norm = re.sub(r"[^a-z0-9]+", "_", weapon).strip("_")
    if norm in token_map:
        return token_map[norm]
    if norm.endswith("s") and norm[:-1] in token_map:
        return token_map[norm[:-1]]
    for token, key in token_map.items():
        if len(token) >= 4 and token in norm:
            return key
    return None


def _multiattack_phrase(description: str) -> str:
    """Keep the primary attack phrase; drop alternates and riders."""
    text = str(description or "")
    lower = text.lower()
    idx = lower.rfind(" makes ")
    if idx >= 0:
        text = text[idx + 1 :]
    for sep in (
        ". alternatively",
        ". it can",
        ". when ",
        ". if ",
        ". it can't",
        ". it cannot",
    ):
        pos = text.lower().find(sep)
        if pos > 0:
            text = text[:pos]
    if " or " in text.lower():
        text = text.split(" or ", 1)[0]
    return text.strip()


def parse_multiattack_attack_keys(
    description: str,
    token_map: dict[str, str],
    *,
    fallback_key: str,
) -> list[str]:
    """Parse SRD multiattack prose into ordered attack keys."""
    phrase = _multiattack_phrase(description)
    keys: list[str] = []

    clause_re = re.compile(
        r"(one|two|three|four|five|six|seven|eight|a|an|\d+)\s+"
        r"(?:with\s+(?:its?\s+)?|to\s+)([\w\s-]+?)"
        r"(?=\s*(?:,?\s*and\s+|\s*\.|$))",
        re.I,
    )
    for match in clause_re.finditer(phrase):
        count = _parse_count(match.group(1))
        weapon = match.group(2).strip()
        key = _weapon_to_key(weapon, token_map)
        if count and key:
            keys.extend([key] * count)

    if keys:
        return keys

    weapon_attack_re = re.compile(
        r"(one|two|three|four|five|six|seven|eight|a|an|\d+)\s+"
        r"([\w-]+)\s+attacks?",
        re.I,
    )
    for match in weapon_attack_re.finditer(phrase):
        count = _parse_count(match.group(1))
        weapon = match.group(2).strip()
        key = _weapon_to_key(weapon, token_map) or (
            fallback_key if weapon.lower() in {"melee", "ranged"} else None
        )
        if count and key:
            keys.extend([key] * count)

    if keys:
        return keys

    with_weapon_re = re.compile(
        r"makes\s+(one|two|three|four|five|six|seven|eight|a|an|\d+)\s+"
        r"attacks?\s+with\s+(?:its?\s+)?([\w-]+)",
        re.I,
    )
    match = with_weapon_re.search(phrase)
    if match:
        count = _parse_count(match.group(1))
        key = _weapon_to_key(match.group(2), token_map)
        if count and key:
            return [key] * count

    generic_re = re.compile(
        r"makes\s+(one|two|three|four|five|six|seven|eight|a|an|\d+)\s+"
        r"(?:melee|ranged)?\s*attacks?",
        re.I,
    )
    match = generic_re.search(phrase)
    if match:
        count = _parse_count(match.group(1))
        if count and count > 1:
            return [fallback_key] * count

    return []


def build_multiattack_entry(
    action: dict[str, Any],
    attacks: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Build one structured multiattack from an SRD action block."""
    name = str(action.get("name") or "").strip()
    if not name.lower().startswith("multiattack"):
        return None
    token_map = attack_token_map(attacks)
    fallback = str((attacks[0] or {}).get("key") or "strike") if attacks else "strike"
    attack_keys = parse_multiattack_attack_keys(
        str(action.get("description") or ""),
        token_map,
        fallback_key=fallback,
    )
    if not attack_keys:
        return None
    return {
        "key": "multiattack",
        "name": name.rstrip(".") or "Multiattack",
        "attack_keys": attack_keys[:12],
        "description": str(action.get("description") or "")[:500],
    }


def extra_attack_count(class_entry: dict[str, Any] | None, level: int) -> int:
    """Attacks per Attack action from Extra Attack feature names (default 1)."""
    if not class_entry:
        return 1
    try:
        level_int = max(1, min(20, int(level or 1)))
    except (TypeError, ValueError):
        level_int = 1
    count = 1
    for row in class_entry.get("level_progression") or []:
        if not isinstance(row, dict):
            continue
        try:
            row_level = int(row.get("level") or 0)
        except (TypeError, ValueError):
            continue
        if row_level > level_int:
            continue
        for key in row.get("trait_keys") or []:
            clean = str(key or "").strip().lower()
            if clean == "cf-extra-attack":
                count = max(count, 2)
            elif clean == "cf-extra-attack-2":
                count = max(count, 3)
            elif clean == "cf-extra-attack-3":
                count = max(count, 4)
        for feat in row.get("features") or []:
            if not isinstance(feat, dict):
                continue
            text = f"{feat.get('name', '')} {feat.get('description', '')}".lower()
            if "extra attack" not in text:
                continue
            if "four times" in text or "four attacks" in text or "extra attack (3)" in text:
                count = max(count, 4)
            elif "three times" in text or "three attacks" in text or "extra attack (2)" in text:
                count = max(count, 3)
            elif (
                "twice" in text
                or "two attacks" in text
                or "attack twice" in text
                or "attacks twice" in text
                or "extra attack" in text
            ):
                count = max(count, 2)
    return count


def extra_attack_count_from_profile(combat_profile: dict[str, Any] | None) -> int | None:
    """Attacks per Attack action from merged trait combat profile."""
    if not isinstance(combat_profile, dict):
        return None
    try:
        count = int(combat_profile.get("extra_attacks_per_action") or 0)
    except (TypeError, ValueError):
        return None
    return count if count >= 2 else None


def resolve_extra_attack_count(
    class_entry: dict[str, Any] | None,
    level: int,
    *,
    combat_profile: dict[str, Any] | None = None,
) -> int:
    """Best attacks-per-action from trait profile and class progression."""
    from_profile = extra_attack_count_from_profile(combat_profile)
    from_class = extra_attack_count(class_entry, level)
    if from_profile is not None:
        return max(from_profile, from_class)
    return from_class


def player_attack_multiattack(extra_attacks: int) -> list[dict[str, Any]]:
    """Virtual Attack action for class Extra Attack."""
    if extra_attacks <= 1:
        return []
    return [
        {
            "key": "attack",
            "name": "Attack",
            "uses_primary_attack": True,
            "swing_count": extra_attacks,
            "description": (
                f"When you take the Attack action, you can attack {extra_attacks} times."
            ),
        }
    ]
