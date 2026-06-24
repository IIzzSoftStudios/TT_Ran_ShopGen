"""SRD Ranger subclasses."""

from app.services.character_creation.subclasses._helpers import subclass_entry

SUBCLASSES = (
    subclass_entry(
        key="hunter",
        name="Hunter",
        class_key="ranger",
        pick_level=3,
        tagline="Emulate the Hunt",
        summary="Hunters learn specialized techniques for taking down threats of particular types.",
        grants=[
            (3, "Hunter's Prey", "Choose Colossus Slayer, Giant Killer, or Horde Breaker."),
            (7, "Defensive Tactics", "Choose Escape the Horde, Multiattack Defense, or Steel Will."),
            (11, "Multiattack", "Choose Volley or Whirlwind Attack."),
            (15, "Superior Hunter's Defense", "Choose Evasion, Stand Against the Tide, or Uncanny Dodge."),
        ],
    ),
)
