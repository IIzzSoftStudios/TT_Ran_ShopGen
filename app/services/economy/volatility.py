"""Market volatility scaling for economy pricing functions."""

from __future__ import annotations

import random
from typing import Optional, Sequence

DEFAULT_MARKET_VOLATILITY = 5
MIN_MARKET_VOLATILITY = 0
MAX_MARKET_VOLATILITY = 10

_BASE_JITTER_HALF = 0.1
_BASE_EVENT_CHOICES: Sequence[float] = (-0.1, 0.0, 0.2)


def normalize_market_volatility(raw: object) -> int:
    """Clamp volatility to 0–10; default 5 preserves legacy tick behavior."""
    if raw is None:
        return DEFAULT_MARKET_VOLATILITY
    try:
        level = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_MARKET_VOLATILITY
    return max(MIN_MARKET_VOLATILITY, min(MAX_MARKET_VOLATILITY, level))


def volatility_scale(level: int) -> float:
    """Multiplier where 5 -> 1.0 (current defaults), 0 -> no jitter/events."""
    level = normalize_market_volatility(level)
    if level == 0:
        return 0.0
    return level / DEFAULT_MARKET_VOLATILITY


def random_demand_fluctuation(rng: random.Random, volatility: int) -> float:
    """Scale demand jitter band; volatility 5 matches legacy ``uniform(0.9, 1.1)``."""
    scale = volatility_scale(volatility)
    if scale <= 0:
        return 1.0
    half = _BASE_JITTER_HALF * scale
    return rng.uniform(1.0 - half, 1.0 + half)


def random_event_modifier(rng: random.Random, volatility: int) -> float:
    """Scale discrete price shock; volatility 5 matches legacy ``choice([-0.1, 0, 0.2])``."""
    scale = volatility_scale(volatility)
    if scale <= 0:
        return 0.0
    choices = [float(c) * scale for c in _BASE_EVENT_CHOICES]
    return float(rng.choice(choices))
