<<<<<<< HEAD
"""
Canonical shop type labels for GM UI suggestions (datalist, etc.).
Union with distinct types from the DB per GM at runtime.
Includes seeder SHOP_THEMES keys and GM add/edit form options.
"""

SHOP_TYPE_DEFAULTS = frozenset(
    {
        # GM add / edit shop forms
=======
"""Canonical shop type labels for GM UI (datalist suggestions)."""

SHOP_TYPE_DEFAULTS = frozenset(
    {
>>>>>>> GCP
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
<<<<<<< HEAD
        # Seeder SHOP_THEMES
=======
>>>>>>> GCP
        "Weapon Shop",
        "Armor Shop",
        "Potion Shop",
        "Magic Shop",
        "Pawn Shop",
        "Bookstore",
        "Blacksmith",
        "Jeweler",
<<<<<<< HEAD
        # Plan examples / common fantasy labels
=======
>>>>>>> GCP
        "Alchemist",
        "Tavern",
    }
)
