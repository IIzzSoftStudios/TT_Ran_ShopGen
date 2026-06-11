"""Pure D&D 5e (SRD 5.1) combat rule helpers.

Every function here is deterministic given an injected ``random.Random``
instance and never imports Flask, the database, or any global mutable
state. Routes/services own persistence; this module owns the math.

Condition identifiers are SRD-safe machine strings only -- no rules text
or lore is reproduced here.
"""

from __future__ import annotations

import math
import re
from random import Random


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# SRD 5.1 condition keys (machine identifiers, not rules text).
CONDITIONS = (
    "blinded",
    "charmed",
    "deafened",
    "frightened",
    "grappled",
    "incapacitated",
    "invisible",
    "paralyzed",
    "petrified",
    "poisoned",
    "prone",
    "restrained",
    "stunned",
    "unconscious",
)

ROLL_MODES = ("normal", "advantage", "disadvantage")

# Diagonal movement cost modes for the square grid.
DIAGONAL_MODES = ("five_ten_five", "always_five", "euclidean")

GRID_CELL_FT = 5

_DICE_RE = re.compile(r"^\s*(\d*)d(\d+)\s*([+-]\s*\d+)?\s*$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Core math
# ---------------------------------------------------------------------------

def ability_modifier(score) -> int:
    """Standard 5e ability modifier: (score - 10) // 2, floor division."""
    try:
        value = int(score)
    except (TypeError, ValueError):
        value = 10
    return (value - 10) // 2


def proficiency_bonus(level) -> int:
    """Stock 5e progression: +2 at 1-4, +3 at 5-8, ... +6 at 17-20."""
    if level is None or int(level) <= 0:
        return 2
    return 2 + ((int(level) - 1) // 4)


def parse_dice(notation: str):
    """Parse ``XdY+Z`` notation into ``(count, sides, modifier)``.

    Raises ``ValueError`` for anything that is not valid dice notation, or
    that would be abusive to roll (caps: 100 dice, d1000).
    """
    if not isinstance(notation, str):
        raise ValueError("Dice notation must be a string.")
    m = _DICE_RE.match(notation)
    if not m:
        raise ValueError(f"Invalid dice notation: {notation!r}")
    count = int(m.group(1) or 1)
    sides = int(m.group(2))
    modifier = int(m.group(3).replace(" ", "")) if m.group(3) else 0
    if count < 1 or count > 100:
        raise ValueError("Dice count must be between 1 and 100.")
    if sides < 2 or sides > 1000:
        raise ValueError("Dice sides must be between 2 and 1000.")
    return count, sides, modifier


def roll_dice(notation: str, rng: Random):
    """Roll ``XdY+Z`` and return ``{"total", "rolls", "modifier", "notation"}``."""
    count, sides, modifier = parse_dice(notation)
    rolls = [rng.randint(1, sides) for _ in range(count)]
    return {
        "notation": notation,
        "rolls": rolls,
        "modifier": modifier,
        "total": sum(rolls) + modifier,
    }


def d20_roll(modifier: int, rng: Random, mode: str = "normal"):
    """Roll a d20 with optional advantage/disadvantage.

    Returns ``{"rolls", "natural", "total", "mode", "is_nat20", "is_nat1"}``.
    ``natural`` is the kept die before the modifier is applied.
    """
    if mode not in ROLL_MODES:
        raise ValueError(f"Unknown roll mode: {mode!r}")
    rolls = [rng.randint(1, 20)]
    if mode in ("advantage", "disadvantage"):
        rolls.append(rng.randint(1, 20))
    natural = max(rolls) if mode == "advantage" else min(rolls)
    return {
        "rolls": rolls,
        "natural": natural,
        "total": natural + int(modifier),
        "mode": mode,
        "is_nat20": natural == 20,
        "is_nat1": natural == 1,
    }


# ---------------------------------------------------------------------------
# Grid distance / movement
# ---------------------------------------------------------------------------

def grid_distance_ft(ax: int, ay: int, bx: int, by: int, mode: str = "five_ten_five") -> int:
    """Distance in feet between two grid cells under the given diagonal mode.

    - ``five_ten_five``: alternating 5/10 ft diagonals (DMG variant).
    - ``always_five``: Chebyshev distance, every step 5 ft (PHB default).
    - ``euclidean``: straight-line distance rounded to the nearest 5 ft.
    """
    dx = abs(int(bx) - int(ax))
    dy = abs(int(by) - int(ay))
    if mode == "always_five":
        return max(dx, dy) * GRID_CELL_FT
    if mode == "five_ten_five":
        diagonals = min(dx, dy)
        straight = max(dx, dy) - diagonals
        # Every second diagonal costs 10 ft.
        return straight * GRID_CELL_FT + (diagonals + diagonals // 2) * GRID_CELL_FT
    if mode == "euclidean":
        return int(round(math.hypot(dx, dy) * GRID_CELL_FT / 5.0)) * 5
    raise ValueError(f"Unknown diagonal mode: {mode!r}")


def movement_cost_ft(path, mode: str = "five_ten_five") -> int:
    """Total cost in feet for a path of grid cells ``[(x, y), ...]``.

    Each consecutive pair must be adjacent (including diagonals). For
    ``five_ten_five`` the alternation is tracked across the whole path.
    """
    if mode not in DIAGONAL_MODES:
        raise ValueError(f"Unknown diagonal mode: {mode!r}")
    total = 0
    diagonal_count = 0
    for (ax, ay), (bx, by) in zip(path, path[1:]):
        dx = abs(int(bx) - int(ax))
        dy = abs(int(by) - int(ay))
        if dx > 1 or dy > 1 or (dx == 0 and dy == 0):
            raise ValueError("Path steps must move exactly one adjacent cell.")
        if dx == 1 and dy == 1:
            if mode == "always_five":
                total += GRID_CELL_FT
            elif mode == "euclidean":
                total += GRID_CELL_FT  # per-step euclidean ~7ft rounds to 5
            else:
                diagonal_count += 1
                total += GRID_CELL_FT if diagonal_count % 2 == 1 else 2 * GRID_CELL_FT
        else:
            total += GRID_CELL_FT
    return total


# ---------------------------------------------------------------------------
# Attacks, damage, saves
# ---------------------------------------------------------------------------

def resolve_attack_roll(attack_mod: int, target_ac: int, rng: Random, mode: str = "normal"):
    """Resolve a d20 attack vs AC.

    Natural 20 always hits and crits; natural 1 always misses. Returns the
    d20 result dict extended with ``hit`` / ``crit`` / ``target_ac``.
    """
    result = d20_roll(attack_mod, rng, mode)
    crit = result["is_nat20"]
    hit = crit or (not result["is_nat1"] and result["total"] >= int(target_ac))
    result.update({"hit": hit, "crit": crit, "target_ac": int(target_ac)})
    return result


def roll_damage(notation: str, rng: Random, crit: bool = False):
    """Roll damage dice; a crit doubles the dice (not the flat modifier)."""
    count, sides, modifier = parse_dice(notation)
    if crit:
        count *= 2
    rolls = [rng.randint(1, sides) for _ in range(count)]
    total = max(0, sum(rolls) + modifier)
    return {
        "notation": notation,
        "crit": crit,
        "rolls": rolls,
        "modifier": modifier,
        "total": total,
    }


def apply_damage(hp_current: int, temp_hp: int, amount: int):
    """Apply damage temp-HP-first.

    Returns ``{"hp_current", "temp_hp", "absorbed", "taken"}`` where
    ``absorbed`` is the temp HP consumed and ``taken`` is the HP lost.
    HP floors at 0 (death/dying handled by the caller via settings).
    """
    amount = max(0, int(amount))
    temp_hp = max(0, int(temp_hp))
    hp_current = max(0, int(hp_current))
    absorbed = min(temp_hp, amount)
    remainder = amount - absorbed
    taken = min(hp_current, remainder)
    return {
        "hp_current": hp_current - taken,
        "temp_hp": temp_hp - absorbed,
        "absorbed": absorbed,
        "taken": taken,
    }


def apply_healing(hp_current: int, hp_max: int, amount: int):
    """Heal up to ``hp_max``; returns ``{"hp_current", "healed"}``."""
    amount = max(0, int(amount))
    hp_current = max(0, int(hp_current))
    hp_max = max(0, int(hp_max))
    healed = min(amount, hp_max - hp_current)
    return {"hp_current": hp_current + healed, "healed": max(0, healed)}


def saving_throw(save_mod: int, dc: int, rng: Random, mode: str = "normal"):
    """Roll a saving throw vs DC; returns d20 dict extended with ``success``."""
    result = d20_roll(save_mod, rng, mode)
    result.update({"dc": int(dc), "success": result["total"] >= int(dc)})
    return result


def concentration_dc(damage: int) -> int:
    """Concentration save DC: the greater of 10 or half the damage taken."""
    return max(10, int(damage) // 2)


def roll_death_save(rng: Random):
    """Roll one death saving throw.

    Returns ``{"natural", "successes", "failures", "revived"}`` deltas:
    nat 20 revives at 1 HP, nat 1 counts as two failures, 10+ is one
    success, otherwise one failure.
    """
    natural = rng.randint(1, 20)
    if natural == 20:
        return {"natural": natural, "successes": 0, "failures": 0, "revived": True}
    if natural == 1:
        return {"natural": natural, "successes": 0, "failures": 2, "revived": False}
    if natural >= 10:
        return {"natural": natural, "successes": 1, "failures": 0, "revived": False}
    return {"natural": natural, "successes": 0, "failures": 1, "revived": False}


# ---------------------------------------------------------------------------
# Initiative
# ---------------------------------------------------------------------------

def roll_initiative(dex_mod: int, rng: Random, mode: str = "normal"):
    """Initiative is a Dexterity-modified d20 roll."""
    return d20_roll(dex_mod, rng, mode)


def order_initiative(entries, rng: Random, tie_mode: str = "dex_then_random"):
    """Sort initiative entries into turn order (highest first).

    ``entries`` is a list of dicts with at least ``id``, ``initiative`` and
    ``dex_mod``. Ties break by ``dex_mod`` (descending) and then, under
    ``dex_then_random``, by a deterministic shuffle from ``rng``; under
    ``stable`` ties keep insertion order. Returns a new sorted list.
    """
    if tie_mode not in ("dex_then_random", "stable"):
        raise ValueError(f"Unknown initiative tie mode: {tie_mode!r}")
    decorated = []
    for index, entry in enumerate(entries):
        jitter = rng.random() if tie_mode == "dex_then_random" else 0.0
        decorated.append(
            (
                -int(entry["initiative"]),
                -int(entry.get("dex_mod") or 0),
                jitter,
                index,
                entry,
            )
        )
    decorated.sort(key=lambda row: row[:4])
    return [row[4] for row in decorated]
