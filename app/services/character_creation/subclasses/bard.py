"""SRD Bard subclasses."""

from app.services.character_creation.subclasses._helpers import subclass_entry

SUBCLASSES = (
    subclass_entry(
        key="college-of-lore",
        name="College of Lore",
        class_key="bard",
        pick_level=3,
        tagline="Knowledge and Wit",
        summary="Bards of the College of Lore collect secrets and use wit and magic to confound foes.",
        grants=[
            (3, "Bonus Proficiencies", "Gain proficiency with three additional skills."),
            (3, "Cutting Words", "Reaction to reduce foe attack/damage/check roll using Bardic Inspiration."),
            (6, "Additional Magical Secrets", "Learn two spells from any class."),
            (14, "Peerless Skill", "Add Bardic Inspiration die to ability check you fail."),
        ],
    ),
)
