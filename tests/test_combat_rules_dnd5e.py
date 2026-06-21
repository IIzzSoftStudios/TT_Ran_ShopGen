"""Pure-math tests for app.services.combat.dnd5e_rules (no Flask/DB)."""

from __future__ import annotations

from random import Random

import pytest

from app.services.combat import dnd5e_rules as rules


def rng(seed: int = 42) -> Random:
    return Random(seed)


# ---------------------------------------------------------------------------
# Modifiers / proficiency
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "score,expected",
    [(1, -5), (8, -1), (9, -1), (10, 0), (11, 0), (14, 2), (20, 5), (30, 10)],
)
def test_ability_modifier(score, expected):
    assert rules.ability_modifier(score) == expected


def test_ability_modifier_bad_input_defaults_to_ten():
    assert rules.ability_modifier(None) == 0
    assert rules.ability_modifier("junk") == 0


@pytest.mark.parametrize(
    "level,expected",
    [(None, 2), (0, 2), (1, 2), (4, 2), (5, 3), (8, 3), (9, 4), (13, 5), (17, 6), (20, 6)],
)
def test_proficiency_bonus(level, expected):
    assert rules.proficiency_bonus(level) == expected


# ---------------------------------------------------------------------------
# Dice parsing / rolling
# ---------------------------------------------------------------------------
def test_parse_dice_variants():
    assert rules.parse_dice("2d6+3") == (2, 6, 3)
    assert rules.parse_dice("d20") == (1, 20, 0)
    assert rules.parse_dice("1d8-1") == (1, 8, -1)
    assert rules.parse_dice("10D10 + 5") == (10, 10, 5)


@pytest.mark.parametrize("bad", ["", "abc", "2d", "d", "0d6", "101d6", "2d1", "2d9999", None, 5])
def test_parse_dice_rejects_invalid(bad):
    with pytest.raises(ValueError):
        rules.parse_dice(bad)


def test_roll_dice_deterministic_and_in_range():
    a = rules.roll_dice("4d6+2", rng(7))
    b = rules.roll_dice("4d6+2", rng(7))
    assert a == b
    assert len(a["rolls"]) == 4
    assert all(1 <= r <= 6 for r in a["rolls"])
    assert a["total"] == sum(a["rolls"]) + 2


def test_d20_roll_modes():
    normal = rules.d20_roll(3, rng(1), "normal")
    assert len(normal["rolls"]) == 1
    assert normal["total"] == normal["natural"] + 3

    adv = rules.d20_roll(0, rng(2), "advantage")
    assert len(adv["rolls"]) == 2
    assert adv["natural"] == max(adv["rolls"])

    dis = rules.d20_roll(0, rng(2), "disadvantage")
    assert dis["rolls"] == adv["rolls"]  # same seed, same dice
    assert dis["natural"] == min(dis["rolls"])

    with pytest.raises(ValueError):
        rules.d20_roll(0, rng(), "lucky")


# ---------------------------------------------------------------------------
# Grid distance / movement cost
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "mode,expected",
    [("always_five", 20), ("five_ten_five", 30), ("euclidean", 30)],
)
def test_grid_distance_pure_diagonal(mode, expected):
    # 4 diagonal steps: 5/10/5/10 = 30 under five_ten_five; 4*5 = 20 flat.
    assert rules.grid_distance_ft(0, 0, 4, 4, mode) == expected


def test_grid_distance_mixed():
    # dx=3, dy=1 -> 1 diagonal + 2 straight = 5 + 10 = 15 (515 mode).
    assert rules.grid_distance_ft(0, 0, 3, 1, "five_ten_five") == 15
    assert rules.grid_distance_ft(0, 0, 3, 1, "always_five") == 15
    with pytest.raises(ValueError):
        rules.grid_distance_ft(0, 0, 1, 1, "weird")


def test_movement_cost_alternating_diagonals():
    path = [(0, 0), (1, 1), (2, 2), (3, 3)]
    assert rules.movement_cost_ft(path, "five_ten_five") == 20  # 5+10+5
    assert rules.movement_cost_ft(path, "always_five") == 15


def test_movement_cost_rejects_teleports_and_no_ops():
    with pytest.raises(ValueError):
        rules.movement_cost_ft([(0, 0), (2, 0)])
    with pytest.raises(ValueError):
        rules.movement_cost_ft([(0, 0), (0, 0)])


# ---------------------------------------------------------------------------
# Attack resolution / damage
# ---------------------------------------------------------------------------
def _seed_for_natural(target: int, mode: str = "normal") -> Random:
    """Find a seed whose first kept d20 equals ``target``."""
    for seed in range(2000):
        result = rules.d20_roll(0, Random(seed), mode)
        if result["natural"] == target:
            return Random(seed)
    raise AssertionError("no seed found")


def test_attack_nat20_always_hits_and_crits():
    r = rules.resolve_attack_roll(0, 999, _seed_for_natural(20))
    assert r["hit"] and r["crit"]


def test_attack_nat1_always_misses():
    r = rules.resolve_attack_roll(50, 1, _seed_for_natural(1))
    assert not r["hit"] and not r["crit"]


def test_attack_meets_ac_hits():
    r = rules.resolve_attack_roll(5, 15, _seed_for_natural(10))
    assert r["total"] == 15 and r["hit"] and not r["crit"]
    r2 = rules.resolve_attack_roll(4, 15, _seed_for_natural(10))
    assert r2["total"] == 14 and not r2["hit"]


def test_roll_damage_crit_doubles_dice_not_modifier():
    normal = rules.roll_damage("2d6+3", rng(5))
    crit = rules.roll_damage("2d6+3", rng(5), crit=True)
    assert len(normal["rolls"]) == 2
    assert len(crit["rolls"]) == 4
    assert crit["modifier"] == 3


def test_roll_damage_never_negative():
    out = rules.roll_damage("1d2-10", rng(1))
    assert out["total"] == 0


def test_apply_damage_temp_hp_first():
    out = rules.apply_damage(hp_current=20, temp_hp=5, amount=8)
    assert out == {"hp_current": 17, "temp_hp": 0, "absorbed": 5, "taken": 3}


def test_apply_damage_floors_at_zero():
    out = rules.apply_damage(hp_current=4, temp_hp=0, amount=50)
    assert out["hp_current"] == 0 and out["taken"] == 4


def test_apply_healing_caps_at_max():
    out = rules.apply_healing(hp_current=18, hp_max=20, amount=10)
    assert out == {"hp_current": 20, "healed": 2}


# ---------------------------------------------------------------------------
# Saves / concentration / death saves
# ---------------------------------------------------------------------------
def test_saving_throw_success_and_failure():
    win = rules.saving_throw(5, 15, _seed_for_natural(10))
    assert win["success"]
    lose = rules.saving_throw(4, 15, _seed_for_natural(10))
    assert not lose["success"]


@pytest.mark.parametrize("damage,dc", [(0, 10), (19, 10), (21, 10), (22, 11), (44, 22)])
def test_concentration_dc(damage, dc):
    assert rules.concentration_dc(damage) == dc


def test_death_save_outcomes():
    nat20 = rules.roll_death_save(_seed_for_natural(20))
    assert nat20["revived"]
    nat1 = rules.roll_death_save(_seed_for_natural(1))
    assert nat1["failures"] == 2
    ten = rules.roll_death_save(_seed_for_natural(10))
    assert ten["successes"] == 1
    nine = rules.roll_death_save(_seed_for_natural(9))
    assert nine["failures"] == 1


# ---------------------------------------------------------------------------
# Initiative ordering
# ---------------------------------------------------------------------------
def test_order_initiative_sorts_high_to_low_with_dex_tiebreak():
    entries = [
        {"id": 1, "initiative": 12, "dex_mod": 1},
        {"id": 2, "initiative": 18, "dex_mod": 0},
        {"id": 3, "initiative": 12, "dex_mod": 4},
    ]
    ordered = rules.order_initiative(entries, rng(9))
    assert [e["id"] for e in ordered] == [2, 3, 1]


def test_order_initiative_random_tiebreak_is_deterministic_per_seed():
    entries = [
        {"id": i, "initiative": 10, "dex_mod": 2} for i in range(6)
    ]
    a = [e["id"] for e in rules.order_initiative(entries, rng(3))]
    b = [e["id"] for e in rules.order_initiative(entries, rng(3))]
    assert a == b


def test_order_initiative_stable_mode_keeps_insertion_order():
    entries = [
        {"id": "a", "initiative": 10, "dex_mod": 2},
        {"id": "b", "initiative": 10, "dex_mod": 2},
    ]
    ordered = rules.order_initiative(entries, rng(0), tie_mode="stable")
    assert [e["id"] for e in ordered] == ["a", "b"]
    with pytest.raises(ValueError):
        rules.order_initiative(entries, rng(0), tie_mode="coin_flip")


def test_conditions_are_srd_machine_keys():
    assert "prone" in rules.CONDITIONS
    assert all(c == c.lower() and " " not in c for c in rules.CONDITIONS)
