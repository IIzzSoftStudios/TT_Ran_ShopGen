"""Axis-position + government aware naming for cities, shops, and items.

Phase 1 scope:
- 8 naming bands keyed off axis position (see
  `defaults.AXIS_POSITION_TO_BAND`).
- `(band, government_type)` cross-matrix of vocabulary (8 x 5 = 40
  entries).
- `city_name`, `shop_name`, `item_name` deterministic given an RNG.
- In-memory collision guard: duplicates are re-rolled once, then
  Roman-numeral suffixed.
- Cursed items get a baseline " (cursed)" suffix (Phase 2 expands this).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from app.services.world_generator.defaults import AXIS_POSITION_TO_BAND


# -----------------------------------------------------------------------------
# Vocabulary -- (band, government) -> {city_prefixes, city_suffixes, ...}
# -----------------------------------------------------------------------------
# Vocabulary is intentionally compact. Quantity of entries per bucket > variety
# because determinism + `rng.choice` makes even short lists feel distinct.
_CITY_BAND_POOLS: Dict[str, Dict[str, List[str]]] = {
    "god_magic": {
        "prefixes": ["Aether", "Primord", "Eterna", "Celesti", "Sunspire"],
        "suffixes": ["-reach", "-light", "-vault", "-spire", "-haven"],
    },
    "high_magic": {
        "prefixes": ["Myth", "Arcan", "Rune", "Sorcer", "Elari"],
        "suffixes": ["-mere", "-hallow", "-weave", "-cairn", "-thorn"],
    },
    "low_magic": {
        "prefixes": ["Dusk", "Fadow", "Whisper", "Old", "Willow"],
        "suffixes": ["-fell", "-dale", "-march", "-brook", "-hold"],
    },
    "medieval": {
        "prefixes": ["Winter", "River", "Oak", "King's", "Stone"],
        "suffixes": ["-fell", "-run", "-heart", "-landing", "-keep"],
    },
    "renaissance": {
        "prefixes": ["Monte", "Port", "Floren", "Vento", "Ducan"],
        "suffixes": ["-vero", "-silica", "-tine", "-porto", "-doria"],
    },
    "industrial": {
        "prefixes": ["Iron", "Gear", "Smoke", "Copper", "Rail"],
        "suffixes": ["-side", "-burg", "-valley", "-port", "-ton"],
    },
    "modern": {
        "prefixes": ["New", "Silver", "West", "Central", "North"],
        "suffixes": ["-Heights", "-Creek", "-field", "-Plaza", "-District"],
    },
    "post_apoc": {
        "prefixes": ["Scrap", "Dust", "Rust", "Last", "Waste"],
        "suffixes": ["-town", "-hope", "-halt", "-light", "-end"],
    },
}


_GOVT_CITY_FLAVOR: Dict[str, List[str]] = {
    "Feudal":     ["", "King's ", "Baron's ", "Lord's "],
    "Corporate":  ["", "Sector ", "Hub ", "District "],
    "Anarchy":    ["", "No-Man's ", "Dead ", "Slayer's "],
    "Theocratic": ["", "Saint ", "Abbey-on-", "Hallowed "],
    "Tribal":     ["", "Great-", "Elder-", "Three-"],
}


_SHOP_TYPE_BY_BAND: Dict[str, List[str]] = {
    "god_magic":   ["Reliquary", "Sanctum", "Altar", "Shrine"],
    "high_magic":  ["Apothecary", "Rune-Scribe", "Enchanter", "Spellwright"],
    "low_magic":   ["General Store", "Smithy", "Herbalist", "Trading Post"],
    "medieval":    ["Smithy", "Tavern", "General Store", "Fletcher", "Armorer"],
    "renaissance": ["Emporium", "Artisan's Guild", "Compass Works", "Foundry"],
    "industrial":  ["Foundry", "Rail Supply", "Steel Works", "Machinists"],
    "modern":      ["Supply Depot", "Tactical Outfitter", "Logistics", "Armory"],
    "post_apoc":   ["Junk Heap", "Scrap Exchange", "Bullet & Bone", "Salvage"],
}


_SHOP_NAME_PREFIXES_BY_GOVT: Dict[str, List[str]] = {
    "Feudal":     ["The King's", "Baron's", "The Royal", "Guild-Master's"],
    "Corporate":  ["Standard", "Prime", "Central", "Unified"],
    "Anarchy":    ["The Rusty", "Dead", "Last", "Slayer's"],
    "Theocratic": ["The Blessed", "Saint's", "The Hallowed", "Vesper's"],
    "Tribal":     ["Elder", "The Great", "Three-Rivers", "Whispering"],
}


_ITEM_ADJECTIVES_BY_BAND: Dict[str, List[str]] = {
    "god_magic":   ["Radiant", "Primordial", "Celestial", "Divine"],
    "high_magic":  ["Ember-Etched", "Runic", "Sorcerous", "Mythic"],
    "low_magic":   ["Dormant", "Fading", "Whispering", "Residual"],
    "medieval":    ["Sturdy", "Well-Worn", "Plain", "Honed"],
    "renaissance": ["Gilded", "Filigreed", "Artisan-Wrought", "Polished"],
    "industrial":  ["Riveted", "Forged", "Standard-Issue", "Mass-Produced"],
    "modern":      ["Tactical", "Precision", "Kevlar-Lined", "Composite"],
    "post_apoc":   ["Rusted", "Scavenged", "Jury-Rigged", "Salvaged"],
}


_ITEM_NOUN_BY_CATEGORY: Dict[str, List[str]] = {
    "Melee":      ["Blade", "Maul", "Cleaver", "Axe", "Spear", "Dagger"],
    "Ranged":     ["Bow", "Crossbow", "Rifle", "Pistol", "Sling"],
    "Armor":      ["Plate", "Mail", "Vest", "Hauberk", "Cuirass"],
    "General":    ["Rope", "Rations", "Torch", "Bedroll", "Lantern", "Pack"],
    "Consumable": ["Elixir", "Tonic", "Draught", "Poultice", "Rations"],
}


# -----------------------------------------------------------------------------
# Public helpers
# -----------------------------------------------------------------------------
def axis_to_band(axis_position: int) -> str:
    """Clamp axis_position to [0..10] then look up the band name."""
    clamped = max(0, min(10, int(axis_position)))
    return AXIS_POSITION_TO_BAND[clamped]


def _with_collision_guard(
    rng, candidate: str, used: Set[str]
) -> str:
    """Return a name that is not already in `used`. Tries a reroll tag,
    then falls back to Roman-numeral suffixes. Always adds to `used`."""
    if candidate not in used:
        used.add(candidate)
        return candidate

    # First fallback: append a short token from the RNG.
    salt = rng.randint(2, 9)
    alt = f"{candidate} {salt}"
    if alt not in used:
        used.add(alt)
        return alt

    # Final fallback: Roman numerals.
    roman = ["II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]
    for suffix in roman:
        tagged = f"{candidate} {suffix}"
        if tagged not in used:
            used.add(tagged)
            return tagged

    # Unreachable in practice; always return something unique.
    fallback = f"{candidate} #{rng.randint(100, 9999)}"
    used.add(fallback)
    return fallback


def city_name(
    rng,
    axis_position: int,
    government_type: str,
    used: Set[str],
) -> str:
    band = axis_to_band(axis_position)
    pool = _CITY_BAND_POOLS.get(band, _CITY_BAND_POOLS["medieval"])
    prefix = rng.choice(pool["prefixes"])
    suffix = rng.choice(pool["suffixes"])
    govt_pref = rng.choice(_GOVT_CITY_FLAVOR.get(government_type, [""]))
    candidate = f"{govt_pref}{prefix}{suffix}".strip()
    return _with_collision_guard(rng, candidate, used)


def shop_type_for_axis(rng, axis_position: int) -> str:
    band = axis_to_band(axis_position)
    return rng.choice(_SHOP_TYPE_BY_BAND.get(band, _SHOP_TYPE_BY_BAND["medieval"]))


def shop_name(
    rng,
    axis_position: int,
    government_type: str,
    shop_type: str,
    used: Set[str],
) -> str:
    prefix = rng.choice(
        _SHOP_NAME_PREFIXES_BY_GOVT.get(government_type, ["The"])
    )
    candidate = f"{prefix} {shop_type}"
    return _with_collision_guard(rng, candidate, used)


def item_name(
    rng,
    axis_position: int,
    category: str,
    rarity: str,
    is_cursed: bool,
    used: Set[str],
) -> str:
    band = axis_to_band(axis_position)
    adjective = rng.choice(
        _ITEM_ADJECTIVES_BY_BAND.get(band, _ITEM_ADJECTIVES_BY_BAND["medieval"])
    )
    noun = rng.choice(
        _ITEM_NOUN_BY_CATEGORY.get(category, _ITEM_NOUN_BY_CATEGORY["General"])
    )

    if rarity == "Legendary":
        candidate = f"{adjective} {noun} of the {band.replace('_', ' ').title()}"
    elif rarity == "Rare":
        candidate = f"{adjective} {noun}"
    else:
        candidate = f"{adjective} {noun}"

    if is_cursed:
        candidate = f"{candidate} (cursed)"

    return _with_collision_guard(rng, candidate, used)
