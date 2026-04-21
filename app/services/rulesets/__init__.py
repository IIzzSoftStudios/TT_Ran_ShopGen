"""Rule set registry entrypoint.

Usage::

    from app.services.rulesets import get_ruleset
    rs = get_ruleset(campaign.system_type)
    rs.skills  # tuple of SkillDef
    rs.compute_ability_mod(14)  # +2 for D&D 5e

Unknown ``system_type`` values fall back to the ``generic`` rule set so a
misconfigured campaign never 500s the character sheet.
"""
from app.services.rulesets.base import (
    AbilityDef,
    DerivedDef,
    ProficiencyTier,
    Ruleset,
    SaveDef,
    SkillDef,
)
from app.services.rulesets.dnd5e import RULESET as _DND5E
from app.services.rulesets.generic import RULESET as _GENERIC
from app.services.rulesets.pf2e import RULESET as _PF2E


_REGISTRY = {}


def register(ruleset):
    """Register or replace a Ruleset under its ``system_type`` key.

    Used internally during module import and exposed for future GM-custom
    rule set plug-ins.
    """
    if not isinstance(ruleset, Ruleset):
        raise TypeError("register() expects a Ruleset instance")
    _REGISTRY[ruleset.system_type] = ruleset
    # Common aliases for D&D 5e so existing template checks on
    # 'dnd' / '5e' keep resolving to the same rule set.
    if ruleset.system_type == "dnd5e":
        _REGISTRY.setdefault("dnd", ruleset)
        _REGISTRY.setdefault("5e", ruleset)


def get_ruleset(system_type):
    """Return the Ruleset for ``system_type`` or the generic fallback."""
    if not system_type:
        return _REGISTRY["generic"]
    key = str(system_type).strip().lower()
    return _REGISTRY.get(key, _REGISTRY["generic"])


def known_system_types():
    """Canonical set of registered system_type keys (excludes aliases)."""
    seen = set()
    out = []
    for rs in _REGISTRY.values():
        if rs.system_type in seen:
            continue
        seen.add(rs.system_type)
        out.append(rs.system_type)
    return tuple(out)


# Seed registry with built-in rule sets.
register(_GENERIC)
register(_DND5E)
register(_PF2E)


__all__ = [
    "AbilityDef",
    "DerivedDef",
    "ProficiencyTier",
    "Ruleset",
    "SaveDef",
    "SkillDef",
    "get_ruleset",
    "known_system_types",
    "register",
]
