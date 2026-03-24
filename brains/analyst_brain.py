"""Sell-side analyst brain.

Detects expectation changes via ratings or target updates.

This implementation uses yfinance's `recommendationMean` / `recommendationKey`.
"""

from typing import Dict, Any, List
from datetime import datetime

from engine.signal_models import Signal
from engine.scoring_engine import compute_score_from_evidence


def analyze(ticker_symbol: str, info: Dict[str, Any], anchor_entry: Dict[str, Any], config: Dict[str, Any]) -> List[Signal]:
    signals: List[Signal] = []

    rec_key = info.get("recommendationKey")
    rec_mean = info.get("recommendationMean")
    target_mean = info.get("targetMeanPrice")
    analyst_count = info.get("numberOfAnalystOpinions")
    current_price = info.get("currentPrice")
    earnings_days = info.get("earnings_days")
    iv_rank = info.get("iv_rank")
    earnings_window = int(config.get("earnings_risk_window_days", 7))

    evidence: List[Dict[str, Any]] = []
    confirmations: List[str] = []
    if rec_key:
        evidence.append({"type": "analyst_key", "note": f"{rec_key}"})
        confirmations.append("catalyst_hook")
    if isinstance(rec_mean, (int, float)):
        evidence.append({"type": "analyst_mean", "note": f"{rec_mean:.2f}"})
        confirmations.append("analyst_change")
    if isinstance(target_mean, (int, float)) and isinstance(current_price, (int, float)) and current_price > 0:
        upside = (target_mean - current_price) / current_price
        if upside >= 0.08:
            evidence.append({"type": "analyst_target_upside", "note": f"target upside {upside:.1%}"})
            confirmations.append("target_upside")
    if isinstance(analyst_count, (int, float)) and analyst_count >= 8:
        evidence.append({"type": "analyst_coverage", "note": f"opinions={int(analyst_count)}"})
        confirmations.append("broad_coverage")
    if isinstance(earnings_days, (int, float)) and earnings_days >= 0:
        evidence.append({"type": "earnings_proximity", "note": f"earnings in {int(earnings_days)}d"})
        confirmations.append("earnings_proximity")

    if len(confirmations) >= 2:
        score = compute_score_from_evidence(evidence, bonuses={"no_duplicate": True})
        if isinstance(iv_rank, (int, float)) and iv_rank >= 0.7:
            score = max(0, min(100, score + 4))
        direction = "up" if rec_key in {"buy", "strong_buy", "outperform"} else "neutral"
        sig = Signal(
            ticker=ticker_symbol,
            signal_type="catalyst_watch",
            brain="Analyst",
            direction=direction,
            score_raw=score,
            confidence=score,
            priority="moderate" if score < 80 else "high",
            reason="Analyst/catalyst sentiment signal",
            why_it_matters="Analyst and event catalysts can alter near-term flows and risk asymmetry.",
            confirmations=confirmations,
            suppressions=[],
            price=info.get("currentPrice"),
            change_pct=info.get("move_1d"),
            volume_ratio=info.get("volume_ratio"),
            metadata={"quote_timestamp": str(info.get("timestamp")), "source": "analyst", "earnings_days": earnings_days},
            action_bias="WATCH",
            evidence=evidence,
            cooldown_key=f"{ticker_symbol}_catalyst_watch_analyst",
            timestamp=datetime.now(),
        )
        signals.append(sig)

    if isinstance(earnings_days, (int, float)) and 0 <= earnings_days <= earnings_window:
        catalyst_evidence: List[Dict[str, Any]] = [
            {"type": "earnings_catalyst", "note": f"earnings in {int(earnings_days)}d"},
        ]
        catalyst_confirmations = ["earnings_proximity"]
        if isinstance(target_mean, (int, float)) and isinstance(current_price, (int, float)) and current_price > 0:
            upside = (target_mean - current_price) / current_price
            if upside >= 0.08:
                catalyst_evidence.append({"type": "analyst_target_upside", "note": f"target upside {upside:.1%}"})
                catalyst_confirmations.append("target_upside")
        if rec_key in {"buy", "strong_buy", "outperform"}:
            catalyst_evidence.append({"type": "analyst_key", "note": str(rec_key)})
            catalyst_confirmations.append("rating_support")

        if len(catalyst_confirmations) >= 2:
            cat_score = compute_score_from_evidence(catalyst_evidence, bonuses={"no_duplicate": True}, base_score=55)
            if isinstance(iv_rank, (int, float)) and iv_rank >= 0.7:
                cat_score = min(100, cat_score + 5)
                catalyst_confirmations.append("volatility_expansion")

            signals.append(
                Signal(
                    ticker=ticker_symbol,
                    signal_type="earnings_catalyst",
                    brain="Analyst",
                    direction="up" if rec_key in {"buy", "strong_buy", "outperform"} else "neutral",
                    score_raw=cat_score,
                    confidence=cat_score,
                    priority="high" if cat_score >= 75 else "strong",
                    reason="Earnings-window catalyst setup with analyst support",
                    why_it_matters="Event-driven setups can create asymmetric moves, but require tighter risk management.",
                    confirmations=catalyst_confirmations,
                    suppressions=[],
                    price=info.get("currentPrice"),
                    change_pct=info.get("move_1d"),
                    volume_ratio=info.get("volume_ratio"),
                    metadata={
                        "quote_timestamp": str(info.get("timestamp")),
                        "source": "analyst",
                        "earnings_days": earnings_days,
                        "earnings_risk_window_days": earnings_window,
                        "iv_rank": iv_rank,
                    },
                    action_bias="WATCH",
                    evidence=catalyst_evidence,
                    cooldown_key=f"{ticker_symbol}_earnings_catalyst_analyst",
                    timestamp=datetime.now(),
                )
            )

    return signals
