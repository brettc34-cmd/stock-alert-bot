"""Druckenmiller brain (simplified momentum/trend checks).

Detects clean trend breakouts using moving average alignment available in info.
"""
from typing import Dict, Any, List
from datetime import datetime

from engine.signal_models import Signal
from engine.scoring_engine import compute_score_from_evidence


def analyze(ticker_symbol: str, info: Dict[str, Any], anchor_entry: Dict[str, Any], config: Dict[str, Any]) -> List[Signal]:
    signals = []

    current_price = info.get("currentPrice")
    ma20 = info.get("ma20")
    ma50 = info.get("ma50")
    high20 = info.get("high20")
    high50 = info.get("high50")
    volume_ratio = info.get("volume_ratio")
    ma20_slope = info.get("ma20_slope")
    rs = info.get("relative_strength_vs_benchmark")

    if current_price is None:
        return signals

    evidence = []
    confirmations = []
    if high20 and current_price >= high20:
        evidence.append({"type": "breakout_20d", "note": "20d high breakout"})
        confirmations.append("breakout_confirmed")
    if high50 and current_price >= high50:
        evidence.append({"type": "breakout_50d", "note": "50d high breakout"})
        confirmations.append("breakout_50d")
    if ma20 and ma50 and current_price > ma20 > ma50:
        evidence.append({"type": "trend_ma_align", "note": "price > MA20 > MA50"})
        confirmations.append("above_key_mas")
    if ma20_slope and ma20_slope > 0:
        evidence.append({"type": "ma20_slope_positive", "note": f"slope={ma20_slope:.3f}"})
        confirmations.append("ma20_slope_positive")
    if isinstance(volume_ratio, (int, float)) and volume_ratio >= config.get("strong_breakout_volume_ratio", 2.0):
        evidence.append({"type": "volume_unusual", "note": f"volume ratio {volume_ratio:.2f}"})
        confirmations.append("volume_ratio_above_threshold")
    if isinstance(rs, (int, float)) and rs > 0:
        evidence.append({"type": "relative_strength_positive", "note": f"rs delta {rs:.2%}"})
        confirmations.append("relative_strength_positive")

    # Require a concrete breakout trigger — MA alignment alone is not a signal.
    # Either price must be at a new 20d/50d high, or volume must be unusually high.
    has_breakout_trigger = (
        "breakout_confirmed" in confirmations or
        "volume_ratio_above_threshold" in confirmations
    )
    if len(confirmations) >= 2 and has_breakout_trigger:
        score = compute_score_from_evidence(
            evidence,
            bonuses={"no_duplicate": True, "strong_breakout": "breakout_confirmed" in confirmations and "volume_ratio_above_threshold" in confirmations},
            base_score=55,
        )
        sig = Signal(
            ticker=ticker_symbol,
            signal_type="breakout",
            brain="Druckenmiller",
            direction="up",
            score_raw=score,
            confidence=score,
            priority="high" if score >= 80 else "strong",
            reason="Trend continuation with breakout confirmation",
            why_it_matters="Aligned trend, momentum, and participation can support further upside continuation.",
            confirmations=confirmations,
            suppressions=[],
            price=current_price,
            change_pct=info.get("move_1d"),
            volume_ratio=volume_ratio,
            metadata={"quote_timestamp": str(info.get("timestamp")), "source": "druckenmiller"},
            action_bias="HOLD_ADD_ON_STRENGTH",
            evidence=evidence,
            cooldown_key=f"{ticker_symbol}_breakout_druckenmiller",
            timestamp=datetime.now(),
        )
        signals.append(sig)

    return signals
