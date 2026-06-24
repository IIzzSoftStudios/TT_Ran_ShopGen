"""SRD Wizard subclasses."""

from app.services.character_creation.subclasses._helpers import subclass_entry

SUBCLASSES = (
    subclass_entry(
        key="school-of-evocation",
        name="School of Evocation",
        class_key="wizard",
        pick_level=2,
        tagline="Master of Destructive Magic",
        summary="Evokers create powerful effects that harm foes while sparing allies.",
        grants=[
            (2, "Evocation Savant", "Halve gold/time to copy evocation spells; double proficiency on INT checks for evocation."),
            (2, "Sculpt Spells", "Allies automatically succeed on saves for your evocation spells."),
            (6, "Potent Cantrip", "Creatures that succeed on saves vs your cantrips still take half damage."),
            (10, "Empowered Evocation", "Add INT mod to one damage roll of evocation spells."),
            (14, "Overchannel", "Maximize damage of 5th-level or lower evocation spells (risk self-damage)."),
        ],
    ),
)
