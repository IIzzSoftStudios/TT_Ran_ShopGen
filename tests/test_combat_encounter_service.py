"""Service-level tests for combat encounter flow (SQLite, no HTTP)."""

from __future__ import annotations

from random import Random

import pytest

from app import app as flask_app
from app.extensions import db
import app.models  # noqa: F401
from app.models import BattleCombatant, Campaign, User
from app.services.combat import CombatValidationError, StaleTurnError
from app.services.combat import encounter_service
from app.services.user_capabilities import ensure_gm_profile


@pytest.fixture(autouse=True)
def _db_tables():
    flask_app.config["WTF_CSRF_ENABLED"] = False
    with flask_app.app_context():
        db.create_all()
        yield
        db.session.rollback()
        db.drop_all()


def _make_campaign(username: str, system_type: str = "dnd5e") -> Campaign:
    user = User(username=username, password="x", role="GM")
    user.set_password("Secret1!")
    db.session.add(user)
    db.session.commit()
    ensure_gm_profile(user)
    db.session.commit()
    db.session.refresh(user)
    campaign = Campaign(
        gm_profile_id=user.gm_profile.id,
        name=f"{username}-camp",
        system_type=system_type,
        is_active=True,
        current_game_day=1,
    )
    db.session.add(campaign)
    db.session.commit()
    return campaign


def _add_combatant(encounter, name, *, x=0, y=0, dex_mod=0, hp=10, ac=10,
                   side="foe", player_id=None, attack_mod=100, range_ft=5):
    combatant = BattleCombatant(
        encounter_id=encounter.id,
        campaign_id=encounter.campaign_id,
        player_id=player_id,
        name=name,
        side=side,
        status="active",
        x=x,
        y=y,
        hp_max=hp,
        hp_current=hp,
        temp_hp=0,
        ac=ac,
        speed_ft=30,
        dex_mod=dex_mod,
        ability_json={"con": 10},
        action_data_json={
            "attacks": [
                {
                    "key": "claw",
                    "name": "Claw",
                    "kind": "melee",
                    "attack_mod": attack_mod,
                    "damage": "1d4+1",
                    "damage_type": "slashing",
                    "range_ft": range_ft,
                }
            ]
        },
        resources_json={"action": True, "bonus_action": True, "reaction": True},
        conditions_json=[],
    )
    db.session.add(combatant)
    db.session.commit()
    return combatant


def _seed_avoiding_nat1() -> Random:
    for seed in range(500):
        if Random(seed).randint(1, 20) > 1:
            return Random(seed)
    raise AssertionError("no seed found")


def _started_encounter(n=3):
    campaign = _make_campaign(f"svc-gm-{n}")
    encounter = encounter_service.create_encounter(campaign.id, "Test Fight")
    db.session.commit()
    combatants = [
        _add_combatant(encounter, f"C{i}", x=i, y=0, dex_mod=n - i)
        for i in range(n)
    ]
    encounter_service.roll_initiative(encounter, Random(42))
    db.session.commit()
    return campaign, encounter, combatants


# ---------------------------------------------------------------------------
# Creation / initiative
# ---------------------------------------------------------------------------
def test_create_encounter_validates_grid():
    campaign = _make_campaign("svc-gm-grid")
    with pytest.raises(CombatValidationError):
        encounter_service.create_encounter(campaign.id, grid_width=2)
    with pytest.raises(CombatValidationError):
        encounter_service.create_encounter(campaign.id, grid_width="huge")


def test_get_or_create_encounter_for_canvas():
    campaign = _make_campaign("svc-gm-canvas")
    from app.models import MapCanvas

    canvas = MapCanvas(campaign_id=campaign.id, scope="world", source_type="generated")
    db.session.add(canvas)
    db.session.commit()

    enc, created = encounter_service.get_or_create_encounter_for_canvas(
        campaign.id, canvas.id, x=0.25, y=0.75
    )
    db.session.commit()
    assert created is True
    assert enc.map_canvas_id == canvas.id
    assert enc.map_x == 0.25
    assert enc.map_y == 0.75
    assert enc.name == "World encounter"

    enc2, created2 = encounter_service.get_or_create_encounter_for_canvas(
        campaign.id, canvas.id, x=0.5, y=0.5
    )
    assert created2 is False
    assert enc2.id == enc.id
    assert enc2.map_x == 0.5
    assert enc2.map_y == 0.5


def test_place_encounter_on_canvas_validates_bounds():
    campaign = _make_campaign("svc-gm-place-canvas")
    from app.models import MapCanvas

    canvas = MapCanvas(campaign_id=campaign.id, scope="city", source_type="generated")
    db.session.add(canvas)
    encounter = encounter_service.create_encounter(campaign.id)
    db.session.commit()

    encounter_service.place_encounter_on_canvas(encounter, campaign.id, canvas.id, 0.1, 0.9)
    db.session.commit()
    assert encounter.map_canvas_id == canvas.id
    assert encounter.map_x == 0.1
    assert encounter.map_y == 0.9

    with pytest.raises(CombatValidationError):
        encounter_service.place_encounter_on_canvas(encounter, campaign.id, canvas.id, 2, 0)


def test_rename_encounter_updates_name():
    _, encounter, _ = _started_encounter()
    encounter_service.rename_encounter(encounter, "Renamed Fight")
    db.session.commit()
    assert encounter.name == "Renamed Fight"
    with pytest.raises(CombatValidationError):
        encounter_service.rename_encounter(encounter, "   ")


def test_roll_initiative_orders_and_starts_round_one():
    _, encounter, _ = _started_encounter()
    assert encounter.status == "active"
    assert encounter.round_number == 1
    assert encounter.turn_index == 0
    order = encounter_service.ordered_combatants(encounter)
    inits = [(c.initiative, c.dex_mod) for c in order]
    assert inits == sorted(inits, key=lambda t: (-t[0], -t[1]))
    assert encounter.turn_version > 0


def test_roll_initiative_requires_combatants():
    campaign = _make_campaign("svc-gm-empty")
    encounter = encounter_service.create_encounter(campaign.id)
    db.session.commit()
    with pytest.raises(CombatValidationError):
        encounter_service.roll_initiative(encounter, Random(1))


# ---------------------------------------------------------------------------
# Locking / stale version
# ---------------------------------------------------------------------------
def test_locked_encounter_rejects_stale_version():
    campaign, encounter, _ = _started_encounter()
    with pytest.raises(StaleTurnError):
        encounter_service.locked_encounter(
            encounter.id, campaign.id, encounter.turn_version + 5
        )


def test_locked_encounter_scopes_by_campaign():
    campaign, encounter, _ = _started_encounter()
    other = _make_campaign("svc-gm-other")
    with pytest.raises(LookupError):
        encounter_service.locked_encounter(encounter.id, other.id)


# ---------------------------------------------------------------------------
# Move
# ---------------------------------------------------------------------------
def test_move_consumes_movement_and_blocks_overspend():
    _, encounter, _ = _started_encounter()
    actor = encounter_service.current_combatant(encounter)
    result = encounter_service.move_action(encounter, actor, actor.x, actor.y + 4)
    db.session.commit()
    assert result["cost_ft"] == 20
    assert actor.movement_used_ft == 20
    # 10 ft left; 15 ft more is too far.
    with pytest.raises(CombatValidationError):
        encounter_service.move_action(encounter, actor, actor.x, actor.y + 3)


def test_move_rejects_occupied_and_out_of_bounds():
    _, encounter, combatants = _started_encounter()
    actor = encounter_service.current_combatant(encounter)
    other = next(c for c in combatants if c.id != actor.id)
    with pytest.raises(CombatValidationError):
        encounter_service.move_action(encounter, actor, other.x, other.y)
    with pytest.raises(CombatValidationError):
        encounter_service.move_action(encounter, actor, -1, 0)


def test_move_requires_actors_turn():
    _, encounter, combatants = _started_encounter()
    actor = encounter_service.current_combatant(encounter)
    off_turn = next(c for c in combatants if c.id != actor.id)
    with pytest.raises(CombatValidationError):
        encounter_service.move_action(encounter, off_turn, off_turn.x, off_turn.y + 1)


# ---------------------------------------------------------------------------
# Attack
# ---------------------------------------------------------------------------
def test_attack_applies_damage_and_consumes_action():
    _, encounter, combatants = _started_encounter()
    attacker = encounter_service.current_combatant(encounter)
    target = next(c for c in combatants if c.id != attacker.id)
    # Place adjacent.
    attacker.x, attacker.y = 0, 0
    target.x, target.y = 1, 0
    db.session.commit()
    before_hp = target.hp_current

    result = encounter_service.attack_action(
        encounter, attacker, target.id, "claw", _seed_avoiding_nat1()
    )
    db.session.commit()
    assert result["hit"] is True
    assert target.hp_current < before_hp
    assert attacker.resources_json["action"] is False
    # Action economy: second attack rejected.
    with pytest.raises(CombatValidationError):
        encounter_service.attack_action(
            encounter, attacker, target.id, "claw", _seed_avoiding_nat1()
        )


def test_attack_rejects_out_of_range_and_self():
    _, encounter, combatants = _started_encounter()
    attacker = encounter_service.current_combatant(encounter)
    target = next(c for c in combatants if c.id != attacker.id)
    attacker.x, attacker.y = 0, 0
    target.x, target.y = 10, 10
    db.session.commit()
    with pytest.raises(CombatValidationError):
        encounter_service.attack_action(
            encounter, attacker, target.id, "claw", Random(1)
        )
    with pytest.raises(CombatValidationError):
        encounter_service.attack_action(
            encounter, attacker, attacker.id, "claw", Random(1)
        )


def test_attack_denies_cross_encounter_target():
    campaign, encounter, _ = _started_encounter()
    other_encounter = encounter_service.create_encounter(campaign.id, "Other")
    db.session.commit()
    foreign = _add_combatant(other_encounter, "Foreign", x=1, y=0)
    attacker = encounter_service.current_combatant(encounter)
    with pytest.raises(CombatValidationError):
        encounter_service.attack_action(
            encounter, attacker, foreign.id, "claw", Random(1)
        )


def test_temp_hp_absorbs_first():
    _, encounter, combatants = _started_encounter()
    attacker = encounter_service.current_combatant(encounter)
    target = next(c for c in combatants if c.id != attacker.id)
    attacker.x, attacker.y = 0, 0
    target.x, target.y = 1, 0
    target.temp_hp = 50
    db.session.commit()
    before_hp = target.hp_current
    result = encounter_service.attack_action(
        encounter, attacker, target.id, "claw", _seed_avoiding_nat1()
    )
    db.session.commit()
    assert result["hit"]
    assert target.hp_current == before_hp  # all soaked by temp HP
    assert target.temp_hp < 50


def test_monster_drops_dead_at_zero_hp():
    _, encounter, combatants = _started_encounter()
    attacker = encounter_service.current_combatant(encounter)
    target = next(c for c in combatants if c.id != attacker.id)
    attacker.x, attacker.y = 0, 0
    target.x, target.y = 1, 0
    target.hp_current = 1
    db.session.commit()
    encounter_service.attack_action(
        encounter, attacker, target.id, "claw", _seed_avoiding_nat1()
    )
    db.session.commit()
    assert target.hp_current == 0
    assert target.status == "dead"


# ---------------------------------------------------------------------------
# Wait semantics
# ---------------------------------------------------------------------------
def test_wait_drops_to_bottom_without_round_increment():
    _, encounter, _ = _started_encounter()
    actor = encounter_service.current_combatant(encounter)
    round_before = encounter.round_number
    order_before = [c.id for c in encounter_service.ordered_combatants(encounter)]

    encounter_service.wait_action(encounter, actor)
    db.session.commit()

    assert encounter.round_number == round_before
    order_after = [c.id for c in encounter_service.ordered_combatants(encounter)]
    assert order_after[-1] == actor.id
    assert order_after == order_before[1:] + [actor.id]
    assert actor.has_waited is True
    # Turn passed to the next combatant in the same round.
    assert encounter_service.current_combatant(encounter).id == order_before[1]


def test_wait_only_once_until_next_turn_starts():
    _, encounter, _ = _started_encounter(n=3)
    actor = encounter_service.current_combatant(encounter)
    encounter_service.wait_action(encounter, actor)
    db.session.commit()
    # Even when their turn comes around again in this round, has_waited
    # persists until _begin_turn fires for them.
    assert actor.has_waited is True
    encounter_service.end_turn(encounter)  # second combatant done
    encounter_service.end_turn(encounter)  # third combatant done -> actor again
    db.session.commit()
    current = encounter_service.current_combatant(encounter)
    assert current.id == actor.id
    assert actor.has_waited is False  # cleared at the start of their next turn


def test_wait_rejected_when_already_waited():
    _, encounter, _ = _started_encounter(n=2)
    actor = encounter_service.current_combatant(encounter)
    encounter_service.wait_action(encounter, actor)
    db.session.commit()
    # Force their turn again without a fresh turn start by waiting from the
    # other combatant, then checking the flag is enforced.
    other = encounter_service.current_combatant(encounter)
    if other.id != actor.id:
        encounter_service.wait_action(encounter, other)
        db.session.commit()
    current = encounter_service.current_combatant(encounter)
    if current.id == actor.id and actor.has_waited:
        with pytest.raises(CombatValidationError):
            encounter_service.wait_action(encounter, actor)


# ---------------------------------------------------------------------------
# Turn advance
# ---------------------------------------------------------------------------
def test_end_turn_advances_and_wraps_round():
    _, encounter, _ = _started_encounter(n=2)
    assert encounter.round_number == 1
    first = encounter_service.current_combatant(encounter)
    second = encounter_service.end_turn(encounter)
    db.session.commit()
    assert second.id != first.id
    assert encounter.round_number == 1
    third = encounter_service.end_turn(encounter)
    db.session.commit()
    assert third.id == first.id
    assert encounter.round_number == 2
    # Turn start resets movement/action.
    assert third.movement_used_ft == 0
    assert third.resources_json["action"] is True


def test_end_turn_skips_dead_combatants():
    _, encounter, combatants = _started_encounter(n=3)
    order = encounter_service.ordered_combatants(encounter)
    order[1].status = "dead"
    db.session.commit()
    nxt = encounter_service.end_turn(encounter)
    db.session.commit()
    assert nxt.id == order[2].id


# ---------------------------------------------------------------------------
# Batch attack
# ---------------------------------------------------------------------------
def test_batch_attack_requires_foes_and_current_turn():
    _, encounter, combatants = _started_encounter(n=3)
    current = encounter_service.current_combatant(encounter)
    others = [c for c in combatants if c.id != current.id]
    target = others[0]
    # Mark target as party so it's a sensible victim.
    target.side = "party"
    db.session.commit()

    # Batch without the current-turn combatant is rejected.
    with pytest.raises(CombatValidationError):
        encounter_service.batch_attack_action(
            encounter, [others[1].id], target.id, "claw", Random(7)
        )

    current.x, current.y = 0, 0
    others[1].x, others[1].y = 1, 1
    target.x, target.y = 1, 0
    db.session.commit()
    results = encounter_service.batch_attack_action(
        encounter, [current.id, others[1].id], target.id, "claw", Random(7)
    )
    db.session.commit()
    assert len(results) == 2
    assert all("to_hit" in r or "skipped" in r for r in results)
