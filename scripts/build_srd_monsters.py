"""Build SRD 5.1 monster catalog from CC-SRD JSON (CC-BY-4.0).

Source: Tabyltop/CC-SRD Monsters-SRD5.1-CCBY4.0License-TT.json
Re-run after updating scripts/_srd_monsters_source.json.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts" / "_srd_monsters_source.json"
SOURCE_URL = (
    "https://raw.githubusercontent.com/Tabyltop/CC-SRD/main/"
    "Monsters-SRD5.1-CCBY4.0License-TT.json"
)
OUT_MANIFEST = ROOT / "app" / "services" / "combat" / "srd_monster_manifest.py"
OUT_DATA = ROOT / "app" / "services" / "combat" / "data" / "srd_monsters_5_1.json"

_LORE_DENY = re.compile(
    r"\b("
    r"beholder|mind flayer|illithid|displacer beast|githyanki|githzerai|"
    r"slaad|umber hulk|yuan-ti|vecna|tarrasque"
    r")\b",
    re.I,
)
_SKIP_ATTACK_NAMES = (
    "multiattack",
    "frightful presence",
    "breath",
    "enslave",
    "detect",
    "tail swipe",
    "tail attack",
    "psychic drain",
)


def monster_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def parse_ac(raw: str) -> int:
    match = re.search(r"\d+", str(raw or ""))
    return int(match.group()) if match else 10


def parse_hp(raw: str) -> int:
    match = re.match(r"(\d+)", str(raw or "").strip())
    return int(match.group(1)) if match else 1


def parse_speed_ft(raw: str) -> int:
    text = str(raw or "")
    match = re.search(r"(?:^|[,\s])(\d+)\s*ft\.(?!\s*/)", text)
    if match:
        return int(match.group(1))
    match = re.search(r"(\d+)\s*ft", text)
    return int(match.group(1)) if match else 30


def parse_cr(raw: str) -> float:
    match = re.match(r"([\d/]+)", str(raw or "").strip())
    if not match:
        return 0.0
    token = match.group(1)
    if "/" in token:
        num, den = token.split("/", 1)
        return round(float(num) / float(den), 3)
    return float(token)


def parse_attack_mod(raw: str) -> int:
    match = re.search(r"[+-]?\d+", str(raw or ""))
    return int(match.group()) if match else 0


def parse_range_ft(action: dict) -> tuple[int, str]:
    reach = str(action.get("reach") or "")
    rng = str(action.get("range") or "")
    if rng:
        match = re.search(r"(\d+)", rng)
        kind = "ranged"
    else:
        match = re.search(r"(\d+)", reach)
        kind = "melee"
    feet = int(match.group(1)) if match else 5
    return feet, kind


def normalize_damage(dice: str) -> str:
    text = str(dice or "").strip().replace(" ", "")
    if not text:
        return "1d6"
    return text


def should_skip_attack(name: str) -> bool:
    lowered = name.lower().strip(". ")
    if lowered.startswith("multiattack"):
        return True
    return any(token in lowered for token in _SKIP_ATTACK_NAMES)


def convert_attacks(actions: list) -> list[dict]:
    attacks: list[dict] = []
    for index, action in enumerate(actions or []):
        if not isinstance(action, dict):
            continue
        name = str(action.get("name") or f"Attack {index + 1}").strip()
        if should_skip_attack(name):
            continue
        if not action.get("to_hit") or not action.get("damage_dice"):
            continue
        range_ft, kind = parse_range_ft(action)
        key = monster_slug(name) or f"attack_{index}"
        attacks.append(
            {
                "key": key[:30],
                "name": name[:60],
                "kind": kind,
                "attack_mod": parse_attack_mod(action.get("to_hit")),
                "damage": normalize_damage(action.get("damage_dice")),
                "damage_type": str(action.get("damage_type") or "bludgeoning")[:20],
                "range_ft": range_ft,
            }
        )
        if len(attacks) >= 10:
            break
    return attacks


def convert_legendary(actions: list) -> list[dict]:
    legendary: list[dict] = []
    for index, action in enumerate(actions or []):
        if not isinstance(action, dict):
            continue
        name = str(action.get("name") or "").strip()
        cost_match = re.search(r"costs\s+(\d+)\s+actions?", name, re.I)
        if not cost_match:
            continue
        cost = int(cost_match.group(1))
        damage = normalize_damage(action.get("damage_dice") or "")
        entry = {
            "key": monster_slug(name)[:30] or f"legendary_{index}",
            "name": name[:60],
            "cost": cost,
            "description": str(action.get("description") or "")[:500],
            "damage_type": str(action.get("damage_type") or "")[:20],
        }
        if action.get("to_hit"):
            entry["attack_mod"] = parse_attack_mod(action.get("to_hit"))
        if damage and damage != "1d6":
            entry["damage"] = damage
        if action.get("reach") or action.get("range"):
            feet, _ = parse_range_ft(action)
            entry["range_ft"] = feet
        legendary.append(entry)
        if len(legendary) >= 10:
            break
    return legendary


def convert_traits(raw_abilities: list) -> list[dict]:
    traits: list[dict] = []
    for ability in raw_abilities or []:
        if not isinstance(ability, dict):
            continue
        traits.append(
            {
                "name": str(ability.get("name") or "Trait")[:80],
                "description": str(ability.get("description") or "")[:500],
            }
        )
    return traits


def parse_ability_score(raw) -> int:
    text = str(raw or "10").strip()
    match = re.match(r"(\d+)", text)
    return int(match.group(1)) if match else 10


def convert_monster(raw: dict) -> dict:
    name = str(raw.get("name") or "").strip()
    if not name or _LORE_DENY.search(name):
        raise ValueError(f"Excluded monster name: {name!r}")
    key = monster_slug(name)
    stats_block = raw.get("stats") or {}
    abilities = {
        ab: parse_ability_score(stats_block.get(ab))
        for ab in ("str", "dex", "con", "int", "wis", "cha")
    }
    attacks = convert_attacks(raw.get("actions") or [])
    if not attacks:
        attacks = [
            {
                "key": "strike",
                "name": "Strike",
                "kind": "melee",
                "attack_mod": 0,
                "damage": "1d6",
                "damage_type": "bludgeoning",
                "range_ft": 5,
            }
        ]
    stat_json = {
        "hp_max": parse_hp(raw.get("hit_points")),
        "ac": parse_ac(raw.get("armor_class")),
        "speed_ft": parse_speed_ft(raw.get("speed")),
        "abilities": abilities,
        "attacks": attacks,
        "legendary_actions": convert_legendary(raw.get("actions") or []),
        "traits": convert_traits(raw.get("abilities") or []),
        "size": str(raw.get("size") or "")[:20],
        "creature_type": str(raw.get("type") or "")[:30],
        "alignment": str(raw.get("alignment") or "")[:40],
        "senses": str(raw.get("senses") or "")[:200],
        "skills": str(raw.get("skills") or "")[:200],
        "saving_throws": str(raw.get("saving_throws") or "")[:200],
        "damage_immunities": str(raw.get("damage_immunities") or "")[:120],
        "damage_resistances": str(raw.get("damage_resistances") or "")[:120],
        "damage_vulnerabilities": str(raw.get("damage_vulnerabilities") or "")[:120],
        "condition_immunities": str(raw.get("condition_immunities") or "")[:120],
        "srd_reference": "SRD 5.1",
        "origin_srd_key": key,
        "gm_edited": False,
    }
    return {
        "key": key,
        "origin_srd_key": key,
        "name": name,
        "challenge_rating": parse_cr(raw.get("challenge")),
        "stat_json": stat_json,
        "content_source": "srd_5_1",
    }


def main() -> None:
    if not SOURCE.is_file():
        import urllib.request

        print(f"Downloading {SOURCE_URL} ...")
        SOURCE.write_bytes(urllib.request.urlopen(SOURCE_URL, timeout=120).read())
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    monsters_raw = payload.get("monsters") or []
    converted: list[dict] = []
    by_cr: dict[str, list[str]] = {}
    skipped = 0
    for raw in monsters_raw:
        try:
            entry = convert_monster(raw)
        except ValueError:
            skipped += 1
            continue
        converted.append(entry)
        cr_label = str(entry["challenge_rating"]).rstrip("0").rstrip(".")
        by_cr.setdefault(cr_label, []).append(entry["name"])
    converted.sort(key=lambda row: (row["name"].lower(), row["key"]))
    for names in by_cr.values():
        names.sort(key=str.lower)

    OUT_DATA.parent.mkdir(parents=True, exist_ok=True)
    OUT_DATA.write_text(
        json.dumps(
            {
                "license": "CC-BY-4.0",
                "attribution": (
                    "Mechanical shells derived from SRD 5.1 (Wizards of the Coast LLC), "
                    "CC-BY-4.0. Conversion source: Tabyltop/CC-SRD."
                ),
                "monsters": converted,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    manifest_lines = [
        '"""SRD 5.1 CC-BY-4.0 monster name manifest for seed audit.',
        "",
        "Reconcile against official SRD 5.1 Creative Commons source.",
        '"""',
        "",
        "SRD_MONSTERS_BY_CR = {",
    ]
    for cr in sorted(by_cr.keys(), key=lambda val: float(val)):
        manifest_lines.append(f"    {cr!r}: [")
        for name in by_cr[cr]:
            manifest_lines.append(f"        {name!r},")
        manifest_lines.append("    ],")
    manifest_lines.extend(
        [
            "}",
            "",
            f"SRD_MONSTER_COUNT = {len(converted)}",
            "",
        ]
    )
    OUT_MANIFEST.write_text("\n".join(manifest_lines), encoding="utf-8")
    print(f"Wrote {OUT_DATA} ({len(converted)} monsters, skipped {skipped})")
    print(f"Wrote {OUT_MANIFEST}")


if __name__ == "__main__":
    main()
