"""Ranking engine.

Simple ranking of signals by confidence and category priority.
"""
from typing import List
from engine.signal_models import Signal


CATEGORY_PRIORITY = {
    # High-priority directional signals
    "breakout": 5,
    "trend_continuation": 5,
    # Dip / value entry signals
    "dip": 4,
    "quality_dip": 4,
    "buy_the_dip": 4,
    "growth_value": 4,
    # Event-driven signals — high urgency when firing
    "earnings_catalyst": 4,
    # Sector and analyst signals
    "catalyst_watch": 3,
    "sector_rotation": 3,
    "unusual_volume": 3,
    "quant_anomaly": 3,
    # Risk / concentration signals — lower than opportunity signals but important
    "risk": 2,
    "concentration_risk": 2,
    "macro_divergence": 2,
    "overlap_exposure_warning": 2,
    "trim_watch": 2,
}


def ranking_score(signal: Signal) -> int:
    pr = CATEGORY_PRIORITY.get(signal.category, 1)
    base = (signal.confidence * 10) + (pr * 100)
    multiplier = (signal.metadata or {}).get("brain_weight_multiplier", 1.0)
    try:
        multiplier_val = float(multiplier)
    except (TypeError, ValueError):
        multiplier_val = 1.0

    quality_bonus = 0
    sector_ret = (signal.metadata or {}).get("sector_return_20d")
    if isinstance(sector_ret, (int, float)) and sector_ret > 0:
        quality_bonus += 20
    peer_rs = (signal.metadata or {}).get("peer_relative_strength")
    if isinstance(peer_rs, (int, float)) and peer_rs > 0:
        quality_bonus += 20

    return int(round((base * multiplier_val) + quality_bonus))


def rank_signals(signals: List[Signal], top_n: int = 5) -> List[Signal]:
    return sorted(signals, key=ranking_score, reverse=True)[:top_n]


__all__ = ["rank_signals", "ranking_score"]
