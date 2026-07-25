"""Demo walkthrough steps (session-driven).

Step state lives in ``session["demo_step"]``. Conversion is Register For Access only.
Client-side sub-phases under Step 1 (Nations tab → borders) live in
``static/js/demo_tutorial.js``.
"""

from __future__ import annotations

from typing import Any


DEMO_NATION_HINT = "Father's Castel-bari"

# Ordered steps. UI locks everything except ``allow_selectors`` for the
# current step (refined further by demo_tutorial.js for Step 1 sub-phases).
DEMO_STEPS: list[dict[str, Any]] = [
    {
        "id": 1,
        "title": "Welcome to Econo-Forge Demo",
        "heading": "Step 1 — Nations",
        "instructions": [
            "Click Nations in the left rail.",
            f'Draw borders for "{DEMO_NATION_HINT}", add a ruler via the NPC wizard, then place its cities.',
        ],
        "allow_selectors": [
            "#regions-tab-btn",
            "#regions-pane-content",
            "#gm-section-menu-btn",
            "#gm-left-chrome",
            "#gm-panel-backdrop",
            "#map-region-boundary-tools",
            "#map-region-boundary-row",
            "#map-stage",
            "#demo-tutorial-root",
        ],
        "nation_hint": DEMO_NATION_HINT,
    },
    {
        "id": 2,
        "title": "Continue with a real account",
        "heading": "Register For Access",
        "instructions": [
            "You have seen the Demo GM workspace.",
            "Register For Access to run your own campaigns.",
        ],
        "allow_selectors": [
            "#demo-tutorial-root",
        ],
        "register_cta": True,
    },
]


def get_demo_step(step_id: int | None) -> dict[str, Any] | None:
    if step_id is None:
        return None
    for step in DEMO_STEPS:
        if step["id"] == int(step_id):
            return step
    return None


def default_demo_step_id() -> int:
    return int(DEMO_STEPS[0]["id"])
