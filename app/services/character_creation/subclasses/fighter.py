"""SRD Fighter subclasses."""

from app.services.character_creation.subclasses._helpers import subclass_entry

SUBCLASSES = (
    subclass_entry(
        key="champion",
        name="Champion",
        class_key="fighter",
        pick_level=3,
        tagline="Raw Physical Power",
        summary="Champions focus on developing raw physical power honed to deadly perfection.",
        grants=[
            (3, "Improved Critical", "Weapon attacks score a critical hit on a roll of 19 or 20."),
            (7, "Remarkable Athlete", "+half proficiency to STR/DEX/CON checks not using proficiency."),
            (10, "Additional Fighting Style", "Choose a second fighting style."),
            (15, "Superior Critical", "Weapon attacks score a critical hit on a roll of 18–20."),
            (18, "Survivor", "Regain HP at start of turn if below half HP and above 0."),
        ],
    ),
)
