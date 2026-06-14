"""Generate dnd5e_spells.py with CORE_SPELLS built from manifest + overrides."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "app/services/character_creation/dnd5e_spells.py"

# Combat-ready overrides keyed by slug. Values merge onto default shells.
COMBAT_OVERRIDES: dict[str, dict] = {
    "acid_splash": {
        "school": "conjuration",
        "casting_time": "1 action",
        "range_text": "60 feet",
        "range_ft": 60,
        "components": "V, S",
        "duration": "Instantaneous",
        "attack_type": "save",
        "save_ability": "dex",
        "damage": "1d6",
        "damage_type": "acid",
        "automation": "auto",
        "summary": "Hurl acid at one or two creatures within range; Dex save for half.",
    },
    "chill_touch": {
        "school": "necromancy",
        "range_text": "120 feet",
        "range_ft": 120,
        "attack_type": "spell_attack",
        "damage": "1d8",
        "damage_type": "necrotic",
        "automation": "auto",
        "summary": "Ranged spell attack deals necrotic damage and hampers healing until your next turn.",
    },
    "eldritch_blast": {
        "school": "evocation",
        "range_text": "120 feet",
        "range_ft": 120,
        "attack_type": "spell_attack",
        "damage": "1d10",
        "damage_type": "force",
        "automation": "auto",
        "summary": "Ranged spell attack for force damage.",
    },
    "fire_bolt": {
        "school": "evocation",
        "range_text": "120 feet",
        "range_ft": 120,
        "attack_type": "spell_attack",
        "damage": "1d10",
        "damage_type": "fire",
        "automation": "auto",
        "summary": "Ranged spell attack for fire damage.",
    },
    "poison_spray": {
        "school": "conjuration",
        "range_text": "10 feet",
        "range_ft": 10,
        "attack_type": "save",
        "save_ability": "con",
        "damage": "1d12",
        "damage_type": "poison",
        "automation": "auto",
        "summary": "Con save or poison damage at close range.",
    },
    "produce_flame": {
        "school": "conjuration",
        "range_text": "Self",
        "range_ft": 0,
        "attack_type": "spell_attack",
        "damage": "1d8",
        "damage_type": "fire",
        "automation": "auto",
        "summary": "Flame in your hand; ranged spell attack for fire damage.",
    },
    "ray_of_frost": {
        "school": "evocation",
        "range_text": "60 feet",
        "range_ft": 60,
        "attack_type": "spell_attack",
        "damage": "1d8",
        "damage_type": "cold",
        "automation": "auto",
        "summary": "Ranged spell attack for cold damage.",
    },
    "sacred_flame": {
        "school": "evocation",
        "range_text": "60 feet",
        "range_ft": 60,
        "attack_type": "save",
        "save_ability": "dex",
        "damage": "1d8",
        "damage_type": "radiant",
        "automation": "auto",
        "summary": "Dex save or radiant damage; ignores cover.",
    },
    "shocking_grasp": {
        "school": "evocation",
        "range_text": "Touch",
        "range_ft": 5,
        "attack_type": "spell_attack",
        "damage": "1d8",
        "damage_type": "lightning",
        "automation": "auto",
        "summary": "Melee spell attack for lightning damage with advantage on metal armor.",
    },
    "burning_hands": {
        "level": 1,
        "school": "evocation",
        "range_text": "Self (15-foot cone)",
        "range_ft": 15,
        "attack_type": "save",
        "save_ability": "dex",
        "damage": "3d6",
        "damage_type": "fire",
        "area": {"shape": "cone", "size_ft": 15},
        "automation": "auto",
        "summary": "15-foot cone; Dex save for half fire damage.",
    },
    "magic_missile": {
        "level": 1,
        "school": "evocation",
        "range_text": "120 feet",
        "range_ft": 120,
        "damage": "3d4+3",
        "damage_type": "force",
        "automation": "auto",
        "summary": "Three darts of force damage automatically hit.",
    },
    "cure_wounds": {
        "level": 1,
        "school": "evocation",
        "range_text": "Touch",
        "range_ft": 5,
        "healing": "1d8",
        "automation": "auto",
        "summary": "Touch to restore hit points.",
        "upcast": {"healing_per_slot": "1d8"},
    },
    "healing_word": {
        "level": 1,
        "school": "evocation",
        "casting_time": "1 bonus action",
        "range_text": "60 feet",
        "range_ft": 60,
        "healing": "1d4",
        "automation": "auto",
        "summary": "Bonus action healing at range.",
        "upcast": {"healing_per_slot": "1d4"},
    },
    "guiding_bolt": {
        "level": 1,
        "school": "evocation",
        "range_text": "120 feet",
        "range_ft": 120,
        "attack_type": "spell_attack",
        "damage": "4d6",
        "damage_type": "radiant",
        "automation": "auto",
        "summary": "Ranged spell attack for radiant damage; next attack has advantage.",
    },
    "inflict_wounds": {
        "level": 1,
        "school": "necromancy",
        "range_text": "Touch",
        "range_ft": 5,
        "attack_type": "spell_attack",
        "damage": "3d10",
        "damage_type": "necrotic",
        "automation": "auto",
        "summary": "Melee spell attack for necrotic damage.",
    },
    "thunderwave": {
        "level": 1,
        "school": "evocation",
        "range_text": "Self (15-foot cube)",
        "range_ft": 15,
        "attack_type": "save",
        "save_ability": "con",
        "damage": "2d8",
        "damage_type": "thunder",
        "area": {"shape": "cube", "size_ft": 15},
        "automation": "auto",
        "summary": "Cube around you; Con save for half thunder damage and push.",
    },
    "shield": {
        "level": 1,
        "school": "abjuration",
        "casting_time": "1 reaction",
        "range_text": "Self",
        "range_ft": 0,
        "automation": "manual",
        "summary": "Reaction +5 AC until start of your next turn.",
    },
    "misty_step": {
        "level": 2,
        "school": "conjuration",
        "casting_time": "1 bonus action",
        "range_text": "Self",
        "range_ft": 0,
        "automation": "manual",
        "summary": "Bonus action teleport up to 30 feet.",
    },
    "scorching_ray": {
        "level": 2,
        "school": "evocation",
        "range_text": "120 feet",
        "range_ft": 120,
        "attack_type": "spell_attack",
        "damage": "2d6",
        "damage_type": "fire",
        "automation": "auto",
        "summary": "Three ranged spell attacks for fire damage.",
    },
    "hold_person": {
        "level": 2,
        "school": "enchantment",
        "range_text": "60 feet",
        "range_ft": 60,
        "concentration": True,
        "duration": "Concentration, up to 1 minute",
        "attack_type": "save",
        "save_ability": "wis",
        "conditions": ["paralyzed"],
        "automation": "manual",
        "summary": "Wis save or paralyzed; concentration.",
    },
    "fireball": {
        "level": 3,
        "school": "evocation",
        "range_text": "150 feet",
        "range_ft": 150,
        "attack_type": "save",
        "save_ability": "dex",
        "damage": "8d6",
        "damage_type": "fire",
        "area": {"shape": "sphere", "size_ft": 20},
        "automation": "auto",
        "summary": "20-foot radius sphere; Dex save for half fire damage.",
        "upcast": {"damage_per_slot": "1d6"},
    },
    "lightning_bolt": {
        "level": 3,
        "school": "evocation",
        "range_text": "Self (100-foot line)",
        "range_ft": 100,
        "attack_type": "save",
        "save_ability": "dex",
        "damage": "8d6",
        "damage_type": "lightning",
        "area": {"shape": "line", "size_ft": 100},
        "automation": "auto",
        "summary": "100-foot line; Dex save for half lightning damage.",
        "upcast": {"damage_per_slot": "1d6"},
    },
    "counterspell": {
        "level": 3,
        "school": "abjuration",
        "casting_time": "1 reaction",
        "range_text": "60 feet",
        "range_ft": 60,
        "automation": "manual",
        "summary": "Reaction to interrupt a creature casting a spell.",
    },
    "floating_disk": {
        "level": 1,
        "school": "conjuration",
        "ritual": True,
        "range_text": "30 feet",
        "range_ft": 30,
        "duration": "1 hour",
        "automation": "manual",
        "summary": "Create a floating horizontal disk that carries up to 500 pounds.",
    },
    "hideous_laughter": {
        "level": 1,
        "school": "enchantment",
        "range_text": "30 feet",
        "range_ft": 30,
        "concentration": True,
        "duration": "Concentration, up to 1 minute",
        "attack_type": "save",
        "save_ability": "wis",
        "conditions": ["incapacitated"],
        "automation": "manual",
        "summary": "Wis save or fall prone incapacitated with laughter.",
    },
    "acid_arrow": {
        "level": 2,
        "school": "evocation",
        "range_text": "90 feet",
        "range_ft": 90,
        "attack_type": "spell_attack",
        "damage": "4d4",
        "damage_type": "acid",
        "automation": "auto",
        "summary": "Ranged spell attack; acid damage on hit and end of next turn.",
    },
    "blindness_deafness": {
        "level": 2,
        "school": "necromancy",
        "range_text": "30 feet",
        "range_ft": 30,
        "attack_type": "save",
        "save_ability": "con",
        "conditions": ["blinded", "deafened"],
        "automation": "manual",
        "summary": "Con save or blinded and deafened.",
    },
}

SCHOOL_HINTS = [
    (re.compile(r"\b(cure|heal|restoration|revivify|resurrection|regenerate)\b", re.I), "evocation"),
    (re.compile(r"\b(detect|identify|scry|augury|divine|commune|legend lore)\b", re.I), "divination"),
    (re.compile(r"\b(illusion|mirror|phantasm|invisibility|disguise|silent image)\b", re.I), "illusion"),
    (re.compile(r"\b(enchant|charm|hold|command|dominate|sleep|confusion)\b", re.I), "enchantment"),
    (re.compile(r"\b(conjure|summon|teleport|misty|dimension door|gate)\b", re.I), "conjuration"),
    (re.compile(r"\b(shield|ward|protection|counterspell|dispel|antimagic)\b", re.I), "abjuration"),
    (re.compile(r"\b(animate dead|blight|contagion|harm|inflict|vampiric)\b", re.I), "necromancy"),
    (re.compile(r"\b(transmute|polymorph|stone shape|alter self)\b", re.I), "transmutation"),
]

LORE_DENY = re.compile(
    r"\b(bigby|melf|mordenkainen|nystul|otiluke|leomund|drawmij|otto|tasha|tenser|evard)\b",
    re.I,
)

MODULE_HEADER = '''\
"""D&D 5e SRD 5.1 spell seed catalog (CC-BY-4.0 mechanical shells).

This module provides campaign compendium defaults only. Spell text is
mechanical metadata for display and MVP combat automation — not book prose.

Attribution: System Reference Document 5.1, Wizards of the Coast LLC,
available under Creative Commons Attribution 4.0 International (CC-BY-4.0).
Product Identity names are excluded; SRD-safe display names are used instead.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from app.services.character_creation.srd_spell_manifest import SRD_SPELLS_BY_LEVEL
from app.services.character_creation.dnd5e_spell_classes import SPELL_CLASSES_BY_KEY

_LORE_DENY = re.compile(
    r"\\b("
    r"bigby|melf|mordenkainen|nystul|otiluke|leomund|drawmij|otto|tasha|tenser|evard"
    r")\\b",
    re.I,
)

_SCHOOL_HINTS: list[tuple[re.Pattern[str], str]] = [
'''

MODULE_MIDDLE = '''
]

_COMBAT_OVERRIDES: dict[str, dict[str, Any]] = '''


def _infer_school(name: str) -> str:
    for pattern, school in SCHOOL_HINTS:
        if pattern.search(name):
            return school
    return "evocation"


def main() -> None:
    hints_src = ",\n".join(
        f'    (re.compile({pattern.pattern!r}, re.I), {school!r})'
        for pattern, school in SCHOOL_HINTS
    )
    overrides_json = json.dumps(COMBAT_OVERRIDES, indent=4)
    overrides_json = (
        overrides_json.replace(": true", ": True")
        .replace(": false", ": False")
        .replace(": null", ": None")
    )

    body = f"""{MODULE_HEADER}{hints_src}
{MODULE_MIDDLE}{overrides_json}


def spell_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", str(name or "").strip().lower()).strip("_")
    return slug[:80] or "spell"


def _infer_school(name: str) -> str:
    for pattern, school in _SCHOOL_HINTS:
        if pattern.search(name):
            return school
    return "evocation"


def _default_shell(name: str, level: int) -> dict[str, Any]:
    school = _infer_school(name)
    concentration = bool(re.search(r"\\b(hold|cloud|wall|sphere|field|guardian|moonbeam|spiritual weapon|invisibility)\\b", name, re.I))
    ritual = bool(re.search(r"\\b(find familiar|identify|alarm|detect|floating disk|private sanctum)\\b", name, re.I))
    range_ft = 60 if level == 0 else (120 if level <= 2 else 150)
    return {{
        "key": spell_slug(name),
        "name": name,
        "level": int(level),
        "school": school,
        "casting_time": "1 action",
        "range_text": f"{{range_ft}} feet" if range_ft else "Self",
        "range_ft": range_ft,
        "components": "V, S",
        "material_component": "",
        "duration": "Concentration, up to 1 minute" if concentration else "Instantaneous",
        "concentration": concentration,
        "ritual": ritual,
        "classes": list(SPELL_CLASSES_BY_KEY.get(spell_slug(name), [])),
        "attack_type": None,
        "save_ability": None,
        "damage": None,
        "damage_type": None,
        "healing": None,
        "area": None,
        "conditions": [],
        "upcast": {{}},
        "automation": "manual",
        "summary": f"SRD {{level}}-level {{school}} spell.",
        "srd_reference": "SRD 5.1",
        "source": "base",
        "is_hidden": False,
        "secret": False,
        "visible_to_owner": True,
    }}


def _merge_override(shell: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(shell)
    merged.update(deepcopy(override))
    merged["key"] = shell["key"]
    merged["name"] = shell["name"]
    merged["level"] = shell["level"]
    if merged.get("automation") != "manual" and not (
        merged.get("attack_type")
        or merged.get("save_ability")
        or merged.get("damage")
        or merged.get("healing")
    ):
        merged["automation"] = "manual"
    return merged


def build_core_spell(name: str, level: int) -> dict[str, Any]:
    if _LORE_DENY.search(name):
        raise ValueError(f"Product Identity spell name: {{name!r}}")
    shell = _default_shell(name, level)
    override = _COMBAT_OVERRIDES.get(shell["key"], {{}})
    return _merge_override(shell, override)


CORE_SPELLS: list[dict[str, Any]] = [
    build_core_spell(name, level)
    for level, names in sorted(SRD_SPELLS_BY_LEVEL.items())
    for name in names
]


def combat_snapshot_fields(entry: dict[str, Any]) -> dict[str, Any]:
    \"\"\"Subset snapshotted onto BattleCombatant.action_data_json spells.\"\"\"
    keep = (
        "key", "name", "level", "classes", "automation", "range_ft", "range_text",
        "casting_time", "attack_type", "save_ability", "damage", "damage_type",
        "healing", "area", "conditions", "upcast", "concentration", "summary",
    )
    return {{k: deepcopy(entry[k]) for k in keep if k in entry}}
"""

    OUT.write_text(body, encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
