"""Lynch brain.

Focuses on growth metrics and valuation reset signals.
"""

from typing import Dict, Any, List
from datetime import datetime

from engine.signal_models import Signal
from engine.scoring_engine import compute_score_from_evidence


def analyze(ticker_symbol: str, info: Dict[str, Any], anchor_entry: Dict[str, Any], config: Dict[str, Any]) -> List[Signal]:
    signals: List[Signal] = []

    current_price = info.get("currentPrice")
    if current_price is None:
        return signals

    # Use revenue growth proxies if available
    # yfinance provides 'revenueGrowth' as a float
    revenue_growth = info.get("revenueGrowth")
    peg_ratio = info.get("pegRatio")
    move_1d = info.get("move_1d")
    ma20 = info.get("ma20")
    ma50 = info.get("ma50")

    evidence: List[Dict[str, Any]] = []
    if isinstance(revenue_growth, (int, float)) and revenue_growth > 0.15:
        evidence.append({"type": "growth", "note": f"rev growth {revenue_growth:.0%}"})
    if isinstance(peg_ratio, (int, float)) and peg_ratio < 2.0:
        evidence.append({"type": "value", "note": f"PEG {peg_ratio:.2f}"})

    # Graceful proxy path when fundamentals are partially missing.
    if not isinstance(revenue_growth, (int, float)) and isinstance(move_1d, (int, float)) and move_1d > 0.015:
        evidence.append({"type": "growth", "note": f"momentum proxy {move_1d:.2%}"})
    if not isinstance(peg_ratio, (int, float)):
        pe = info.get("trailingPE")
        if isinstance(pe, (int, float)) and 0 < pe < 25:
            evidence.append({"type": "value", "note": f"PE proxy {pe:.2f}"})

    if isinstance(ma20, (int, float)) and isinstance(ma50, (int, float)) and current_price > ma20 > ma50:
        evidence.append({"type": "trend_ma_align", "note": "technical trend support"})

    evidence_types = {e.get("type") for e in evidence}
    if "growth" in evidence_types and "value" in evidence_types:
        score = compute_score_from_evidence(evidence, bonuses={"no_duplicate": True})
        sig = Signal(
            ticker=ticker_symbol,
            signal_type="growth_value",
            brain="Lynch",
            direction="up",
            score_raw=score,
            confidence=score,
            priority="moderate",
            reason="Growth with reasonable valuation detected",
            why_it_matters="Growth at reasonable valuation can support long runway compounding.",
            confirmations=sorted(evidence_types),
            suppressions=[],
            price=current_price,
            change_pct=info.get("move_1d"),
            volume_ratio=info.get("volume_ratio"),
            metadata={"quote_timestamp": str(info.get("timestamp")), "source": "lynch"},
            action_bias="WATCH",
            evidence=evidence,
            cooldown_key=f"{ticker_symbol}_growth_value_lynch",
            timestamp=datetime.now(),
        )
        signals.append(sig)

    return signals
