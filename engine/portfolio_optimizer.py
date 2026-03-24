"""Portfolio optimization helpers for signal-to-allocation translation."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List

from engine.signal_models import Signal


ADD_TYPES = {"breakout", "trend_continuation", "buy_the_dip", "dip", "quality_dip", "growth_value", "earnings_catalyst"}


def _corr_penalty(signal: Signal, others: Iterable[Signal]) -> float:
    sector = (signal.metadata or {}).get("sector")
    if not isinstance(sector, str):
        return 1.0
    count = sum(1 for s in others if (s.metadata or {}).get("sector") == sector and s.ticker != signal.ticker)
    return max(0.6, 1.0 - (0.08 * count))


def optimize_targets(
    signals: List[Signal],
    *,
    max_single_name_weight: float = 0.12,
    max_sector_weight: float = 0.35,
    gross_risk_budget: float = 0.75,
) -> Dict[str, Any]:
    """Return target allocation plan by ticker and sector.

    This is a conservative allocator using confidence and volatility proxies.
    """
    candidates = [s for s in signals if s.signal_type in ADD_TYPES and s.direction in {"up", "neutral"}]
    if not candidates:
        return {
            "targets": {},
            "sector_targets": {},
            "gross_target": 0.0,
            "notes": ["No add-candidate signals for optimization"],
        }

    raw_scores: Dict[str, float] = {}
    sector_of: Dict[str, str] = {}
    chosen_signal: Dict[str, Signal] = {}
    for s in candidates:
        vol = abs(float(s.change_pct or 0.01))
        vol = max(0.01, min(0.08, vol))
        edge = max(0.0, min(1.0, float(s.confidence) / 100.0))
        score = edge / vol
        score *= _corr_penalty(s, candidates)
        if s.brain == "SectorRotation":
            score *= 1.05
        if score > raw_scores.get(s.ticker, 0.0):
            raw_scores[s.ticker] = score
            chosen_signal[s.ticker] = s
        sector = (s.metadata or {}).get("sector")
        if isinstance(sector, str):
            sector_of[s.ticker] = sector

    total = sum(raw_scores.values()) or 1.0
    targets: Dict[str, float] = {}
    for ticker, score in raw_scores.items():
        w = (score / total) * gross_risk_budget
        targets[ticker] = min(max_single_name_weight, max(0.0, w))

    # Enforce sector caps by proportional scaling within capped sectors.
    sector_buckets: Dict[str, List[str]] = defaultdict(list)
    for t in targets:
        sector_buckets[sector_of.get(t, "Unknown")].append(t)

    sector_targets: Dict[str, float] = {}
    notes: List[str] = []
    for sector, names in sector_buckets.items():
        sec_weight = sum(targets[n] for n in names)
        if sec_weight > max_sector_weight and sec_weight > 0:
            scale = max_sector_weight / sec_weight
            for n in names:
                targets[n] *= scale
            sec_weight = max_sector_weight
            notes.append(f"Scaled sector {sector} to cap {max_sector_weight:.0%}")
        sector_targets[sector] = round(sec_weight, 4)

    # Attach optimizer fields back to selected signals.
    for ticker, signal in chosen_signal.items():
        signal.metadata["optimizer_target_weight"] = round(targets.get(ticker, 0.0), 4)

    return {
        "targets": {k: round(v, 4) for k, v in sorted(targets.items(), key=lambda kv: kv[1], reverse=True)},
        "sector_targets": sector_targets,
        "gross_target": round(sum(targets.values()), 4),
        "notes": notes,
    }
