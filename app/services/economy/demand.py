# app/services/economy/demand.py

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass, field
from typing import DefaultDict, List, Optional

from sqlalchemy.orm import joinedload

from app.models import DemandModifier


def load_active_modifiers_for_campaign(campaign_id: int) -> List[DemandModifier]:
    """Load active demand modifiers once per tick (with targets eager-loaded)."""
    return (
        DemandModifier.query.filter(
            DemandModifier.is_active == True,
            DemandModifier.campaign_id == campaign_id,
        )
        .options(joinedload(DemandModifier.targets))
        .all()
    )


@dataclass
class DemandContext:
    """In-memory index of active demand modifiers for one campaign tick."""

    campaign_id: int
    global_modifiers: List[float] = field(default_factory=list)
    city_buckets: DefaultDict[int, List[float]] = field(
        default_factory=lambda: defaultdict(list)
    )
    shop_buckets: DefaultDict[int, List[float]] = field(
        default_factory=lambda: defaultdict(list)
    )
    item_buckets: DefaultDict[int, List[float]] = field(
        default_factory=lambda: defaultdict(list)
    )

    @classmethod
    def from_modifiers(
        cls, campaign_id: int, modifiers: List[DemandModifier]
    ) -> "DemandContext":
        ctx = cls(campaign_id=campaign_id)
        for mod in modifiers:
            if mod.scope == "global":
                ctx.global_modifiers.append(float(mod.effect_value))
            for target in mod.targets or []:
                if target.campaign_id != campaign_id:
                    continue
                effect = float(mod.effect_value)
                if target.entity_type == "city":
                    ctx.city_buckets[int(target.entity_id)].append(effect)
                elif target.entity_type == "shop":
                    ctx.shop_buckets[int(target.entity_id)].append(effect)
                elif target.entity_type == "item":
                    ctx.item_buckets[int(target.entity_id)].append(effect)
        return ctx

    def modifier_total(
        self,
        city_id=None,
        shop_id=None,
        item_id=None,
    ) -> float:
        total_modifier = 1.0
        total_modifier += sum(self.global_modifiers)
        if city_id is not None:
            total_modifier += sum(self.city_buckets.get(int(city_id), []))
        if shop_id is not None:
            total_modifier += sum(self.shop_buckets.get(int(shop_id), []))
        if item_id is not None:
            total_modifier += sum(self.item_buckets.get(int(item_id), []))
        return total_modifier


def _modifier_total_from_list(
    active_modifiers: List[DemandModifier],
    campaign_id: int,
    city_id=None,
    shop_id=None,
    item_id=None,
) -> float:
    total_modifier = 1.0
    for mod in active_modifiers:
        if mod.scope == "global":
            total_modifier += mod.effect_value
        for target in mod.targets or []:
            if target.campaign_id != campaign_id:
                continue
            if target.entity_type == "city" and target.entity_id == city_id:
                total_modifier += mod.effect_value
            elif target.entity_type == "shop" and target.entity_id == shop_id:
                total_modifier += mod.effect_value
            elif target.entity_type == "item" and target.entity_id == item_id:
                total_modifier += mod.effect_value
    return total_modifier


def get_active_modifiers(
    campaign_id: int,
    city_id=None,
    shop_id=None,
    item_id=None,
    preloaded_modifiers: Optional[List[DemandModifier]] = None,
    demand_context: Optional[DemandContext] = None,
):
    """
    Retrieves active demand modifier total for one campaign.

    Evaluation order:
    1. ``demand_context`` — indexed in-memory hot path (zero DB reads).
    2. ``preloaded_modifiers`` — legacy list path for transition callers.
    3. Standalone DB query when neither is provided.
    """
    if demand_context is not None:
        return demand_context.modifier_total(
            city_id=city_id, shop_id=shop_id, item_id=item_id
        )

    if preloaded_modifiers is not None:
        return _modifier_total_from_list(
            preloaded_modifiers, campaign_id, city_id, shop_id, item_id
        )

    active_modifiers = load_active_modifiers_for_campaign(campaign_id)
    return _modifier_total_from_list(
        active_modifiers, campaign_id, city_id, shop_id, item_id
    )


def calculate_demand(
    rarity,
    stock_level,
    campaign_id: int,
    city_id=None,
    shop_id=None,
    item_id=None,
    rng: Optional[random.Random] = None,
    preloaded_modifiers: Optional[List[DemandModifier]] = None,
    demand_context: Optional[DemandContext] = None,
):
    """
    Demand strength as a multiplier (~0.5-3+) from DB modifiers, rarity, stock, and RNG.
    """
    rng = rng or random
    modifier_base = get_active_modifiers(
        campaign_id,
        city_id=city_id,
        shop_id=shop_id,
        item_id=item_id,
        preloaded_modifiers=preloaded_modifiers,
        demand_context=demand_context,
    )
    rarity_effect = rarity * 0.2
    stock_effect = max(0.1, (stock_level / 100) * 0.1)
    random_fluctuation = rng.uniform(0.9, 1.1)

    demand = modifier_base * (1 + rarity_effect - stock_effect) * random_fluctuation
    return round(demand, 4)
