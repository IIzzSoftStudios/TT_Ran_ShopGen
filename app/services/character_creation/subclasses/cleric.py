"""SRD Cleric subclasses."""

from app.services.character_creation.subclasses._helpers import subclass_entry

SUBCLASSES = (
    subclass_entry(
        key="life-domain",
        name="Life Domain",
        class_key="cleric",
        pick_level=1,
        tagline="Preserve and Restore Life",
        summary="Clerics of the Life Domain preserve life and heal the wounded.",
        grants=[
            (1, "Bonus Proficiency", "Proficiency with heavy armor."),
            (1, "Disciple of Life", "Healing spells restore additional HP equal to 2 + spell level."),
            (2, "Channel Divinity: Preserve Life", "Restore HP divided among creatures within 30 ft."),
            (6, "Blessed Healer", "Healing spells also heal you for 2 + spell level."),
            (8, "Divine Strike", "Once per turn, extra radiant damage on weapon attack."),
            (17, "Supreme Healing", "Healing spells always use maximum dice."),
        ],
    ),
)
