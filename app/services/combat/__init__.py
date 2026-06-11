"""Tactical combat services (D&D 5e only).

Pure rule math lives in :mod:`dnd5e_rules`; persistence and turn flow in
:mod:`encounter_service`. Nothing in this package touches the economy
simulation tick path.
"""


class CombatValidationError(ValueError):
    """Invalid combat input; routes map this to a 400 JSON error."""


class StaleTurnError(RuntimeError):
    """Client acted on an outdated turn_version; routes map this to 409."""
