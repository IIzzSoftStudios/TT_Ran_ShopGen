"""Rule set registry base types.

Each table-top RPG system (D&D 5e, PF2E, Generic, future GM-custom) is a
``Ruleset`` instance exposing the fixed schema of abilities, skills, saves and
derived stats the character sheet renders. The character_sheet_service
consumes this schema to build the template-ready view and to whitelist inputs
on writes.

Keeping this as plain dataclasses (not DB rows) means:
- schema lookup is a pure Python dict hit, no query on every sheet render;
- the registry is extensible at runtime for future GM-custom rule sets;
- validation keys live in one place instead of sprinkled across routes.
"""
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass(frozen=True)
class AbilityDef:
    key: str
    label: str


@dataclass(frozen=True)
class SkillDef:
    key: str
    label: str
    ability_key: str


@dataclass(frozen=True)
class SaveDef:
    key: str
    label: str
    ability_key: Optional[str] = None


@dataclass(frozen=True)
class DerivedDef:
    key: str
    label: str
    # When True, the stat is pinned to the character header strip (above
    # Saves on Player_Home.html, between name/class and saves). When False,
    # it drops into the Core Stats grid alongside abilities. Drives both the
    # payload schema and the dashboard JS so there's one source of truth.
    header: bool = False


@dataclass(frozen=True)
class ProficiencyTier:
    key: str
    label: str
    value: int
    multiplier: float


@dataclass(frozen=True)
class Ruleset:
    system_type: str
    display_name: str
    abilities: tuple
    skills: tuple
    saves: tuple
    derived: tuple
    proficiency_tiers: tuple
    supports_skill_proficiency: bool = False
    supports_save_proficiency: bool = False
    ability_min: int = 1
    ability_max: int = 30
    ability_default: int = 10

    _ability_mod_fn: Optional[Callable[[int], int]] = field(default=None, repr=False)
    _prof_bonus_fn: Optional[Callable[[int], int]] = field(default=None, repr=False)

    def compute_ability_mod(self, score):
        if score is None:
            return 0
        try:
            score_int = int(score)
        except (TypeError, ValueError):
            return 0
        if self._ability_mod_fn is not None:
            return self._ability_mod_fn(score_int)
        return (score_int - 10) // 2

    def proficiency_bonus(self, level):
        try:
            lvl = int(level) if level is not None else 0
        except (TypeError, ValueError):
            lvl = 0
        if self._prof_bonus_fn is not None:
            return self._prof_bonus_fn(lvl)
        return 0

    def clamp_ability(self, score):
        try:
            s = int(score)
        except (TypeError, ValueError):
            return None
        if s < self.ability_min:
            return self.ability_min
        if s > self.ability_max:
            return self.ability_max
        return s

    def ability_keys(self):
        return tuple(a.key for a in self.abilities)

    def skill_keys(self):
        return tuple(s.key for s in self.skills)

    def save_keys(self):
        return tuple(s.key for s in self.saves)

    def tier_values(self):
        return tuple(t.value for t in self.proficiency_tiers)

    def tier_by_value(self, value):
        try:
            v = int(value)
        except (TypeError, ValueError):
            return None
        for t in self.proficiency_tiers:
            if t.value == v:
                return t
        return None

    def to_meta(self):
        """Lightweight dict for Jinja templates (avoids exposing callables)."""
        return {
            "system_type": self.system_type,
            "display_name": self.display_name,
            "supports_skill_proficiency": self.supports_skill_proficiency,
            "supports_save_proficiency": self.supports_save_proficiency,
            "proficiency_tiers": [
                {"key": t.key, "label": t.label, "value": t.value}
                for t in self.proficiency_tiers
            ],
            "ability_min": self.ability_min,
            "ability_max": self.ability_max,
        }
