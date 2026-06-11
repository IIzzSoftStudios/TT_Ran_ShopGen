"""Deterministic procedural monster template generator (D&D 5e mechanics).

Produces purely mechanical SRD-style stat blocks from a seed string: the
same ``(seed, challenge)`` input always yields the same template. Names are
generated from neutral fantasy syllables -- no WotC Product Identity names
and no bundled monster database.
"""

from __future__ import annotations

import hashlib
from random import Random

from app.services.combat import dnd5e_rules as rules

# Neutral descriptive vocabulary; deliberately avoids any Product Identity.
_NAME_PREFIXES = (
    "Ashen", "Dire", "Feral", "Gloom", "Grave", "Iron", "Marsh", "Night",
    "Rime", "Shadow", "Stone", "Storm", "Thorn", "Vile", "Wild",
)
_NAME_CREATURES = (
    "Stalker", "Brute", "Crawler", "Howler", "Lurker", "Mauler", "Prowler",
    "Render", "Shrieker", "Skitterer", "Slinger", "Warden", "Wretch",
)

_ROLES = ("bruiser", "skirmisher", "lurker", "sniper")

_DAMAGE_TYPES = ("bludgeoning", "piercing", "slashing")


def derive_seed(raw_seed: str | None, rng: Random | None = None) -> str:
    """Normalize a GM-supplied seed (or mint a random one) to a sha256 hex."""
    if raw_seed is None or not str(raw_seed).strip():
        source_rng = rng or Random()
        raw_seed = f"auto-{source_rng.getrandbits(64):016x}"
    return hashlib.sha256(str(raw_seed).strip().encode("utf-8")).hexdigest()


def generate_monster_template(seed_hex: str, challenge: float = 1.0) -> dict:
    """Build a deterministic mechanical stat block for the given seed.

    ``challenge`` roughly follows the 5e CR ladder (0.25 .. 10 supported in
    v1) and scales HP, AC, attack bonus, and damage dice.
    """
    try:
        challenge = float(challenge)
    except (TypeError, ValueError):
        challenge = 1.0
    challenge = min(10.0, max(0.25, challenge))

    rng = Random(int(seed_hex[:16], 16))
    role = rng.choice(_ROLES)
    name = f"{rng.choice(_NAME_PREFIXES)} {rng.choice(_NAME_CREATURES)}"

    # Ability scores: role-weighted 8..18, scaled slightly by CR.
    cr_bump = int(challenge // 3)
    abilities = {}
    for key in ("str", "dex", "con", "int", "wis", "cha"):
        base = rng.randint(8, 14)
        if role == "bruiser" and key in ("str", "con"):
            base += rng.randint(2, 4)
        elif role in ("skirmisher", "lurker") and key == "dex":
            base += rng.randint(2, 4)
        elif role == "sniper" and key in ("dex", "wis"):
            base += rng.randint(1, 3)
        abilities[key] = min(20, base + cr_bump)

    con_mod = rules.ability_modifier(abilities["con"])
    dex_mod = rules.ability_modifier(abilities["dex"])
    str_mod = rules.ability_modifier(abilities["str"])

    hit_dice = max(1, int(2 + challenge * 3 + rng.randint(0, 2)))
    hp_max = max(1, hit_dice * (4 + con_mod) + rng.randint(0, hit_dice))
    ac = 10 + dex_mod + min(4, int(challenge // 2)) + (1 if role == "bruiser" else 0)
    speed_ft = 30 + (10 if role == "skirmisher" else 0) - (5 if role == "bruiser" and rng.random() < 0.3 else 0)

    prof = rules.proficiency_bonus(max(1, int(challenge * 2)))
    melee_mod = max(str_mod, dex_mod)
    damage_dice_count = max(1, int(round(challenge)))

    attacks = [
        {
            "key": "melee",
            "name": f"{name.split()[-1]} Strike",
            "kind": "melee",
            "attack_mod": melee_mod + prof,
            "damage": f"{damage_dice_count}d6+{max(0, melee_mod)}",
            "damage_type": rng.choice(_DAMAGE_TYPES),
            "range_ft": 5,
        }
    ]
    if role in ("sniper", "skirmisher", "lurker"):
        attacks.append(
            {
                "key": "ranged",
                "name": "Hurled Spike",
                "kind": "ranged",
                "attack_mod": dex_mod + prof,
                "damage": f"{max(1, damage_dice_count - 1)}d6+{max(0, dex_mod)}",
                "damage_type": "piercing",
                "range_ft": 60,
            }
        )

    return {
        "name": name,
        "role": role,
        "challenge_rating": challenge,
        "abilities": abilities,
        "hp_max": hp_max,
        "ac": min(21, ac),
        "speed_ft": max(20, speed_ft),
        "dex_mod": dex_mod,
        "attack_bonus": melee_mod + prof,
        "attacks": attacks,
        "generation_seed": seed_hex,
    }
