"""GM market overview: per-item price/stock aggregates vs baselines and last sim run."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import func
from app.extensions import db
from app.models import Campaign, GlobalMarket, Item, Shop, ShopInventory, SimulationState
from app.services.simulation_state_helpers import get_simulation_state_for_campaign
from app.services.world_generator.campaign_settings import read_market_volatility

_EPSILON = 0.01


def _compare_vs_base(current: float, base: float) -> str:
    if abs(current - base) < _EPSILON:
        return "equal"
    if current > base:
        return "higher"
    return "lower"


def _normalize_last_market_run(raw: Any) -> Dict[str, Any]:
    """Coerce persisted JSON/JSONB into a dict for reads."""
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return {}
    if not isinstance(raw, dict):
        return {}
    return raw


def _item_hist(last_run_data: Dict[str, Any], item_id: int) -> Dict[str, Any]:
    """Look up per-item snapshot; keys may be str or int depending on JSON backend."""
    items_map = last_run_data.get("items") or {}
    if not isinstance(items_map, dict):
        return {}
    hist = items_map.get(str(item_id))
    if hist is None:
        hist = items_map.get(item_id)
    return hist if isinstance(hist, dict) else {}


def _delta_from_hist(hist: Dict[str, Any], start_key: str, end_key: str) -> Optional[float]:
    """Prefer precomputed delta keys; fall back to end − start."""
    if "price_delta" in hist and start_key.startswith("avg_price"):
        return float(hist["price_delta"])
    if "stock_delta" in hist and start_key.startswith("avg_stock"):
        return float(hist["stock_delta"])
    if start_key in hist and end_key in hist:
        return float(hist[end_key]) - float(hist[start_key])
    return None


def aggregate_item_metrics(
    campaign_id: int,
    *,
    in_stock_only: bool = False,
) -> Dict[int, Dict[str, Any]]:
    """Per-item avg price/stock across shop inventory (campaign-scoped).

    When ``in_stock_only`` is True, only inventory rows with ``stock > 0`` are
    included so catalog items with no stock do not appear.
    """
    q = (
        db.session.query(
            Item.item_id,
            func.avg(ShopInventory.dynamic_price).label("avg_price"),
            func.avg(ShopInventory.stock).label("avg_stock"),
            func.count(ShopInventory.inventory_id).label("shop_row_count"),
        )
        .join(ShopInventory, ShopInventory.item_id == Item.item_id)
        .join(Shop, ShopInventory.shop_id == Shop.shop_id)
        .filter(Item.campaign_id == campaign_id)
        .filter(Shop.campaign_id == campaign_id)
    )
    if in_stock_only:
        q = q.filter(ShopInventory.stock > 0)

    results = q.group_by(Item.item_id).all()

    metrics: Dict[int, Dict[str, Any]] = {}
    for row in results:
        avg_stock = float(row.avg_stock) if row.avg_stock is not None else 0.0
        if in_stock_only and avg_stock <= _EPSILON:
            continue
        metrics[int(row.item_id)] = {
            "avg_price": float(row.avg_price) if row.avg_price is not None else 0.0,
            "avg_stock": avg_stock,
            "shop_row_count": int(row.shop_row_count or 0),
        }
    return metrics


def build_market_overview_payload(campaign_id: int) -> Dict[str, Any]:
    current_metrics = aggregate_item_metrics(campaign_id, in_stock_only=True)
    market_volatility = read_market_volatility(campaign_id)

    market_map = {
        m.item_id: m
        for m in GlobalMarket.query.filter_by(campaign_id=campaign_id).all()
    }

    sim_state = get_simulation_state_for_campaign(db.session, campaign_id)
    last_run_data = _normalize_last_market_run(
        sim_state.last_market_run if sim_state is not None else None
    )

    if not current_metrics:
        items_q: List[Item] = []
    else:
        items_q = (
            Item.query.filter(
                Item.campaign_id == campaign_id,
                Item.item_id.in_(current_metrics.keys()),
            )
            .order_by(Item.name)
            .all()
        )

    payload_items: List[Dict[str, Any]] = []
    for item in items_q:
        metric = current_metrics.get(item.item_id)
        if not metric or metric["avg_stock"] <= _EPSILON:
            continue

        mkt_row = market_map.get(item.item_id)

        base_price = (
            float(mkt_row.average_price)
            if mkt_row is not None
            else float(item.base_price)
        )
        base_stock = (
            float(mkt_row.baseline_avg_stock)
            if mkt_row is not None and mkt_row.baseline_avg_stock is not None
            else 0.0
        )

        curr_price = metric["avg_price"]
        curr_stock = metric["avg_stock"]

        hist = _item_hist(last_run_data, item.item_id)
        last_run_price_delta = _delta_from_hist(
            hist, "avg_price_start", "avg_price_end"
        )
        last_run_stock_delta = _delta_from_hist(
            hist, "avg_stock_start", "avg_stock_end"
        )

        payload_items.append(
            {
                "item_id": item.item_id,
                "name": item.name,
                "type": item.type,
                "current_avg_price": round(curr_price, 2),
                "base_avg_price": round(base_price, 2),
                "price_vs_base": _compare_vs_base(curr_price, base_price),
                "last_run_price_delta": (
                    round(last_run_price_delta, 2)
                    if last_run_price_delta is not None
                    else None
                ),
                "current_avg_stock": round(curr_stock, 2),
                "base_avg_stock": round(base_stock, 2),
                "stock_vs_base": _compare_vs_base(curr_stock, base_stock),
                "last_run_stock_delta": (
                    round(last_run_stock_delta, 2)
                    if last_run_stock_delta is not None
                    else None
                ),
            }
        )

    last_run: Optional[Dict[str, Any]] = None
    if last_run_data.get("completed_at"):
        last_run = {
            "period": last_run_data.get("period"),
            "game_day_start": last_run_data.get("game_day_start"),
            "game_day_end": last_run_data.get("game_day_end"),
            "completed_at": last_run_data.get("completed_at"),
        }

    campaign = Campaign.query.get(campaign_id)
    current_game_day = (
        int(campaign.current_game_day)
        if campaign is not None and campaign.current_game_day is not None
        else None
    )

    return {
        "items": payload_items,
        "last_run": last_run,
        "current_game_day": current_game_day,
        "market_volatility": market_volatility,
        "stocked_item_count": len(payload_items),
    }


def persist_last_market_run_snapshot(
    campaign_id: int,
    period: str,
    game_day_start: int,
    game_day_end: int,
    start_metrics: Dict[int, Dict[str, Any]],
    end_metrics: Dict[int, Dict[str, Any]],
) -> None:
    """Write last successful batch market deltas onto ``SimulationState``."""
    from datetime import datetime

    from sqlalchemy.orm.attributes import flag_modified

    item_keys = set(start_metrics.keys()) | set(end_metrics.keys())
    items_payload: Dict[str, Dict[str, float]] = {}
    for item_id in item_keys:
        s_met = start_metrics.get(
            item_id, {"avg_price": 0.0, "avg_stock": 0.0}
        )
        e_met = end_metrics.get(
            item_id, {"avg_price": 0.0, "avg_stock": 0.0}
        )
        start_stock = float(s_met["avg_stock"])
        end_stock = float(e_met["avg_stock"])
        if start_stock <= _EPSILON and end_stock <= _EPSILON:
            continue

        price_start = float(s_met["avg_price"])
        price_end = float(e_met["avg_price"])
        stock_start = start_stock
        stock_end = end_stock

        items_payload[str(item_id)] = {
            "avg_price_start": price_start,
            "avg_price_end": price_end,
            "avg_stock_start": stock_start,
            "avg_stock_end": stock_end,
            "price_delta": price_end - price_start,
            "stock_delta": stock_end - stock_start,
        }

    snapshot = {
        "period": period,
        "game_day_start": game_day_start,
        "game_day_end": game_day_end,
        "completed_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "items": items_payload,
    }

    sim_state = get_simulation_state_for_campaign(db.session, campaign_id)
    if sim_state is None:
        sim_state = SimulationState(campaign_id=campaign_id)
        db.session.add(sim_state)
    sim_state.last_market_run = snapshot
    flag_modified(sim_state, "last_market_run")
    db.session.commit()


def start_metrics_json(metrics: Dict[int, Dict[str, Any]]) -> str:
    """Serialize start metrics for Redis (string keys)."""
    return json.dumps({str(k): v for k, v in metrics.items()})


def parse_start_metrics_json(raw: Union[str, bytes, None]) -> Optional[Dict[int, Dict[str, Any]]]:
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    return {int(k): v for k, v in parsed.items()}


def capture_start_metrics_for_job(campaign_id: int) -> str:
    """Snapshot in-stock metrics at enqueue time (before worker runs)."""
    metrics = aggregate_item_metrics(campaign_id, in_stock_only=True)
    return start_metrics_json(metrics)
