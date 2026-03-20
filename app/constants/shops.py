"""
Canonical shop type labels for GM UI suggestions (datalist, etc.).
Union with distinct types from the DB per GM at runtime.
Includes seeder SHOP_THEMES keys and GM add/edit form options.
"""

SHOP_TYPE_DEFAULTS = frozenset(
    {
        # GM add / edit shop forms
        "Armor",
        "Arms Dealer",
        "Cyberwear",
        "General Store",
        "Medical",
        "Garage",
        "Airport",
        "Stable",
        "Dock",
        "Military Base",
        "Fence",
        # Seeder SHOP_THEMES
        "Weapon Shop",
        "Armor Shop",
        "Potion Shop",
        "Magic Shop",
        "Pawn Shop",
        "Bookstore",
        "Blacksmith",
        "Jeweler",
        # Plan examples / common fantasy labels
        "Alchemist",
        "Tavern",
    }
)
