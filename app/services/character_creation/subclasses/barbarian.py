"""SRD Barbarian subclasses."""

from app.services.character_creation.subclasses._helpers import subclass_entry

SUBCLASSES = (
    subclass_entry(
        key="path-of-the-berserker",
        name="Path of the Berserker",
        class_key="barbarian",
        pick_level=3,
        tagline="Channel Rage into Violent Fury",
        summary=(
            "Barbarians on this path direct Rage toward violence, "
            "thrilling in battle as fury seizes and empowers them."
        ),
        grants=[
            (3, "Frenzy", "Bonus attack as part of Attack while raging; exhaustion after."),
            (6, "Mindless Rage", "Immune to charmed and frightened while raging."),
            (10, "Intimidating Presence", "Bonus action to frighten nearby creatures (WIS save)."),
            (14, "Retaliation", "Reaction melee attack when damaged by adjacent foe."),
        ],
    ),
)
