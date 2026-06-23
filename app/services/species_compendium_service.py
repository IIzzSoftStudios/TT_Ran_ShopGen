"""Campaign-scoped species compendium stored in world settings JSON.

The compendium stores GM-authored mechanics and notes for species. Base entries
are seeded as editable shells; no SRD rules text is copied here.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from app.extensions import db
from app.models import CampaignWorldConfig
from app.services.character_creation.dnd5e_species import CORE_SPECIES, CORE_SPECIES_BY_KEY
from app.services.world_generator.defaults import DEFAULT_SPECIES_DISTRIBUTION

_ABILITIES = ("str", "dex", "con", "int", "wis", "cha")
_MAX_NAME_LEN = 60
_MAX_TRAITS = 12


class SpeciesValidationError(ValueError):
    """Raised when species compendium input is invalid."""


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(name or "").strip().lower()).strip("-")
    return slug[:80] or "species"


def _default_species_entry(name: str, percent: float, source: str = "base") -> dict[str, Any]:
    return {
        "key": _slug(name),
        "name": name,
        "source": source,
        "origin_srd_key": None,
        "content_source": None,
        "population_percent": float(percent),
        "ability_modifiers": {ability: 0 for ability in _ABILITIES},
        "flex_ability_bonuses": 0,
        "stat_modifiers": "",
        "traits": [],
        "trait_keys": [],
        "combat_effects": {},
        "notes": "",
        "summary": "",
        "gm_edited": False,
    }


def _species_entry_from_core(raw: dict[str, Any], percent: float) -> dict[str, Any]:
    entry = _default_species_entry(str(raw["name"]), percent, source="base")
    entry.update(
        {
            "key": str(raw["key"]),
            "origin_srd_key": str(raw.get("origin_srd_key") or raw["key"]),
            "content_source": str(raw.get("content_source") or "srd_5_1"),
            "summary": str(raw.get("summary") or ""),
            "ability_modifiers": _clean_ability_modifiers(raw.get("ability_modifiers") or {}),
            "flex_ability_bonuses": int(raw.get("flex_ability_bonuses") or 0),
            "stat_modifiers": str(raw.get("stat_modifiers") or "")[:1000],
            "traits": _clean_traits(raw.get("traits") or []),
            "trait_keys": _clean_trait_keys(raw.get("trait_keys") or []),
            "notes": "",
            "gm_edited": False,
        }
    )
    return entry


def _apply_core_species_fields(entry: dict[str, Any], raw: dict[str, Any]) -> None:
    entry["origin_srd_key"] = str(raw.get("origin_srd_key") or raw["key"])
    entry["content_source"] = str(raw.get("content_source") or "srd_5_1")
    if not str(entry.get("summary") or "").strip():
        entry["summary"] = str(raw.get("summary") or "")
    entry["ability_modifiers"] = _clean_ability_modifiers(raw.get("ability_modifiers") or {})
    entry["flex_ability_bonuses"] = int(raw.get("flex_ability_bonuses") or 0)
    if not str(entry.get("stat_modifiers") or "").strip():
        entry["stat_modifiers"] = str(raw.get("stat_modifiers") or "")[:1000]
    if not entry.get("traits"):
        entry["traits"] = _clean_traits(raw.get("traits") or [])
    if not entry.get("trait_keys"):
        entry["trait_keys"] = _clean_trait_keys(raw.get("trait_keys") or [])
    if entry.get("source") in (None, "default"):
        entry["source"] = "base"


def _config_for_campaign(campaign_id: int) -> CampaignWorldConfig:
    cfg = CampaignWorldConfig.query.filter_by(campaign_id=campaign_id).first()
    if cfg is None:
        cfg = CampaignWorldConfig(
            campaign_id=campaign_id,
            settings_json={},
            schema_version=1,
        )
        db.session.add(cfg)
        db.session.flush()
    if not isinstance(cfg.settings_json, dict):
        cfg.settings_json = {}
    return cfg


def _distribution_entries(settings: dict[str, Any]) -> list[dict[str, Any]]:
    distribution = settings.get("species_distribution")
    if not isinstance(distribution, list) or not distribution:
        return [
            {"name": name, "percent": percent, "source": "default"}
            for name, percent in DEFAULT_SPECIES_DISTRIBUTION
        ]
    return [row for row in distribution if isinstance(row, dict)]


def _ensure_compendium(settings: dict[str, Any]) -> list[dict[str, Any]]:
    compendium = settings.get("species_compendium")
    if not isinstance(compendium, list):
        compendium = []

    by_key: dict[str, dict[str, Any]] = {}
    for raw in compendium:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        key = str(raw.get("key") or _slug(name))
        entry = _default_species_entry(
            name,
            float(raw.get("population_percent") or raw.get("percent") or 0),
            str(raw.get("source") or "custom"),
        )
        entry.update(deepcopy(raw))
        entry["key"] = key
        entry["name"] = name
        entry["ability_modifiers"] = _clean_ability_modifiers(
            entry.get("ability_modifiers") or {}
        )
        entry["flex_ability_bonuses"] = int(entry.get("flex_ability_bonuses") or 0)
        entry["traits"] = _clean_traits(entry.get("traits") or [])
        entry["trait_keys"] = _clean_trait_keys(entry.get("trait_keys") or [])
        entry["gm_edited"] = bool(entry.get("gm_edited"))
        by_key[key] = entry

    percent_by_name = {
        str(row.get("name") or "").strip(): float(row.get("percent") or row.get("population_percent") or 0)
        for row in _distribution_entries(settings)
        if str(row.get("name") or "").strip()
    }

    for raw in CORE_SPECIES:
        key = str(raw["key"])
        percent = percent_by_name.get(str(raw["name"]), 0.0)
        if key not in by_key:
            by_key[key] = _species_entry_from_core(raw, percent)
            continue
        existing = by_key[key]
        existing["population_percent"] = float(
            existing.get("population_percent") if existing.get("population_percent") is not None else percent
        )
        if existing.get("gm_edited"):
            continue
        if existing.get("source") == "custom":
            continue
        _apply_core_species_fields(existing, raw)

    for row in _distribution_entries(settings):
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        key = _slug(name)
        source = "custom" if row.get("source") == "custom" else "base"
        percent = float(row.get("percent") or row.get("population_percent") or 0)
        if key not in by_key:
            core = CORE_SPECIES_BY_KEY.get(key)
            if core is not None:
                by_key[key] = _species_entry_from_core(core, percent)
            else:
                by_key[key] = _default_species_entry(name, percent, source)
        else:
            by_key[key]["population_percent"] = percent
            if by_key[key].get("source") in (None, "default"):
                by_key[key]["source"] = source

    entries = sorted(by_key.values(), key=lambda row: (row.get("source") == "custom", row["name"].lower()))
    settings["species_compendium"] = entries
    return entries


def ensure_species_compendium(campaign_id: int) -> list[dict[str, Any]]:
    from app.services.traits_compendium_service import ensure_traits_compendium

    ensure_traits_compendium(campaign_id)
    cfg = _config_for_campaign(campaign_id)
    settings = cfg.settings_json
    entries = _ensure_compendium(settings)
    cfg.settings_json = settings
    flag_modified(cfg, "settings_json")
    db.session.flush()
    return deepcopy(entries)


def list_species(campaign_id: int) -> list[dict[str, Any]]:
    return ensure_species_compendium(campaign_id)


def get_species_entry(campaign_id: int, key: str) -> dict[str, Any] | None:
    needle = str(key or "").strip().lower()
    for entry in ensure_species_compendium(campaign_id):
        if str(entry.get("key") or "").lower() == needle:
            return deepcopy(entry)
    return None


def city_species_population(
    campaign_id: int, city_id: int, total_population: int
) -> list[dict[str, Any]]:
    """Return editable species population rows for a city.

    City-specific rows win. If none exist, derive counts from the campaign
    species compendium percentages and the city's current total population.
    """
    cfg = _config_for_campaign(campaign_id)
    settings = cfg.settings_json
    city_map = settings.get("city_species_population")
    if isinstance(city_map, dict):
        existing = city_map.get(str(city_id))
        if isinstance(existing, list):
            rows = []
            for row in existing:
                if not isinstance(row, dict):
                    continue
                name = str(row.get("name") or "").strip()
                if not name:
                    continue
                try:
                    population = int(row.get("population") or 0)
                except (TypeError, ValueError):
                    population = 0
                rows.append(
                    {
                        "key": str(row.get("key") or _slug(name)),
                        "name": name,
                        "population": max(0, population),
                        "percent": _percent(max(0, population), total_population),
                    }
                )
            if rows:
                return rows

    compendium_by_key = {entry["key"]: entry for entry in ensure_species_compendium(campaign_id)}
    ordered_entries = []
    for row in _distribution_entries(settings):
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        key = _slug(name)
        ordered_entries.append(compendium_by_key.get(key) or _default_species_entry(name, row.get("percent") or 0))
    if not ordered_entries:
        ordered_entries = list(compendium_by_key.values())

    rows = []
    for entry in ordered_entries:
        percent = float(entry.get("population_percent") or 0)
        rows.append(
            {
                "key": entry["key"],
                "name": entry["name"],
                "population": int(round(max(0, total_population) * percent / 100.0)),
                "percent": round(percent, 3),
            }
        )
    return rows


def custom_species_needing_builder(campaign_id: int) -> list[dict[str, Any]]:
    return [
        entry
        for entry in ensure_species_compendium(campaign_id)
        if entry.get("source") == "custom"
    ]


def settings_has_custom_species(settings: dict[str, Any]) -> bool:
    for row in _distribution_entries(settings):
        if row.get("source") == "custom" and float(row.get("percent") or 0) > 0:
            return True
    return False


def _percent(population: int, total_population: int) -> float:
    if total_population <= 0:
        return 0.0
    return round((population / total_population) * 100.0, 3)


def _clean_ability_modifiers(raw: dict[str, Any]) -> dict[str, int]:
    clean = {}
    for ability in _ABILITIES:
        try:
            value = int(raw.get(ability, 0))
        except (TypeError, ValueError):
            raise SpeciesValidationError(f"{ability.upper()} modifier must be an integer.")
        if not (-10 <= value <= 10):
            raise SpeciesValidationError(f"{ability.upper()} modifier must be between -10 and 10.")
        clean[ability] = value
    return clean


def _clean_traits(raw: Any) -> list[dict[str, str]]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        rows = []
        for index, line in enumerate(raw.splitlines()):
            text = line.strip()
            if text:
                rows.append({"name": f"Trait {index + 1}", "description": text[:500]})
        return rows[:_MAX_TRAITS]
    if not isinstance(raw, list) or len(raw) > _MAX_TRAITS:
        raise SpeciesValidationError("traits must be a list of at most 12 entries.")
    clean = []
    for index, trait in enumerate(raw):
        if not isinstance(trait, dict):
            raise SpeciesValidationError("Each trait must be an object.")
        name = str(trait.get("name") or f"Trait {index + 1}").strip()[:80]
        description = str(trait.get("description") or "").strip()[:500]
        if name or description:
            clean.append({"name": name, "description": description})
    return clean


def _clean_trait_keys(raw: Any) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        keys = [part.strip().lower() for part in raw.split(",") if part.strip()]
    elif isinstance(raw, list):
        keys = [str(part or "").strip().lower() for part in raw if str(part or "").strip()]
    else:
        raise SpeciesValidationError("trait_keys must be a list or comma-separated string.")
    if len(keys) > 24:
        raise SpeciesValidationError("At most 24 trait keys allowed per species.")
    return keys


def _clean_species_patch(raw: dict[str, Any]) -> dict[str, Any]:
    name = str(raw.get("name") or "").strip()
    if not name or len(name) > _MAX_NAME_LEN:
        raise SpeciesValidationError("Species name must be 1-60 characters.")
    try:
        population_percent = float(raw.get("population_percent", 0))
    except (TypeError, ValueError):
        raise SpeciesValidationError("Population percent must be a number.")
    if not (0 <= population_percent <= 100):
        raise SpeciesValidationError("Population percent must be between 0 and 100.")
    clean = {
        "name": name,
        "population_percent": round(population_percent, 3),
        "ability_modifiers": _clean_ability_modifiers(raw.get("ability_modifiers") or {}),
        "flex_ability_bonuses": int(raw.get("flex_ability_bonuses") or 0),
        "stat_modifiers": str(raw.get("stat_modifiers") or "").strip()[:1000],
        "traits": _clean_traits(raw.get("traits") or []),
        "trait_keys": _clean_trait_keys(raw.get("trait_keys") or []),
        "notes": str(raw.get("notes") or "").strip()[:1000],
        "gm_edited": True,
    }
    if "summary" in raw:
        clean["summary"] = str(raw.get("summary") or "").strip()[:500]
    return clean


def update_species(campaign_id: int, key: str, raw: dict[str, Any]) -> dict[str, Any]:
    cfg = _config_for_campaign(campaign_id)
    settings = cfg.settings_json
    entries = _ensure_compendium(settings)
    clean = _clean_species_patch(raw)
    for entry in entries:
        if entry.get("key") == key:
            entry.update(clean)
            cfg.settings_json = settings
            flag_modified(cfg, "settings_json")
            db.session.flush()
            return deepcopy(entry)
    raise SpeciesValidationError("Species entry not found.")


def create_species(campaign_id: int, raw: dict[str, Any]) -> dict[str, Any]:
    cfg = _config_for_campaign(campaign_id)
    settings = cfg.settings_json
    entries = _ensure_compendium(settings)
    clean = _clean_species_patch(raw)
    existing_keys = {entry["key"] for entry in entries}
    base_key = _slug(clean["name"])
    key = base_key
    suffix = 2
    while key in existing_keys:
        key = f"{base_key}-{suffix}"
        suffix += 1
    entry = {
        "key": key,
        "source": "custom",
        "gm_edited": True,
        **clean,
    }
    entries.append(entry)
    distribution = settings.get("species_distribution")
    if not isinstance(distribution, list):
        distribution = _distribution_entries(settings)
    distribution.append(
        {
            "name": clean["name"],
            "percent": clean["population_percent"],
            "source": "custom",
        }
    )
    settings["species_distribution"] = distribution
    settings["species_compendium"] = sorted(
        entries,
        key=lambda row: (row.get("source") == "custom", row["name"].lower()),
    )
    cfg.settings_json = settings
    flag_modified(cfg, "settings_json")
    db.session.flush()
    return deepcopy(entry)


def update_city_species_population(
    campaign_id: int, city_id: int, raw_rows: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int]:
    cfg = _config_for_campaign(campaign_id)
    settings = cfg.settings_json
    known = {entry["key"]: entry["name"] for entry in ensure_species_compendium(campaign_id)}
    rows = []
    for row in raw_rows:
        key = str(row.get("key") or "").strip()
        name = str(row.get("name") or known.get(key) or "").strip()
        if not key:
            key = _slug(name)
        if not name:
            raise SpeciesValidationError("Species name is required.")
        try:
            population = int(row.get("population") or 0)
        except (TypeError, ValueError):
            raise SpeciesValidationError(f"{name} population must be an integer.")
        if population < 0:
            raise SpeciesValidationError(f"{name} population cannot be negative.")
        rows.append({"key": key, "name": name, "population": population})

    total = sum(row["population"] for row in rows)
    clean_rows = [
        {
            **row,
            "percent": _percent(row["population"], total),
        }
        for row in rows
    ]
    city_map = settings.get("city_species_population")
    if not isinstance(city_map, dict):
        city_map = {}
    city_map[str(city_id)] = clean_rows
    settings["city_species_population"] = city_map
    cfg.settings_json = settings
    flag_modified(cfg, "settings_json")
    db.session.flush()
    return deepcopy(clean_rows), total
