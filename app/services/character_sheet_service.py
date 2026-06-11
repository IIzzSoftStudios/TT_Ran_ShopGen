"""Character sheet persistence + view builder.

One service boundary between (route, template) and (PlayerCharacterSheet,
ruleset registry). Routes never touch sheet_json directly; they call:

- ``get_or_default_sheet(player, campaign)`` on GET
- ``build_character_view(player, campaign, equipment_slots=..., name=...)``
  on GET to produce the exact SimpleNamespace the Jinja templates consume
- ``apply_sheet_update(player, campaign, form)`` on POST

Security invariants (from the Cyber-Architect review passes):
- Stat / skill / save / defense keys are whitelisted against the rule set
  (never client-supplied).
- Proficiency tier values must be in the rule set's declared tier set.
- Ability scores are clamped to the rule set's ability_min / ability_max.
- The caller is responsible for loading the right Player + Campaign (scope
  enforcement: player self-access via current_user, GM access via the
  campaign's owning GM). This service trusts the objects it is handed.
"""
from datetime import datetime
from types import SimpleNamespace

from app.extensions import db
from app.models import Campaign, Player, PlayerCharacterSheet
from app.services.rulesets import Ruleset, get_ruleset


SHEET_SCHEMA_VERSION = 1


def _empty_sheet(system_type):
    return {
        "schema_version": SHEET_SCHEMA_VERSION,
        "system_type": system_type,
        "name": None,
        "class_name": None,
        "species": None,
        "level": None,
        "notes": None,
        "abilities": {},
        "defenses": {},
        "save_prof_flags": {},
        "skill_prof_tiers": {},
    }


def _system_type_of(campaign):
    if campaign is None:
        return "generic"
    return getattr(campaign, "system_type", None) or "generic"


def _ruleset_for_sheet(campaign, sheet: dict) -> Ruleset:
    st = (sheet.get("system_type") or "").strip().lower()
    if not st or st == "generic":
        st = _system_type_of(campaign)
    return get_ruleset(st)


def create_initial_vault_sheet(player_id, *, system_type, name=None):
    """Insert a fresh vault (campaign_id NULL) sheet for ``player_id``.

    Used by the character-creation form so a brand new ``Player`` row lands
    with the system the user picked baked into ``sheet_json``. Caller owns
    the surrounding transaction (no commit here).
    """
    st = (system_type or "").strip().lower() or "generic"
    sheet = _empty_sheet(st)
    if name:
        clean = str(name).strip()
        if clean:
            sheet["name"] = clean[:100]
    row = PlayerCharacterSheet(
        player_id=player_id,
        campaign_id=None,
        sheet_json=sheet,
    )
    db.session.add(row)
    return row


def ensure_initial_campaign_sheet(player, campaign, *, name=None):
    """Create the starter campaign sheet for a campaign-bound character.

    CAMP-code registration creates the campaign ``Player`` row before the
    full character-builder flow runs. This gives that character a scoped sheet
    immediately so the later walkthrough can edit the existing character
    instead of creating a second solo vault character.
    """
    if player is None or campaign is None:
        return None
    row = PlayerCharacterSheet.query.filter_by(
        player_id=player.id,
        campaign_id=campaign.id,
    ).first()
    if row is not None:
        return row
    sheet = _empty_sheet(_system_type_of(campaign))
    if name:
        clean = str(name).strip()
        if clean:
            sheet["name"] = clean[:100]
    row = PlayerCharacterSheet(
        player_id=player.id,
        campaign_id=campaign.id,
        sheet_json=sheet,
    )
    db.session.add(row)
    return row


def get_or_default_sheet(player, campaign):
    """Return the stored sheet dict (or a defaulted one). Never auto-inserts."""
    if player is None:
        return _empty_sheet(_system_type_of(campaign))

    row = None
    if campaign is not None:
        row = (
            PlayerCharacterSheet.query.filter_by(
                player_id=player.id, campaign_id=campaign.id
            ).first()
        )
    else:
        row = (
            PlayerCharacterSheet.query.filter(
                PlayerCharacterSheet.player_id == player.id,
                PlayerCharacterSheet.campaign_id.is_(None),
            ).first()
        )

    if row is None or not isinstance(row.sheet_json, dict):
        return _empty_sheet(_system_type_of(campaign))

    # Merge with defaults so newly-added top-level keys (future schema
    # versions) do not KeyError older stored blobs.
    merged = _empty_sheet(_system_type_of(campaign))
    for k, v in row.sheet_json.items():
        merged[k] = v
    if campaign is not None:
        # Campaign is source of truth for in-campaign sheets.
        merged["system_type"] = _system_type_of(campaign)
    # Vault (campaign is None): keep ``system_type`` from stored JSON.
    for sub in ("abilities", "defenses", "save_prof_flags", "skill_prof_tiers"):
        if not isinstance(merged.get(sub), dict):
            merged[sub] = {}
    return merged


def _build_abilities_display(ruleset, sheet):
    out = []
    abilities_map = sheet.get("abilities") or {}
    for ab in ruleset.abilities:
        raw = abilities_map.get(ab.key)
        try:
            value = int(raw) if raw is not None and raw != "" else None
        except (TypeError, ValueError):
            value = None
        modifier = (
            ruleset.compute_ability_mod(value) if value is not None else None
        )
        out.append(
            {
                "id": f"ability_{ab.key}",
                "key": ab.key,
                "label": ab.label,
                "category": "ability",
                "value": value,
                "modifier": modifier,
                "computed_value": None,
            }
        )
    return out


def _build_defenses_display(ruleset, sheet):
    out = []
    defenses_map = sheet.get("defenses") or {}
    for d in ruleset.derived:
        raw = defenses_map.get(d.key)
        try:
            value = int(raw) if raw is not None and raw != "" else None
        except (TypeError, ValueError):
            value = None
        out.append(
            {
                "id": f"defense_{d.key}",
                "key": d.key,
                "label": d.label,
                "category": "derived",
                "value": value,
                "modifier": None,
                "computed_value": None,
            }
        )

    # Saves rendered in the same grid with category='save' so the template's
    # per-save proficiency checkbox block fires.
    prof_flags = sheet.get("save_prof_flags") or {}
    level = sheet.get("level") or 0
    prof_bonus = ruleset.proficiency_bonus(level)
    abilities_map = sheet.get("abilities") or {}
    for s in ruleset.saves:
        ability_mod = 0
        if s.ability_key:
            score = abilities_map.get(s.ability_key)
            ability_mod = ruleset.compute_ability_mod(score)
        flag = prof_flags.get(s.key)
        try:
            flag_f = float(flag) if flag is not None else 0.0
        except (TypeError, ValueError):
            flag_f = 0.0
        computed = ability_mod + (prof_bonus * (1 if flag_f >= 0.5 else 0))
        out.append(
            {
                "id": f"save_{s.key}",
                "key": s.key,
                "label": s.label,
                "category": "save",
                "value": None,
                "modifier": None,
                "computed_value": computed,
            }
        )
    return out


def _build_skills_display(ruleset, sheet):
    out = []
    if not ruleset.skills:
        return out
    prof_tiers = sheet.get("skill_prof_tiers") or {}
    level = sheet.get("level") or 0
    prof_bonus = ruleset.proficiency_bonus(level)
    abilities_map = sheet.get("abilities") or {}
    for sk in ruleset.skills:
        ability_mod = ruleset.compute_ability_mod(
            abilities_map.get(sk.ability_key)
        )
        tier_val = prof_tiers.get(sk.key)
        tier = ruleset.tier_by_value(tier_val)
        multiplier = tier.multiplier if tier is not None else 0.0
        # Round half to nearest lower int (D&D 5e half-proficiency rounds down).
        prof_component = int(prof_bonus * multiplier)
        computed = ability_mod + prof_component
        out.append(
            {
                "id": f"skill_{sk.key}",
                "key": sk.key,
                "label": sk.label,
                "category": "skill",
                "value": None,
                "modifier": ability_mod,
                "computed_value": computed,
            }
        )
    return out


def _assemble_display_sections(ruleset, sheet):
    """Build each display section once and return (abilities, derived, saves, skills).

    Centralised so ``build_character_view`` and ``character_data_payload``
    stay in lock-step and do not each rebuild overlapping slices of the
    sheet (which previously made ``stat_display`` diverge between the HTML
    view and the JSON payload).
    """
    abilities = _build_abilities_display(ruleset, sheet)
    defenses_and_saves = _build_defenses_display(ruleset, sheet)
    derived = [row for row in defenses_and_saves if row["category"] == "derived"]
    saves = [row for row in defenses_and_saves if row["category"] == "save"]
    skills = _build_skills_display(ruleset, sheet)
    return abilities, derived, saves, skills


def build_character_view(player, campaign, *, name=None, equipment_slots=None):
    """Produce the SimpleNamespace the character-sheet templates consume."""
    sheet = get_or_default_sheet(player, campaign)
    ruleset = _ruleset_for_sheet(campaign, sheet)

    stored_raw = sheet.get("name") if isinstance(sheet, dict) else None
    stored_name = (stored_raw or "").strip() or None
    if name:
        display_name = name
    elif stored_name:
        display_name = stored_name
    elif player is not None and getattr(player, "is_npc", False):
        display_name = "NPC"
    elif player is not None and getattr(player, "id", None) is not None:
        # Stay consistent with list views (`list_characters`,
        # `_player_character_rows_for_campaign`, and
        # `_build_solo_characters_for_user`) which all fall back to
        # ``Character #N``. Surfacing the account username here was a
        # cross-character PII leak: another player viewing a sheet would
        # learn the owner's login name even though the character was
        # left intentionally unnamed.
        display_name = f"Character #{player.id}"
    else:
        display_name = "Character"

    abilities, derived, saves, skills = _assemble_display_sections(ruleset, sheet)
    defenses_display = derived + saves
    # Flat list in the same shape the JSON payload produces so any consumer
    # (template or frontend) that reads ``character.stat_display`` sees the
    # full ability + derived + save + skill set, not just abilities.
    stat_display = abilities + derived + saves + skills

    return SimpleNamespace(
        id=getattr(player, "id", None),
        name=display_name,
        # Resolved ruleset (unknown campaign.system_type falls back to generic).
        system_type=ruleset.system_type,
        class_name=sheet.get("class_name"),
        species=sheet.get("species"),
        level=sheet.get("level"),
        notes=sheet.get("notes"),
        abilities_display=abilities,
        defenses_display=defenses_display,
        skills_display=skills,
        save_prof_flags=dict(sheet.get("save_prof_flags") or {}),
        skill_prof_tiers=dict(sheet.get("skill_prof_tiers") or {}),
        equipment_slots=equipment_slots or [],
        ruleset_meta=ruleset.to_meta(),
        stat_display=stat_display,
    )


def character_data_payload(player, campaign, *, equipment_slots=None):
    """Shape for /player/character-data (the Player_Home.html panel)."""
    sheet = get_or_default_sheet(player, campaign)
    ruleset = _ruleset_for_sheet(campaign, sheet)

    abilities, derived, saves, skills = _assemble_display_sections(ruleset, sheet)
    stat_display = abilities + derived + saves + skills

    return {
        "system_type": ruleset.system_type,
        "stat_display": stat_display,
        "stat_schema": {
            "abilities": [
                {"key": a.key, "label": a.label} for a in ruleset.abilities
            ],
            "skills": [
                {"key": s.key, "label": s.label, "ability_key": s.ability_key}
                for s in ruleset.skills
            ],
            "saves": [
                {"key": s.key, "label": s.label, "ability_key": s.ability_key}
                for s in ruleset.saves
            ],
            "derived": [
                {"key": d.key, "label": d.label, "header": bool(d.header)}
                for d in ruleset.derived
            ],
            "supports_skill_proficiency": ruleset.supports_skill_proficiency,
            "supports_save_proficiency": ruleset.supports_save_proficiency,
            "proficiency_tiers": [
                {"key": t.key, "label": t.label, "value": t.value}
                for t in ruleset.proficiency_tiers
            ],
        },
        "equipment_slots": equipment_slots or [],
    }


def _coerce_optional_int(raw):
    if raw is None:
        return None
    s = str(raw).strip()
    if s == "":
        return None
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def _coerce_optional_str(raw, max_len=500):
    if raw is None:
        return None
    s = str(raw).strip()
    if s == "":
        return None
    return s[:max_len]


def apply_sheet_update(player, campaign, form):
    """Validate + write a sheet update. Returns (ok: bool, errors: list[str]).

    ``form`` is any mapping-like (request.form works directly). All writes go
    through the rule set whitelist; unknown keys are dropped silently (we do
    NOT raise because the HTML form legitimately submits the CSRF token and
    other non-stat fields).
    """
    errors = []
    if player is None:
        return False, ["Player not found."]

    current = get_or_default_sheet(player, campaign)
    ruleset = _ruleset_for_sheet(campaign, current)

    # Identity fields
    current["name"] = _coerce_optional_str(form.get("name"), max_len=100)
    current["class_name"] = _coerce_optional_str(form.get("class_name"), max_len=100)
    current["species"] = _coerce_optional_str(form.get("species"), max_len=100)
    level = _coerce_optional_int(form.get("level"))
    if level is not None and (level < 0 or level > 40):
        errors.append("Level must be between 0 and 40.")
        level = max(0, min(40, level))
    current["level"] = level
    current["notes"] = _coerce_optional_str(form.get("notes"), max_len=5000)

    # Abilities + defenses + saves all come through the same stat_<id> inputs.
    ability_keys = set(ruleset.ability_keys())
    derived_keys = {d.key for d in ruleset.derived}
    save_keys = set(ruleset.save_keys())

    new_abilities = {}
    new_defenses = {}

    for field_name, raw in form.items():
        if not field_name.startswith("stat_"):
            continue
        token = field_name[len("stat_"):]
        if "_" not in token:
            continue
        kind, _, key = token.partition("_")
        value = _coerce_optional_int(raw)
        if kind == "ability" and key in ability_keys:
            if value is None:
                continue
            clamped = ruleset.clamp_ability(value)
            if clamped is None:
                continue
            new_abilities[key] = clamped
        elif kind == "defense" and key in derived_keys:
            if value is None:
                continue
            # HP / AC / etc.: accept any non-negative int up to a generous cap.
            new_defenses[key] = max(0, min(value, 10000))
        elif kind == "save":
            # Saves are computed; no raw input stored. Ignore.
            continue

    current["abilities"] = new_abilities
    current["defenses"] = new_defenses

    # Save proficiency flags.
    if ruleset.supports_save_proficiency:
        new_save_flags = {}
        for key in save_keys:
            field = f"save_prof_flag_{key}"
            if form.get(field):
                new_save_flags[key] = 1.0
        current["save_prof_flags"] = new_save_flags
    else:
        current["save_prof_flags"] = {}

    # Skill proficiency tiers.
    if ruleset.supports_skill_proficiency:
        new_skill_tiers = {}
        valid_tier_values = set(ruleset.tier_values())
        for sk in ruleset.skills:
            flag_field = f"skill_prof_flag_{sk.key}"
            tier_field = f"skill_prof_tier_{sk.key}"
            if not form.get(flag_field):
                continue
            tier_raw = form.get(tier_field)
            tier_val = _coerce_optional_int(tier_raw)
            if tier_val is None or tier_val not in valid_tier_values:
                # Fall back to the first non-zero tier (e.g. "trained" /
                # "normal") so checking the box without picking a tier still
                # persists proficiency.
                fallback = next(
                    (t.value for t in ruleset.proficiency_tiers if t.value > 0),
                    None,
                )
                if fallback is None:
                    continue
                tier_val = fallback
            new_skill_tiers[sk.key] = tier_val
        current["skill_prof_tiers"] = new_skill_tiers
    else:
        current["skill_prof_tiers"] = {}

    current["schema_version"] = SHEET_SCHEMA_VERSION
    current["system_type"] = ruleset.system_type

    # Persist (upsert).
    if campaign is not None:
        row = PlayerCharacterSheet.query.filter_by(
            player_id=player.id, campaign_id=campaign.id
        ).first()
    else:
        row = (
            PlayerCharacterSheet.query.filter(
                PlayerCharacterSheet.player_id == player.id,
                PlayerCharacterSheet.campaign_id.is_(None),
            ).first()
        )
    if row is None:
        row = PlayerCharacterSheet(
            player_id=player.id,
            campaign_id=campaign.id if campaign is not None else None,
            sheet_json=current,
        )
        db.session.add(row)
    else:
        row.sheet_json = current
        row.updated_at = datetime.utcnow()

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return False, [f"Failed to save character sheet: {exc}"]

    return (len(errors) == 0), errors
