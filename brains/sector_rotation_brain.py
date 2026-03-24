"""Sector rotation brain.

Produces signals when a ticker's sector is a clear leader/laggard over 20d.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from engine.scoring_engine import compute_score_from_evidence
from engine.signal_models import Signal


def analyze(ticker_symbol: str, info: Dict[str, Any], anchor_entry: Dict[str, Any], config: Dict[str, Any]) -> List[Signal]:
    del anchor_entry
    signals: List[Signal] = []

    sector = info.get("sector")
    sector_ret = info.get("sector_return_20d")
    if not isinstance(sector, str) or not isinstance(sector_ret, (int, float)):
        return signals

    current_price = info.get("currentPrice")
    move_1d = info.get("move_1d")
    if current_price is None:
        return signals

    leader_cutoff = float(config.get("sector_leader_return_20d", 0.03))
    laggard_cutoff = float(config.get("sector_laggard_return_20d", -0.03))

    if sector_ret >= leader_cutoff:
        evidence = [
            {"type": "sector_rotation", "note": f"{sector} leadership {sector_ret:.2%}"},
        ]
        if isinstance(move_1d, (int, float)) and move_1d > 0:
            evidence.append({"type": "confirmation", "note": f"positive day {move_1d:.2%}"})
        score = compute_score_from_evidence(evidence, base_score=52)
        signals.append(
            Signal(
                ticker=ticker_symbol,
                signal_type="trend_continuation",
                brain="SectorRotation",
                direction="up",
                score_raw=score,
                confidence=score,
                priority="strong" if score >= 70 else "moderate",
                reason=f"{sector} sector leadership supports trend continuation",
                why_it_matters="Leadership sectors tend to attract incremental institutional flows.",
                confirmations=["sector_leadership"],
                suppressions=[],
                price=current_price,
                change_pct=move_1d,
                volume_ratio=info.get("volume_ratio"),
                metadata={
                    "quote_timestamp": str(info.get("timestamp")),
                    "source": "sector_rotation",
                    "sector": sector,
                    "sector_return_20d": sector_ret,
                },
                action_bias="WATCH",
                evidence=evidence,
                cooldown_key=f"{ticker_symbol}_sector_rotation_leader",
                timestamp=datetime.now(),
            )
        )

    elif sector_ret <= laggard_cutoff:
        evidence = [
            {"type": "sector_rotation", "note": f"{sector} lagging {sector_ret:.2%}"},
            {"type": "macro_divergence", "note": "sector underperforming"},
        ]
        score = compute_score_from_evidence(evidence, base_score=50)
        signals.append(
            Signal(
                ticker=ticker_symbol,
                signal_type="risk",
                brain="SectorRotation",
                direction="down",
                score_raw=score,
                confidence=score,
                priority="strong" if score >= 70 else "moderate",
                reason=f"{sector} sector lagging; elevate risk controls",
                why_it_matters="Persistent sector underperformance can cap upside and increase downside beta.",
                confirmations=["sector_lagging"],
                suppressions=[],
                price=current_price,
                change_pct=move_1d,
                volume_ratio=info.get("volume_ratio"),
                metadata={
                    "quote_timestamp": str(info.get("timestamp")),
                    "source": "sector_rotation",
                    "sector": sector,
                    "sector_return_20d": sector_ret,
                    "risk_priority_bypass": True,
                },
                action_bias="WATCH",
                evidence=evidence,
                cooldown_key=f"{ticker_symbol}_sector_rotation_laggard",
                timestamp=datetime.now(),
            )
        )

    return signals
