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
        "population_percent": float(percent),
        "ability_modifiers": {ability: 0 for ability in _ABILITIES},
        "stat_modifiers": "",
        "traits": [],
        "notes": "",
    }


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
        entry["traits"] = _clean_traits(entry.get("traits") or [])
        by_key[key] = entry

    for row in _distribution_entries(settings):
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        key = _slug(name)
        source = "custom" if row.get("source") == "custom" else "base"
        percent = float(row.get("percent") or row.get("population_percent") or 0)
        if key not in by_key:
            by_key[key] = _default_species_entry(name, percent, source)
        else:
            by_key[key]["population_percent"] = percent
            if by_key[key].get("source") in (None, "default"):
                by_key[key]["source"] = source

    entries = sorted(by_key.values(), key=lambda row: (row.get("source") == "custom", row["name"].lower()))
    settings["species_compendium"] = entries
    return entries


def ensure_species_compendium(campaign_id: int) -> list[dict[str, Any]]:
    cfg = _config_for_campaign(campaign_id)
    settings = cfg.settings_json
    entries = _ensure_compendium(settings)
    cfg.settings_json = settings
    flag_modified(cfg, "settings_json")
    db.session.flush()
    return deepcopy(entries)


def list_species(campaign_id: int) -> list[dict[str, Any]]:
    return ensure_species_compendium(campaign_id)


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
    return {
        "name": name,
        "population_percent": round(population_percent, 3),
        "ability_modifiers": _clean_ability_modifiers(raw.get("ability_modifiers") or {}),
        "stat_modifiers": str(raw.get("stat_modifiers") or "").strip()[:1000],
        "traits": _clean_traits(raw.get("traits") or []),
        "notes": str(raw.get("notes") or "").strip()[:1000],
    }


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
