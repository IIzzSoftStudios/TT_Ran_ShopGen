"""SRD Druid subclasses."""

from app.services.character_creation.subclasses._helpers import subclass_entry

SUBCLASSES = (
    subclass_entry(
        key="circle-of-the-land",
        name="Circle of the Land",
        class_key="druid",
        pick_level=2,
        tagline="Magic of the Land",
        summary="Druids of the Circle of the Land draw on the magic of terrain they have bonded with.",
        grants=[
            (2, "Bonus Cantrip", "Learn one additional druid cantrip."),
            (2, "Natural Recovery", "Recover spell slots during a short rest once per long rest."),
            (3, "Circle Spells", "Always have certain land-themed spells prepared."),
            (6, "Land's Stride", "Ignore difficult terrain; immunity to nonmagical plant hazards."),
            (10, "Nature's Ward", "Immune to charm and frighten from elementals or fey."),
            (14, "Nature's Sanctuary", "Beasts and plant creatures must save to attack you."),
        ],
    ),
)
