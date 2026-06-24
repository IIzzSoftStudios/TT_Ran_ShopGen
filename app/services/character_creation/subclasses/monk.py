"""SRD Monk subclasses."""

from app.services.character_creation.subclasses._helpers import subclass_entry

SUBCLASSES = (
    subclass_entry(
        key="way-of-the-open-hand",
        name="Way of the Open Hand",
        class_key="monk",
        pick_level=3,
        tagline="Ultimate Martial Arts",
        summary="Monks of the Open Hand are masters of unarmed combat and ki manipulation.",
        grants=[
            (3, "Open Hand Technique", "Flurry of Blows can knock prone, push, or deny reactions."),
            (6, "Wholeness of Body", "Regain HP equal to 3 × monk level (long rest recharge)."),
            (11, "Tranquility", "Sanctuary effect until you attack (long rest recharge)."),
            (17, "Quivering Palm", "Set up delayed lethal ki strike on a creature."),
        ],
    ),
)
