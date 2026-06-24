"""SRD Rogue subclasses."""

from app.services.character_creation.subclasses._helpers import subclass_entry

SUBCLASSES = (
    subclass_entry(
        key="thief",
        name="Thief",
        class_key="rogue",
        pick_level=3,
        tagline="Burglar and Treasure Hunter",
        summary="Thieves hone skills useful for delving ancient ruins and urban larceny.",
        grants=[
            (3, "Fast Hands", "Bonus action Sleight of Hand, thieves' tools, or Use an Object."),
            (3, "Second-Story Work", "Climbing does not cost extra movement; +4 ft jump with running start."),
            (9, "Supreme Sneak", "Advantage on Stealth if you move no more than half speed."),
            (13, "Use Magic Device", "Ignore class/race/level requirements on magic items."),
            (17, "Thief's Reflexes", "Take two turns in the first round of combat."),
        ],
    ),
)
