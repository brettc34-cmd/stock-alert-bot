"""Buffett brain (simplified).

This brain checks for quality/value pullbacks based on simple heuristics.
It returns Signal objects similar to the quant brain.
"""
from typing import Dict, Any, List
from datetime import datetime

from engine.signal_models import Signal
from engine.scoring_engine import compute_score_from_evidence


def analyze(ticker_symbol: str, info: Dict[str, Any], anchor_entry: Dict[str, Any], config: Dict[str, Any]) -> List[Signal]:
    signals = []

    # Simplified heuristics: look for dividend yield or stable cashflow proxy
    current_price = info.get("currentPrice")
    trailing_pe = info.get("trailingPE")
    dividend_yield = info.get("dividendYield")
    recent_high = info.get("recent_high")
    ma20 = info.get("ma20")
    ma50 = info.get("ma50")
    earnings_days = info.get("earnings_days")

    if current_price is None:
        return signals

    evidence = []
    confirmations = []
    drawdown = None
    if recent_high and current_price and recent_high > 0:
        drawdown = (recent_high - current_price) / recent_high
        # Trigger dip when price is at least 6% below recent high (<= 94% of high).
        if 0.06 <= drawdown <= 0.22:
            evidence.append({"type": "quality_dip", "note": f"drawdown={drawdown:.1%}"})
            confirmations.append("quality_dip")

    near_support = False
    if isinstance(ma20, (int, float)) and ma20 > 0 and abs(current_price - ma20) / ma20 <= 0.02:
        near_support = True
    if isinstance(ma50, (int, float)) and ma50 > 0 and abs(current_price - ma50) / ma50 <= 0.02:
        near_support = True
    if near_support:
        evidence.append({"type": "pullback_support", "note": "price near MA20/MA50 support zone"})
        confirmations.append("pullback_into_support")

    # Placeholder thesis-break check: severe trend damage and no value anchors.
    no_thesis_break = True
    if drawdown is not None and drawdown > 0.25 and not dividend_yield and (not trailing_pe or trailing_pe > 30):
        no_thesis_break = False
    if no_thesis_break:
        evidence.append({"type": "no_thesis_break", "note": "no clear thesis-break flags"})
        confirmations.append("no_thesis_break")
    if dividend_yield and dividend_yield > 0.02:
        evidence.append({"type": "buffett_dividend", "note": f"yield={dividend_yield:.2%}"})
        confirmations.append("quality_income_support")
    if trailing_pe and trailing_pe < 15:
        evidence.append({"type": "buffett_cheap_pe", "note": f"pe={trailing_pe}"})
        confirmations.append("valuation_improving")

    has_dip = "quality_dip" in confirmations
    has_secondary_quality = any(
        c in confirmations for c in {"pullback_into_support", "quality_income_support", "valuation_improving"}
    )
    if len(confirmations) >= 2 and has_dip and has_secondary_quality:
        score = compute_score_from_evidence(
            evidence,
            bonuses={"no_earnings_nearby": (earnings_days is None or earnings_days > config.get("earnings_risk_window_days", 7)), "no_duplicate": True},
            base_score=50,
        )
        label = "quality_dip" if dividend_yield or trailing_pe else "technical_dip_candidate"
        sig = Signal(
            ticker=ticker_symbol,
            signal_type=label,
            brain="Buffett",
            direction="down",
            score_raw=score,
            confidence=score,
            priority="strong" if score >= 60 else "moderate",
            reason="Value/quality pullback candidate detected",
            why_it_matters="A controlled drawdown with intact thesis can improve long-term entry quality.",
            confirmations=confirmations,
            suppressions=[],
            price=current_price,
            change_pct=info.get("move_1d"),
            volume_ratio=info.get("volume_ratio"),
            metadata={
                "quote_timestamp": str(info.get("timestamp")),
                "source": "buffett",
                "earnings_days": earnings_days,
                "earnings_risk_window_days": config.get("earnings_risk_window_days", 7),
                "no_thesis_break": no_thesis_break,
                "min_confidence_override": 50,
            },
            action_bias="SCALE_IN",
            evidence=evidence,
            cooldown_key=f"{ticker_symbol}_{label}_buffett",
            timestamp=datetime.now(),
        )
        signals.append(sig)

    return signals
