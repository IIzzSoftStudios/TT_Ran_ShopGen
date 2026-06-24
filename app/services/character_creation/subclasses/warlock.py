"""SRD Warlock subclasses."""

from app.services.character_creation.subclasses._helpers import subclass_entry

SUBCLASSES = (
    subclass_entry(
        key="the-fiend",
        name="The Fiend",
        class_key="warlock",
        pick_level=1,
        tagline="Pact with an Infernal Patron",
        summary="Warlocks bound to the Fiend gain power from the lower planes.",
        grants=[
            (1, "Dark One's Blessing", "Gain temp HP when you reduce a hostile creature to 0 HP."),
            (1, "Fiend Spells", "Always have certain fiend-themed spells available."),
            (6, "Dark One's Own Luck", "Add d10 to ability check or save (short/long rest recharge)."),
            (10, "Fiendish Resilience", "Choose a damage type to resist until next long rest."),
            (14, "Hurl Through Hell", "Banish target to hellish landscape on hit (long rest recharge)."),
        ],
    ),
)
