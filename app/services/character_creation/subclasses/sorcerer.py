"""SRD Sorcerer subclasses."""

from app.services.character_creation.subclasses._helpers import subclass_entry

SUBCLASSES = (
    subclass_entry(
        key="draconic-bloodline",
        name="Draconic Bloodline",
        class_key="sorcerer",
        pick_level=1,
        tagline="Power of Dragon Ancestry",
        summary="Sorcerers with draconic bloodline magic draw power from a dragon ancestor.",
        grants=[
            (1, "Dragon Ancestor", "Choose a dragon type; speak Draconic; double proficiency on CHA checks with dragons."),
            (1, "Draconic Resilience", "+1 HP per level; AC 13 + DEX when not wearing armor."),
            (6, "Elemental Affinity", "Add CHA mod to damage of matching element; resistance for 1 hour."),
            (14, "Dragon Wings", "Sprout dragon wings for 1 hour (long rest recharge)."),
            (18, "Draconic Presence", "Channel awe or fear in 60 ft (long rest recharge)."),
        ],
    ),
)
