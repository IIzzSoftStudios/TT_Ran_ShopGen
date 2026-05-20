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

from typing import Dict, List, Set

from app.services.world_generator.defaults import AXIS_POSITION_TO_BAND

_MAX_GENERATED_NAME_LEN = 100


# -----------------------------------------------------------------------------
# Vocabulary -- (band, government) -> {city_prefixes, city_suffixes, ...}
# -----------------------------------------------------------------------------
_CITY_BAND_POOLS: Dict[str, Dict[str, List[str]]] = {
    "god_magic": {
        "prefixes": [
            "Aether", "Primord", "Eterna", "Celesti", "Sunspire", "Astral", "Aura",
            "Zenith", "Lumini", "Solar", "Stellar", "Zephyr", "Empyrean", "Chronos",
            "Genesis", "Aeon", "Seraph", "Nexus", "Umbral", "Hyperion", "Elysium",
            "Apex", "Solstice", "Equinox", "Nadir", "Dawn", "Vesper", "Halcyon",
            "Sancti", "Cosmo", "Ignis", "Glimmer", "Prism", "Aethel", "Sovereign",
            "Crest", "Orion", "Nova", "Polaris", "Summit", "Vortex",
        ],
        "suffixes": [
            "-reach", "-light", "-vault", "-spire", "-haven", "-cradle", "-throne",
            "-apex", "-crown", "-sanctum", "-domain", "-fount", "-pillar", "-canopy",
            "-veil", "-shrine", "-ascent", "-crest", "-obelisk", "-altar", "-temple",
            "-nexus", "-vortex", "-firmament", "-bastion", "-citadel", "-fortress",
            "-sanctuary", "-refuge", "-oasis", "-eden", "-source", "-well", "-origin",
            "-gate", "-glen", "-court", "-hall", "-matrix",
        ],
    },
    "high_magic": {
        "prefixes": [
            "Myth", "Arcan", "Rune", "Sorcer", "Elari", "Glyph", "Mana", "Spell",
            "Hex", "Charm", "Enchant", "Wizard", "Mage", "Sage", "Alche", "Mystic",
            "Cinder", "Frost", "Pyre", "Aero", "Hydro", "Geo", "Chrono", "Phanto",
            "Shadow", "Shimmer", "Crystal", "Prism", "Mirage", "Illusion", "Specter",
            "Wraith", "Phantom", "Spirit", "Faerie", "Sprite", "Nymph", "Dryad",
            "Sylph", "Vellum", "Scroll", "Ley", "Weave", "Amulet", "Talisman",
        ],
        "suffixes": [
            "-mere", "-hallow", "-weave", "-cairn", "-thorn", "-spire", "-tower",
            "-keep", "-clave", "-sanctum", "-grove", "-wood", "-forest", "-glade",
            "-vale", "-valley", "-peak", "-mount", "-hill", "-ridge", "-cliff",
            "-crag", "-rock", "-stone", "-cave", "-cavern", "-grotto", "-den",
            "-lair", "-hollow", "-well", "-spring", "-fountain", "-pool", "-pond",
            "-lake", "-run", "-flow", "-tide", "-surge",
        ],
    },
    "low_magic": {
        "prefixes": [
            "Dusk", "Fadow", "Whisper", "Old", "Willow", "Bramble", "Briar", "Thistle",
            "Nettle", "Moss", "Fern", "Lichen", "Ivy", "Vine", "Root", "Stump", "Log",
            "Bark", "Twig", "Branch", "Leaf", "Mud", "Clay", "Silt", "Sand", "Dust",
            "Ash", "Soot", "Coal", "Char", "Peat", "Bog", "Fen", "Mire", "Marsh",
            "Swamp", "Heath", "Moor", "Downs", "Wold", "Weald", "Chase", "Thicket",
        ],
        "suffixes": [
            "-fell", "-dale", "-march", "-brook", "-hold", "-croft", "-thwaite", "-toft",
            "-by", "-thorp", "-ham", "-ton", "-bury", "-borough", "-burgh", "-stead",
            "-stow", "-worth", "-garth", "-hay", "-end", "-side", "-head", "-foot",
            "-top", "-bottom", "-edge", "-verge", "-bank", "-shore", "-strand", "-coast",
            "-cliff", "-crag", "-tor", "-low", "-barrow", "-mound", "-ridge", "-dene",
            "-comb", "-glen",
        ],
    },
    "medieval": {
        "prefixes": [
            "Winter", "River", "Oak", "King's", "Stone", "Gold", "Silver", "Iron",
            "Steel", "Bronze", "Copper", "Brass", "Wolf", "Bear", "Boar", "Deer",
            "Stag", "Hart", "Fox", "Badger", "Otter", "Beaver", "Eagle", "Hawk",
            "Falcon", "Raven", "Crow", "Owl", "Swan", "Heron", "Bull", "Ox", "Sheep",
            "Ram", "Goat", "Horse", "Hound", "Barley", "Wheat", "Rye", "Mill",
            "Bridge",
        ],
        "suffixes": [
            "-fell", "-run", "-heart", "-landing", "-keep", "-bridge", "-ford",
            "-crossing", "-way", "-path", "-road", "-gate", "-wall", "-ditch", "-moat",
            "-dyke", "-bank", "-mound", "-hill", "-mount", "-peak", "-crest", "-ridge",
            "-pass", "-gap", "-valley", "-glen", "-dale", "-vale", "-wood", "-forest",
            "-grove", "-orchard", "-field", "-meadow", "-lea", "-pasture", "-green",
            "-common", "-park", "-chase",
        ],
    },
    "renaissance": {
        "prefixes": [
            "Monte", "Port", "Floren", "Vento", "Ducan", "Bella", "Vista", "Buona",
            "Sera", "Alba", "Rosa", "Bianca", "Nera", "Verde", "Oro", "Argento",
            "Pietra", "Rocca", "Castel", "Villa", "Palazzo", "Corte", "Piazza", "Corso",
            "Via", "Borgo", "Paese", "Torre", "Ponte", "Porto", "Baia", "Golfo", "Mare",
            "Isola", "Costa", "Riva", "Spiaggia", "Valle", "Pianura", "Navi", "Santi",
        ],
        "suffixes": [
            "-vero", "-silica", "-tine", "-porto", "-doria", "-bello", "-vista", "-doro",
            "-gento", "-marino", "-fino", "-venere", "-roma", "-milano", "-torino",
            "-genova", "-venezia", "-bologna", "-firenze", "-pisa", "-siena", "-lucca",
            "-livorno", "-arezzo", "-perugia", "-orvieto", "-viterbo", "-tivoli", "-ostia",
            "-anzio", "-nettuno", "-gaeta", "-napoli", "-salerno", "-foggia", "-bari",
            "-taranto", "-lecce", "-brindisi", "-parma", "-modena",
        ],
    },
    "industrial": {
        "prefixes": [
            "Iron", "Gear", "Smoke", "Copper", "Rail", "Steel", "Coal", "Coke", "Steam",
            "Boiler", "Engine", "Piston", "Valve", "Gauge", "Pump", "Turbine", "Mill",
            "Factory", "Works", "Plant", "Foundry", "Forge", "Smelter", "Furnace", "Kiln",
            "Oven", "Stove", "Hearth", "Chimney", "Stack", "Vent", "Pipe", "Tube", "Wire",
            "Cable", "Chain", "Bolt", "Nut", "Screw", "Rivet", "Weld", "Casting", "Machin",
        ],
        "suffixes": [
            "-side", "-burg", "-valley", "-port", "-ton", "-ville", "-town", "-city",
            "-station", "-junction", "-terminus", "-depot", "-yard", "-wharf", "-pier",
            "-dock", "-harbor", "-basin", "-canal", "-lock", "-viaduct", "-bridge",
            "-tunnel", "-cut", "-trench", "-pit", "-mine", "-quarry", "-shaft", "-drift",
            "-slope", "-seam", "-vein", "-lode", "-deposit", "-field", "-district", "-zone",
            "-sector", "-ward", "-quarter",
        ],
    },
    "modern": {
        "prefixes": [
            "New", "Silver", "West", "Central", "North", "South", "East", "Metro", "Grand",
            "Great", "Little", "Upper", "Lower", "High", "Low", "Mid", "Inner", "Outer",
            "Urban", "Suburban", "Rural", "Local", "Regional", "Federal", "State", "County",
            "City", "Town", "Bay", "Beach", "Coast", "Harbor", "Port", "Lake", "River",
            "Valley", "Ridge", "Hill", "Park", "Plaza", "Center", "Square", "Market",
        ],
        "suffixes": [
            "-Heights", "-Creek", "-field", "-Plaza", "-District", "-Park", "-Center",
            "-Square", "-Terrace", "-Gardens", "-Estates", "-Manor", "-Crest", "-View",
            "-Ridge", "-Valley", "-Glen", "-Dale", "-Grove", "-Wood", "-Forest", "-Hills",
            "-Downs", "-Meadows", "-Fields", "-Commons", "-Greens", "-Courts", "-Yards",
            "-Lanes", "-Ways", "-Drives", "-Avenues", "-Streets", "-Roads", "-Boulevards",
            "-Highways", "-Freeways", "-Expressways", "-Parkways",
        ],
    },
    "post_apoc": {
        "prefixes": [
            "Scrap", "Dust", "Rust", "Last", "Waste", "Bone", "Ash", "Char", "Bleak",
            "Grim", "Dark", "Dead", "Dread", "Gloom", "Shadow", "Night", "Void", "Null",
            "Zero", "End", "Final", "Terminal", "Omega", "Alpha", "First", "Lone", "Solo",
            "One", "Single", "Twin", "Broken", "Fractured", "Shattered", "Cracked", "Torn",
            "Ripped", "Mangled", "Crushed", "Smashed", "Beaten", "Barren", "Toxic", "Cinder",
        ],
        "suffixes": [
            "-town", "-hope", "-halt", "-light", "-end", "-ruin", "-wreck", "-scrap",
            "-dust", "-rust", "-waste", "-bone", "-ash", "-char", "-pit", "-hole", "-crater",
            "-chasm", "-rift", "-abyss", "-void", "-trench", "-ditch", "-moat", "-wall",
            "-fence", "-gate", "-post", "-camp", "-base", "-fort", "-outpost", "-station",
            "-stop", "-site", "-zone", "-sector", "-ward", "-quarter", "-block", "-row",
        ],
    },
}


_GOVT_CITY_FLAVOR: Dict[str, List[str]] = {
    "Feudal": [
        "", "King's ", "Baron's ", "Lord's ", "Duke's ", "Earl's ", "Count's ",
        "Prince's ", "Queen's ", "Knight's ", "Squire's ", "Vassal's ", "Liege's ",
        "Overlord's ", "Monarch's ", "Emperor's ", "Regent's ", "Palatine ", "Thane's ",
        "Jarl's ", "Castellan's ", "Seneschal's ", "Steward's ", "Marshal's ", "Sheriff's ",
        "Mayor's ", "Burgomaster's ", "Guild's ", "Master's ", "Warden's ", "Protector's ",
        "Governor's ", "Viceroy's ", "Khan's ", "Emir's ",
    ],
    "Corporate": [
        "", "Sector ", "Hub ", "District ", "Zone ", "Division ", "Branch ",
        "Department ", "Office ", "Bureau ", "Agency ", "Board ", "Council ",
        "Executive ", "Management ", "Headquarters ", "HQ ", "Terminal ", "Depot ",
        "Station ", "Facility ", "Plant ", "Factory ", "Works ", "Mill ", "Foundry ",
        "Refinery ", "Laboratory ", "Center ", "Complex ", "Campus ", "Park ", "Plaza ",
        "Warehouse ",
    ],
    "Anarchy": [
        "", "No-Man's ", "Dead ", "Slayer's ", "Rogue's ", "Outlaw's ", "Bandit's ",
        "Thief's ", "Pirate's ", "Scavenger's ", "Vagrant's ", "Gutter ", "Slum ",
        "Shanty ", "Row ", "Alley ", "Yard ", "Pit ", "Hole ", "Sink ", "Den ", "Lair ",
        "Burrow ", "Nest ", "Hive ", "Pack ", "Mob ", "Gang ", "Horde ", "Faction ",
        "Sect ", "Cartel ",
    ],
    "Theocratic": [
        "", "Saint ", "Abbey-on-", "Hallowed ", "Holy ", "Sacred ", "Divine ", "Blessed ",
        "Venerable ", "Pious ", "Devout ", "Religious ", "Clerical ", "Priestly ",
        "Pontifical ", "Papal ", "Patriarchal ", "Episcopal ", "Diocesan ", "Parish ",
        "Cathedral ", "Basilica ", "Church ", "Chapel ", "Shrine ", "Sanctuary ",
        "Monastery ", "Convent ", "Priory ", "Friary ", "Hermitage ", "Cloister ",
        "Abbot's ", "Rector's ", "Pastor's ",
    ],
    "Tribal": [
        "", "Great-", "Elder-", "Three-", "Chief's ", "Sagamore's ", "Sachem's ",
        "Khan's ", "Chieftain's ", "Headman's ", "Elder's ", "Father's ", "Mother's ",
        "Ancestor's ", "Totem ", "Sacred ", "Holy ", "Great ", "Grand ", "High ", "First ",
        "Blood-", "Bone-", "Storm-", "Sun-", "Moon-", "Wild-", "Stone-", "Fang-",
    ],
}


_SHOP_TYPE_BY_BAND: Dict[str, List[str]] = {
    "god_magic": [
        "Reliquary", "Sanctum", "Altar", "Shrine", "Temple", "Chantry", "Sacristy",
        "Vestry", "Oracle Post", "Lightward Trading", "Sacred Vault", "Dawn Chapel",
    ],
    "high_magic": [
        "Apothecary", "Rune-Scribe", "Enchanter", "Spellwright", "Thaumaturgist",
        "Alchemist", "Arcane Exchange", "Scroll Vault", "Focus Foundry", "Grimoire Library",
        "Scriptorium", "Ley-Ward Shop",
    ],
    "low_magic": [
        "General Store", "Smithy", "Herbalist", "Trading Post", "Chandler", "Cooper",
        "Wheelwright", "Carpenter", "Weaver", "Tanner", "Shoemaker", "Hedge Apothecary",
    ],
    "medieval": [
        "Smithy", "Tavern", "General Store", "Fletcher", "Armorer", "Bowyer", "Bladesmith",
        "Blacksmith", "Locksmith", "Farrier", "Tailor", "Mercer", "Inn", "Alehouse",
    ],
    "renaissance": [
        "Emporium", "Artisan's Guild", "Compass Works", "Foundry", "Atelier", "Workshop",
        "Observatory", "Bookshop", "Printing House", "Clockmaker", "Glassworks", "Cartographer",
    ],
    "industrial": [
        "Foundry", "Rail Supply", "Steel Works", "Machinists", "Mill", "Factory", "Plant",
        "Machine Shop", "Boiler House", "Pump House", "Warehouse", "Gasworks",
    ],
    "modern": [
        "Supply Depot", "Tactical Outfitter", "Logistics", "Armory", "Hardware Depot",
        "Surplus Store", "Pharmacy", "Automotive Hub", "Electronics Hub", "Wholesaler",
        "Showroom", "Distribution Complex",
    ],
    "post_apoc": [
        "Junk Heap", "Scrap Exchange", "Bullet & Bone", "Salvage", "Trade Post",
        "Barter Town", "Scavenger Den", "Rust Market", "Fuel Barter", "Scrap Yard",
        "Outlaw Bazaar", "Casing Press",
    ],
}


_SHOP_NAME_PREFIXES_BY_GOVT: Dict[str, List[str]] = {
    "Feudal": [
        "The King's", "Baron's", "The Royal", "Guild-Master's", "Duke's", "Earl's",
        "The Count's", "The Prince's", "Queen's", "Knight's", "Liege's", "Monarch's",
        "Emperor's", "Regent's", "Thane's", "Jarl's", "Castellan's", "Steward's",
        "Marshal's", "Constable's", "Sheriff's", "Mayor's", "The Guild's", "Master's",
        "Warden's", "Protector's", "Governor's", "Viceroy's",
    ],
    "Corporate": [
        "Standard", "Prime", "Central", "Unified", "Global", "International", "National",
        "Federal", "State", "Metro", "Grand", "Apex", "Consolidated", "Core", "Nexus",
        "Horizon", "Summit", "Vertex", "Executive", "Official", "Licensed", "Alpha",
        "Beta", "Gamma", "Delta", "Omega",
    ],
    "Anarchy": [
        "The Rusty", "Dead", "Last", "Slayer's", "Rogue's", "Outlaw's", "Bandit's",
        "Thief's", "Pirate's", "Scavenger's", "Gutter", "Slum", "Shanty", "Skid", "Row",
        "Alley", "Yard", "Pit", "Hole", "Den", "Lair", "Burrow", "Nest", "Hive", "Pack",
        "Mob", "Gang", "Horde", "Faction", "Black Market",
    ],
    "Theocratic": [
        "The Blessed", "Saint's", "The Hallowed", "Vesper's", "Holy", "Sacred", "Divine",
        "Venerable", "Pious", "Devout", "Clerical", "Priestly", "Pontifical", "Papal",
        "Episcopal", "Diocesan", "Parish", "Cathedral", "Basilica", "Church", "Chapel",
        "Shrine", "Sanctuary", "Abbot's", "Prior's", "Rector's", "Pastor's", "Monastic",
        "Canonical", "Orthodox", "Grace",
    ],
    "Tribal": [
        "Elder", "The Great", "Three-Rivers", "Whispering", "Chief's", "Sagamore's",
        "Sachem's", "Khan's", "Chieftain's", "Headman's", "Ancestor's", "Totem", "Sacred",
        "Holy", "Grand", "High", "First", "Blood", "Bone", "Fang", "Claw", "Iron-Oak",
        "Red-Earth", "Stone-River", "Wild-Run",
    ],
}


_ITEM_ADJECTIVES_BY_BAND: Dict[str, List[str]] = {
    "god_magic": [
        "Radiant", "Primordial", "Celestial", "Divine", "Astral", "Cosmic", "Empyrean",
        "Stellar", "Solar", "Lunar", "Eternal", "Supreme", "Sovereign", "Holy", "Sacred",
        "Immortal", "Ethereal", "Seraphic", "Angelic", "Blessed", "Hallowed", "Sanctified",
        "Consecrated", "Anointed", "Exalted", "Glorious", "Resplendent", "Undying",
        "Timeless", "Pure", "True", "Noble", "Luminous", "Brilliant", "Sacred-Forged",
    ],
    "high_magic": [
        "Ember-Etched", "Runic", "Sorcerous", "Mythic", "Arcane", "Mystical", "Magical",
        "Alchemical", "Hermetic", "Esoteric", "Occult", "Enchanted", "Charmed", "Hexed",
        "Phantasmal", "Spectral", "Shadowy", "Luminous", "Brilliant", "Gleaming", "Resonating",
        "Infused", "Attuned", "Ley-Bound", "Weave-Spun", "Volatile", "Stable", "Imbued",
        "Conjured", "Manifested", "Prismatic", "Glittering", "Shimmering", "Spell-Touched",
    ],
    "low_magic": [
        "Dormant", "Fading", "Whispering", "Residual", "Faint", "Weak", "Dim", "Dull",
        "Pale", "Muted", "Subdued", "Quiet", "Still", "Calm", "Serene", "Tranquil", "Mild",
        "Gentle", "Wild", "Feral", "Natural", "Raw", "Crude", "Rough", "Coarse", "Humble",
        "Modest", "Weathered", "Seasoned", "Earthy", "Rooted", "Simple", "Plain-Wrought",
    ],
    "medieval": [
        "Sturdy", "Well-Worn", "Plain", "Honed", "Strong", "Tough", "Hard", "Solid", "Firm",
        "Heavy", "Light", "Thick", "Thin", "Broad", "Narrow", "Wide", "Long", "Short", "Fine",
        "Good", "Fair", "Brave", "Stout", "Valiant", "Hardy", "Robust", "Rugged", "Sound",
        "Balanced", "Tempered", "Reliable", "Serviceable", "Standard", "Common", "Trusted",
    ],
    "renaissance": [
        "Gilded", "Filigreed", "Artisan-Wrought", "Polished", "Ornate", "Decorated",
        "Embellished", "Chased", "Engraved", "Etched", "Carved", "Sculpted", "Molded",
        "Cast", "Forged", "Wrought", "Hammered", "Fluted", "Damascened", "Inlaid",
        "Burnished", "Sleek", "Graceful", "Refined", "Elegant", "Masterful", "Custom",
        "Commissioned", "Classical", "Fine-Stitched", "Intricate",
    ],
    "industrial": [
        "Riveted", "Forged", "Standard-Issue", "Mass-Produced", "Machined", "Cast-Iron",
        "Heavy-Duty", "Galvanized", "Pneumatic", "Hydraulic", "Steam-Powered", "Gear-Driven",
        "Welded", "Bolted", "Stamped", "Engineered", "Assembled", "Fabricated", "Automated",
        "Standardized", "Uniform", "Interchangeable", "Modular", "Prefabricated", "Bulky",
        "Functional", "Utilitarian", "Practical", "Mechanical", "Automatic", "Motorized",
        "Electric", "Milled", "Plated", "Reinforced", "Corrugated",
    ],
    "modern": [
        "Tactical", "Precision", "Ballistic", "Composite", "Advanced", "High-Tech", "Digital",
        "Smart", "Synthetic", "Polymer", "Carbon-Fiber", "Titanium", "Alloy", "Reinforced",
        "Ergonomic", "Streamlined", "Modular", "Customized", "Optimized", "Enhanced",
        "Upgraded", "Modified", "Specialized", "Professional", "Commercial-Grade",
        "Military-Spec", "Mil-Spec", "Certified", "Rated", "Tested", "Secure", "Anodized",
        "Waterproof", "Shockproof", "Insulated", "Lightweight", "Surplus", "Issued",
    ],
    "post_apoc": [
        "Rusted", "Scavenged", "Jury-Rigged", "Salvaged", "Makeshift", "Crude", "Rough", "Raw",
        "Broken", "Fractured", "Shattered", "Cracked", "Split", "Torn", "Ripped", "Mangled",
        "Crushed", "Smashed", "Beaten", "Battered", "Dented", "Scarred", "Scratched", "Marred",
        "Spoiled", "Ruined", "Damaged", "Defective", "Flawed", "Corroded", "Contaminated",
        "Scorched", "Charred", "Patched", "Taped", "Cobbled", "Reclaimed", "Worn",
    ],
}


_ITEM_NOUN_BY_CATEGORY: Dict[str, List[str]] = {
    "Melee": [
        "Blade", "Maul", "Cleaver", "Axe", "Spear", "Dagger", "Sword", "Greatsword",
        "Longsword", "Shortsword", "Rapier", "Scimitar", "Falchion", "Cutlass", "Saber",
        "Broadsword", "Claymore", "Mace", "Morningstar", "Flail", "Warhammer", "Battleaxe",
        "Greataxe", "Halberd", "Glaive", "Pike", "Lance", "Trident", "Quarterstaff", "Club",
        "Cudgel", "Staff", "Whip", "Gauntlet", "Kopis", "Gladius", "Dirk", "Stiletto",
        "War-Pick", "Billhook", "Kukri", "Machete", "Hatchet",
    ],
    "Ranged": [
        "Bow", "Crossbow", "Rifle", "Pistol", "Sling", "Longbow", "Shortbow", "Recurve",
        "Arbalest", "Light Crossbow", "Heavy Crossbow", "Hand Crossbow", "Musket", "Carbine",
        "Shotgun", "Blunderbuss", "Flintlock", "Revolver", "Semi-Auto Rifle", "Sniper Rifle",
        "Dart Gun", "Blowgun", "Bolas", "Chakram", "Shuriken", "Throwing Knife", "Throwing Axe",
        "Javelin", "Harpoon", "Net", "Slingshot", "Matchlock", "Repeater", "Bolt-Action",
        "Pump-Action", "Lever-Action", "Derringer", "Hand Cannon",
    ],
    "Armor": [
        "Plate", "Mail", "Vest", "Hauberk", "Cuirass", "Breastplate", "Backplate", "Gorget",
        "Pauldrons", "Spaulders", "Bracers", "Vambraces", "Gauntlets", "Cuisses", "Greaves",
        "Sabatons", "Brigandine", "Gambeson", "Doublet", "Jack", "Coat", "Jerkin", "Tunic",
        "Cloak", "Cape", "Mantle", "Shroud", "Hood", "Helmet", "Helm", "Bascinet", "Sallet",
        "Armet", "Great Helm", "Morion", "Burgonet", "Coif", "Cap", "Shield", "Buckler",
        "Targe", "Kite Shield", "Heater Shield", "Tower Shield", "Round Shield", "Flak Vest",
        "Ballistic Vest", "Field Jacket",
    ],
    "General": [
        "Rope", "Rations", "Torch", "Bedroll", "Lantern", "Pack", "Backpack", "Sack", "Bag",
        "Pouch", "Purse", "Case", "Box", "Chest", "Crate", "Barrel", "Cask", "Bottle",
        "Flask", "Vial", "Jug", "Jar", "Pot", "Pan", "Kettle", "Cauldron", "Cup", "Goblet",
        "Mug", "Tankard", "Plate", "Bowl", "Knife", "Fork", "Spoon", "Needle", "Thread",
        "Twine", "Cord", "Chain", "Lock", "Key", "Padlock", "Tinderbox", "Spyglass", "Compass",
        "Canteen", "Blanket", "Whetstone", "Oil Flask",
    ],
    "Consumable": [
        "Elixir", "Tonic", "Draught", "Poultice", "Rations", "Potion", "Phial", "Infusion",
        "Decoction", "Tincture", "Extract", "Essence", "Fluid", "Juice", "Sap", "Syrup",
        "Oil", "Balm", "Salve", "Ointment", "Cream", "Paste", "Gel", "Lotion", "Wash",
        "Liniment", "Bandage", "Dressing", "Gauze", "Swab", "Pill", "Tablet", "Capsule",
        "Lozenge", "Powder", "Dust", "Salt", "Crystal", "Herb", "Root", "Leaf",
    ],
}


# -----------------------------------------------------------------------------
# Public helpers
# -----------------------------------------------------------------------------
def axis_to_band(axis_position: int) -> str:
    """Clamp axis_position to [0..10] then look up the band name."""
    clamped = max(0, min(10, int(axis_position)))
    return AXIS_POSITION_TO_BAND[clamped]


def _fit_generated_name(candidate: str, suffix: str = "") -> str:
    """Keep generated names within the DB column limit, preserving suffixes."""
    if len(candidate) + len(suffix) <= _MAX_GENERATED_NAME_LEN:
        return f"{candidate}{suffix}"

    room = _MAX_GENERATED_NAME_LEN - len(suffix)
    if room <= 3:
        return suffix[-_MAX_GENERATED_NAME_LEN:]
    return candidate[: room - 3].rstrip() + "..." + suffix


def _with_collision_guard(
    rng, candidate: str, used: Set[str]
) -> str:
    """Return a name that is not already in `used`. Tries a reroll tag,
    then falls back to Roman-numeral suffixes. Always adds to `used`."""
    candidate = _fit_generated_name(candidate)
    if candidate not in used:
        used.add(candidate)
        return candidate

    salt = rng.randint(2, 9)
    alt = _fit_generated_name(candidate, f" {salt}")
    if alt not in used:
        used.add(alt)
        return alt

    roman = ["II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]
    for suffix in roman:
        tagged = _fit_generated_name(candidate, f" {suffix}")
        if tagged not in used:
            used.add(tagged)
            return tagged

    fallback = _fit_generated_name(candidate, f" #{rng.randint(100, 9999)}")
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
    else:
        candidate = f"{adjective} {noun}"

    if is_cursed:
        candidate = f"{candidate} (cursed)"

    return _with_collision_guard(rng, candidate, used)
