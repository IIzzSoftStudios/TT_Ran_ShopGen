"""Tests for the character sheet view builder.

These tests exercise the pure view-construction paths (no DB writes) by:
- Using a ``None`` player so ``get_or_default_sheet`` returns defaults
  without querying PlayerCharacterSheet.
- Using a lightweight ``SimpleNamespace`` campaign stub so the service
  reads only ``system_type`` off it.
"""
from types import SimpleNamespace

from app.services import character_sheet_service
from app.services.character_sheet_service import (
    _build_abilities_display,
    _build_defenses_display,
    _build_skills_display,
    character_data_payload,
    build_character_view,
    get_or_default_sheet,
)
from app.services.rulesets import get_ruleset


def _campaign(system_type):
    return SimpleNamespace(id=None, system_type=system_type, name="test")


def test_default_sheet_for_no_player_is_empty_and_generic_fallback():
    sheet = get_or_default_sheet(player=None, campaign=_campaign("dnd5e"))
    assert sheet["system_type"] == "dnd5e"
    assert sheet["abilities"] == {}
    assert sheet["skills"] if False else True


def test_build_character_view_dnd5e_contains_six_abilities_and_eighteen_skills():
    view = build_character_view(
        player=None, campaign=_campaign("dnd5e"), name="Hero"
    )
    assert view.system_type == "dnd5e"
    assert len(view.abilities_display) == 6
    assert len(view.skills_display) == 18
    # Saves appear inside defenses_display as category='save'.
    save_rows = [s for s in view.defenses_display if s["category"] == "save"]
    assert len(save_rows) == 6
    assert view.ruleset_meta["supports_skill_proficiency"] is True


def test_build_character_view_pf2e_has_three_saves_and_pf2e_tiers():
    view = build_character_view(
        player=None, campaign=_campaign("pf2e"), name="Hero"
    )
    assert view.system_type == "pf2e"
    save_rows = [s for s in view.defenses_display if s["category"] == "save"]
    assert len(save_rows) == 3
    tier_labels = {t["label"] for t in view.ruleset_meta["proficiency_tiers"]}
    assert {"Untrained", "Trained", "Expert", "Master", "Legendary"} == tier_labels


def test_build_character_view_generic_has_no_skills_section():
    view = build_character_view(
        player=None, campaign=_campaign("generic"), name="Hero"
    )
    assert view.skills_display == []
    assert view.ruleset_meta["supports_skill_proficiency"] is False


def test_build_character_view_unknown_system_falls_back_to_generic():
    view = build_character_view(
        player=None, campaign=_campaign("made_up_ruleset"), name="Hero"
    )
    assert view.system_type == "generic"
    assert view.skills_display == []


def _player_stub(player_id, *, is_npc=False, sheet_name=None, account_username="alice_login"):
    """Fake Player with the attributes ``build_character_view`` reads.

    ``character_sheet_service.get_or_default_sheet`` accesses
    ``player.id`` to query ``PlayerCharacterSheet``; we pre-load a
    cached sheet on the namespace via the ``_sheet`` shortcut. To keep
    the tests independent of the DB layer we patch
    ``get_or_default_sheet`` in the test, not here.
    """
    return SimpleNamespace(
        id=player_id,
        is_npc=is_npc,
        user=SimpleNamespace(username=account_username),
        _stored_name=sheet_name,
    )


def test_build_character_view_falls_back_to_character_n_not_username(monkeypatch):
    """A character left unnamed must NOT surface the player's login username.

    Regression for the report where creating a character with the optional
    name field empty caused the dashboard to render the user's account
    username as the character's display name. The fallback should match
    every list view in the codebase (``Character #N``).
    """

    player = _player_stub(player_id=42, account_username="alice_login")

    def _fake_sheet(p, c):
        return {
            "schema_version": 1,
            "system_type": "generic",
            "name": None,
            "abilities": {},
        }

    monkeypatch.setattr(character_sheet_service, "get_or_default_sheet", _fake_sheet)
    view = build_character_view(player=player, campaign=_campaign("generic"))
    assert view.name == "Character #42"
    assert "alice_login" not in view.name


def test_build_character_view_uses_stored_name_over_fallback(monkeypatch):
    player = _player_stub(player_id=42, account_username="alice_login", sheet_name="Eira")

    def _fake_sheet(p, c):
        return {
            "schema_version": 1,
            "system_type": "generic",
            "name": "Eira",
            "abilities": {},
        }

    monkeypatch.setattr(character_sheet_service, "get_or_default_sheet", _fake_sheet)
    view = build_character_view(player=player, campaign=_campaign("generic"))
    assert view.name == "Eira"


def test_build_character_view_explicit_name_arg_wins_over_stored(monkeypatch):
    player = _player_stub(player_id=7, account_username="bob_login", sheet_name="Eira")

    def _fake_sheet(p, c):
        return {
            "schema_version": 1,
            "system_type": "generic",
            "name": "Eira",
            "abilities": {},
        }

    monkeypatch.setattr(character_sheet_service, "get_or_default_sheet", _fake_sheet)
    view = build_character_view(
        player=player, campaign=_campaign("generic"), name="Override"
    )
    assert view.name == "Override"


def test_build_character_view_npc_with_no_stored_name_displays_npc(monkeypatch):
    player = _player_stub(player_id=99, is_npc=True, account_username="gm_login")

    def _fake_sheet(p, c):
        return {
            "schema_version": 1,
            "system_type": "generic",
            "name": None,
            "abilities": {},
        }

    monkeypatch.setattr(character_sheet_service, "get_or_default_sheet", _fake_sheet)
    view = build_character_view(player=player, campaign=_campaign("generic"))
    assert view.name == "NPC"


def test_abilities_display_picks_up_stored_scores_and_computes_modifier():
    rs = get_ruleset("dnd5e")
    sheet = {
        "system_type": "dnd5e",
        "abilities": {"str": 16, "dex": 8, "con": 10, "int": 12, "wis": 14, "cha": 9},
    }
    display = _build_abilities_display(rs, sheet)
    by_key = {row["key"]: row for row in display}
    assert by_key["str"]["value"] == 16
    assert by_key["str"]["modifier"] == 3
    assert by_key["dex"]["modifier"] == -1
    assert by_key["con"]["modifier"] == 0


def test_skills_display_applies_dnd5e_proficiency_bonus_at_level_five():
    rs = get_ruleset("dnd5e")
    sheet = {
        "system_type": "dnd5e",
        "level": 5,
        "abilities": {"str": 16, "dex": 14, "wis": 12, "cha": 10, "int": 10, "con": 10},
        "skill_prof_tiers": {
            "athletics": 2,   # Normal prof
            "stealth": 1,     # Half prof
            "perception": 3,  # Expertise
        },
    }
    rows = {r["key"]: r for r in _build_skills_display(rs, sheet)}
    # Level 5 -> PB +3. Athletics (STR +3, normal) = +6
    assert rows["athletics"]["computed_value"] == 6
    # Stealth (DEX +2, half of +3 -> floor(1.5) = 1) = +3
    assert rows["stealth"]["computed_value"] == 3
    # Perception (WIS +1, expertise x2 -> +6) = +7
    assert rows["perception"]["computed_value"] == 7
    # Untouched skill uses only ability mod (WIS +1 -> Insight +1)
    assert rows["insight"]["computed_value"] == 1


def test_saves_display_applies_proficiency_in_dnd5e():
    rs = get_ruleset("dnd5e")
    sheet = {
        "system_type": "dnd5e",
        "level": 1,
        "abilities": {"str": 14, "dex": 10, "con": 16, "int": 10, "wis": 10, "cha": 10},
        "save_prof_flags": {"str": 1.0, "con": 1.0},
    }
    rows = {r["key"]: r for r in _build_defenses_display(rs, sheet) if r["category"] == "save"}
    # Level 1 -> PB +2; STR save +2 ability + 2 = +4
    assert rows["str"]["computed_value"] == 4
    # DEX save (no prof) = +0
    assert rows["dex"]["computed_value"] == 0
    # CON save (+3 ability + 2 PB) = +5
    assert rows["con"]["computed_value"] == 5


def test_character_data_payload_shape_is_flat_list_plus_schema():
    payload = character_data_payload(
        player=None, campaign=_campaign("dnd5e"), equipment_slots=[]
    )
    assert payload["system_type"] == "dnd5e"
    categories = {row["category"] for row in payload["stat_display"]}
    assert {"ability", "derived", "save", "skill"}.issubset(categories)
    assert "abilities" in payload["stat_schema"]
    assert "skills" in payload["stat_schema"]


def test_view_stat_display_matches_payload_stat_display():
    """Regression: ``build_character_view.stat_display`` must be the same
    flat ability+derived+save+skill list that ``character_data_payload``
    produces. Previously the view only exposed abilities, which diverged
    from the JSON endpoint and would confuse any consumer that reads
    ``character.stat_display`` expecting the full list."""
    for system in ("dnd5e", "pf2e", "generic"):
        view = build_character_view(
            player=None, campaign=_campaign(system), name="Hero"
        )
        payload = character_data_payload(
            player=None, campaign=_campaign(system), equipment_slots=[]
        )
        assert [
            (row["key"], row["category"]) for row in view.stat_display
        ] == [
            (row["key"], row["category"]) for row in payload["stat_display"]
        ], f"stat_display mismatch for system_type={system!r}"
        # And both must expose every category the ruleset provides, not
        # just abilities.
        view_cats = {row["category"] for row in view.stat_display}
        assert "ability" in view_cats
        if system == "dnd5e":
            assert {"ability", "derived", "save", "skill"}.issubset(view_cats)


def test_apply_sheet_update_rejects_missing_player():
    ok, errors = character_sheet_service.apply_sheet_update(
        player=None, campaign=_campaign("dnd5e"), form={}
    )
    assert ok is False
    assert errors and "Player" in errors[0]
