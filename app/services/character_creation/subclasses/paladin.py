"""SRD Paladin subclasses."""

from app.services.character_creation.subclasses._helpers import subclass_entry

SUBCLASSES = (
    subclass_entry(
        key="oath-of-devotion",
        name="Oath of Devotion",
        class_key="paladin",
        pick_level=3,
        tagline="Hold to the Highest Ideals",
        summary="Paladins who take the Oath of Devotion hold themselves to the highest ideals of justice and order.",
        grants=[
            (3, "Oath Spells", "Always have certain devotion-themed spells prepared."),
            (3, "Channel Divinity", "Sacred Weapon and Turn the Unholy channel options."),
            (7, "Aura of Devotion", "You and allies within 10 ft immune to charm."),
            (15, "Purity of Spirit", "Always under protection from evil and good effect."),
            (20, "Holy Nimbus", "Emit bright light; extra radiant damage to fiends and undead."),
        ],
    ),
)
