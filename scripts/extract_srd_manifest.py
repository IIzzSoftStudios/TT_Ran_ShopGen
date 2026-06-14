"""One-off: extract SRD spell manifest from agent transcript."""
import json
import re
from pathlib import Path

TRANSCRIPT = Path(
    r"C:\Users\Owner\.cursor\projects\c-Users-Owner-Desktop-Code-Code-TT-Shop-Gen"
    r"\agent-transcripts\019cf4bf-d0fd-4c9c-bf2d-fb11ed51080a"
    r"\019cf4bf-d0fd-4c9c-bf2d-fb11ed51080a.jsonl"
)
OUT = Path(__file__).resolve().parents[1] / "app/services/character_creation/srd_spell_manifest.py"

# Strip Product Identity / lore names to SRD-safe display names.
_RENAME = {
    "Bigby's Hand": "Arcane Hand",
    "Melf's Acid Arrow": "Acid Arrow",
    "Tenser's Floating Disk": "Floating Disk",
    "Otto's Irresistible Dance": "Irresistible Dance",
    "Drawmij's Instant Summons": "Instant Summons",
    "Leomund's Secret Chest": "Secret Chest",
    "Leomund's Tiny Hut": "Private Sanctum",
    "Mordenkainen's Faithful Hound": "Faithful Hound",
    "Mordenkainen's Magnificent Mansion": "Magnificent Mansion",
    "Mordenkainen's Private Sanctum": "Private Sanctum",
    "Mordenkainen's Sword": "Arcane Sword",
    "Nystul's Magic Aura": "Arcanist's Magic Aura",
    "Otiluke's Freezing Sphere": "Freezing Sphere",
    "Otiluke's Resilient Sphere": "Resilient Sphere",
    "Tasha's Hideous Laughter": "Hideous Laughter",
    "Evard's Black Tentacles": "Black Tentacles",
}

_LORE_DENY = re.compile(
    r"\b("
    r"bigby|melf|mordenkainen|nystul|otiluke|leomund|drawmij|otto|tasha|tenser|evard"
    r")\b",
    re.I,
)


def _clean_name(raw: str) -> str:
    name = re.split(r"\s*\*\(", raw)[0].strip()
    name = _RENAME.get(name, name)
    if _LORE_DENY.search(name):
        raise ValueError(f"Product Identity name remains after rename: {name!r}")
    return name


def _level_from_header(line: str) -> int | None:
    if re.match(r"^## Cantrips \(Level 0\)", line):
        return 0
    m = re.match(r"^## (\d+)(?:st|nd|rd|th) Level", line)
    if m:
        return int(m.group(1))
    return None


text = ""
with TRANSCRIPT.open(encoding="utf-8") as fh:
    for line in fh:
        if "Cantrips (Level 0)" in line:
            obj = json.loads(line)
            text = obj["message"]["content"][0]["text"]
            break

sections: dict[int, list[str]] = {}
current: int | None = None
for line in text.split("\n"):
    level = _level_from_header(line)
    if level is not None:
        current = level
        sections.setdefault(current, [])
        continue
    if line.strip().startswith("* ") and current is not None:
        sections[current].append(_clean_name(line.strip()[2:].strip()))

# Official SRD 5.1 CC spells missing from pasted checklist (312 extracted).
_MISSING: dict[int, list[str]] = {
    0: ["Create Bonfire", "Frostbite", "Toll the Dead", "Word of Radiance"],
    1: ["Arms of Hadar", "Disguise Self", "Ensnaring Strike"],
}
for level, names in _MISSING.items():
    bucket = sections.setdefault(level, [])
    for name in names:
        if name not in bucket:
            bucket.append(name)

for level, names in sections.items():
    sections[level] = sorted(set(names), key=str.lower)

lines = [
    '"""SRD 5.1 CC-BY-4.0 spell name manifest for seed audit.',
    "",
    "Reconcile against official SRD 5.1 Creative Commons source.",
    '"""',
    "",
    "SRD_SPELLS_BY_LEVEL = {",
]
for lvl in sorted(sections.keys()):
    lines.append(f"    {lvl}: [")
    for name in sections[lvl]:
        lines.append(f"        {name!r},")
    lines.append("    ],")
lines.extend(
    [
        "}",
        "",
        "SRD_SPELL_COUNT = sum(len(v) for v in SRD_SPELLS_BY_LEVEL.values())",
        "",
    ]
)
OUT.write_text("\n".join(lines), encoding="utf-8")
total = sum(len(v) for v in sections.values())
print(f"Wrote {OUT} ({total} spells)")
for lvl in sorted(sections.keys()):
    print(f"  level {lvl}: {len(sections[lvl])}")
