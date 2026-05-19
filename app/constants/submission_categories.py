"""Canonical categories and validation sets for user_submissions."""

BUG_REPORT_CATEGORIES = {
    "Simulation",
    "Shop",
    "City & Region",
    "Campaign & Characters",
    "Player market",
    "Account & session",
    "UI & display",
    "Performance",
    "Other",
}

FEEDBACK_CATEGORIES = {
    "Simulation & economy feel",
    "GM tools",
    "Player experience",
    "Campaign picker & onboarding",
    "Documentation",
    "Visual design",
    "General / other",
}

SUGGESTION_CATEGORIES = {
    "New feature",
    "UX/workflow",
    "Economy & balance",
    "GM workflow",
    "Player workflow",
    "Character sheet & inventory",
    "Reports & exports",
    "Accessibility",
    "Other",
}

VALID_CATEGORIES_BY_KIND = {
    "bug_report": BUG_REPORT_CATEGORIES,
    "feedback": FEEDBACK_CATEGORIES,
    "suggestion": SUGGESTION_CATEGORIES,
}

VALID_SEVERITIES = {"Minor", "Cosmetic", "Major", "Blocker"}

VALID_FREQUENCIES = {"Once", "Daily", "Weekly", "Constantly"}

VALID_STATUSES = {"pending", "reviewed", "closed"}

KINDS = frozenset(VALID_CATEGORIES_BY_KIND.keys())

EXTRA_KEYS_BY_KIND = {
    "bug_report": frozenset({"steps_to_reproduce", "expected_behavior", "severity"}),
    "feedback": frozenset({"rating", "worked_well", "frustrating"}),
    "suggestion": frozenset({"frequency", "beta_test"}),
}


def categories_for_json():
    """Lists for account_menu_config (JSON-serializable)."""
    return {kind: sorted(cats) for kind, cats in VALID_CATEGORIES_BY_KIND.items()}
