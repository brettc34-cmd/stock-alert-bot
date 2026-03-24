"""Soros brain.

Detects macro / narrative divergence signals using basic macro proxies.

This is a simplified implementation: it uses currency and rates info from yfinance
(ticker symbols like ^IRX for rates, DX-Y.NYB for dollar index) and compares
relative moves.
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

    rs = info.get("relative_strength_vs_benchmark")
    move_1d = info.get("move_1d")
    ma20 = info.get("ma20")
    ma50 = info.get("ma50")

    evidence: List[Dict[str, Any]] = []
    confirmations: List[str] = []

    # Primary: meaningful RS divergence vs benchmark.
    if isinstance(rs, (int, float)) and abs(rs) > 0.03:
        evidence.append({"type": "macro_divergence", "note": f"RS divergence {rs:.1%}"})
        confirmations.append("macro_alignment" if rs > 0 else "macro_divergence")

    # Supporting: confirming price move on the same day.
    if isinstance(move_1d, (int, float)) and abs(move_1d) >= 0.01:
        evidence.append({"type": "quant_move_anomaly", "note": f"daily move {move_1d:.2%}"})
        confirmations.append("price_move_aligned")

    # Supporting: MA technical structure alignment.
    if ma20 and ma50 and current_price:
        if current_price > ma20 > ma50:
            evidence.append({"type": "trend_ma_align", "note": "price above key MAs"})
            confirmations.append("technical_alignment")
        elif current_price < ma20 < ma50:
            evidence.append({"type": "trend_ma_align", "note": "price below key MAs"})
            confirmations.append("bearish_ma_alignment")

    # Need at least macro divergence + one confirming condition to fire.
    if len(evidence) >= 2 and any(e.get("type") == "macro_divergence" for e in evidence):
        score = compute_score_from_evidence(evidence, bonuses={"no_duplicate": True})
        direction = "down" if (rs or 0) < 0 else "up"
        sig = Signal(
            ticker=ticker_symbol,
            signal_type="macro_divergence",
            brain="Soros",
            direction=direction,
            score_raw=score,
            confidence=score,
            priority="strong" if score >= 60 else "moderate",
            reason="Macro/narrative divergence with technical confirmation",
            why_it_matters="Cross-asset divergence plus price momentum often signals regime risk or asymmetric setup changes.",
            confirmations=confirmations,
            suppressions=[],
            price=current_price,
            change_pct=move_1d,
            volume_ratio=info.get("volume_ratio"),
            metadata={"quote_timestamp": str(info.get("timestamp")), "source": "soros", "rs": rs},
            action_bias="HIGH_CAUTION" if (rs or 0) < 0 else "WATCH",
            evidence=evidence,
            cooldown_key=f"{ticker_symbol}_macro_divergence_soros",
            timestamp=datetime.now(),
        )
        signals.append(sig)

    return signals
