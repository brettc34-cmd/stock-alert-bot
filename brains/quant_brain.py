"""Quant brain helpers.

This module contains utilities for detecting abnormal volume/price moves and
for converting the existing ladder logic into a re-usable function that
returns human-readable messages and updated anchor data.
"""
from typing import Dict, Any, List
from datetime import datetime

from engine.signal_models import Signal
from engine.scoring_engine import compute_score_from_evidence


def process_ladder_and_volume(ticker_symbol: str, info: Dict[str, Any],
                              anchor_entry: Dict[str, float], config: Dict[str, Any],
                              state: Dict[str, Any], timestamp_text: str, day_progress: float) -> List[Signal]:
    """Run ladder crossing and volume projection checks and return Signal objects.

    Updates `anchor_entry` and `state` in-place and returns a list of
    `Signal` dataclass instances for downstream scoring/verification.
    """
    signals: List[Signal] = []

    current_price = info.get("currentPrice")
    current_volume = info.get("volume")
    average_volume = info.get("averageVolume")

    if current_price is None:
        return signals

    current_price = round(float(current_price), 2)

    ladder_step = config.get("ladder_step", 5)

    anchor = anchor_entry.get("anchor")
    next_up = anchor_entry.get("next_up")
    next_down = anchor_entry.get("next_down")

    old_anchor = anchor
    crossed_up_steps = []
    crossed_down_steps = []

    while current_price >= next_up:
        crossed_up_steps.append(next_up)
        anchor = round(anchor + ladder_step, 2)
        next_up = round(anchor + ladder_step, 2)
        next_down = round(anchor - ladder_step, 2)

    while current_price <= next_down:
        crossed_down_steps.append(next_down)
        anchor = round(anchor - ladder_step, 2)
        next_up = round(anchor + ladder_step, 2)
        next_down = round(anchor - ladder_step, 2)

    anchor_entry["anchor"] = anchor
    anchor_entry["next_up"] = next_up
    anchor_entry["next_down"] = next_down

    # Create ladder signals
    if crossed_up_steps:
        # Use mapped evidence types so scoring engine can weight them correctly.
        evidence = [{"type": "breakout_20d", "note": f"crossed ${step}"} for step in crossed_up_steps]
        vol_ratio = info.get("volume_ratio") or 0
        if vol_ratio >= 1.5:
            evidence.append({"type": "volume_unusual", "note": f"vol_ratio={vol_ratio:.2f}"})
        score_raw = compute_score_from_evidence(evidence, bonuses={"no_duplicate": True}, base_score=45)
        confs = ["ladder_breakout_up", "volume_confirming"] if vol_ratio >= 1.5 else ["ladder_breakout_up"]
        sig = Signal(
            ticker=ticker_symbol,
            signal_type="breakout",
            brain="Quant",
            direction="up",
            score_raw=score_raw,
            confidence=score_raw,
            priority="strong",
            reason=f"Crossed up ladder steps: {', '.join(str(s) for s in crossed_up_steps)}",
            why_it_matters="Price expansion across ladder levels can indicate momentum continuation.",
            confirmations=confs,
            suppressions=[],
            price=current_price,
            change_pct=info.get("move_1d"),
            volume_ratio=info.get("volume_ratio"),
            metadata={
                "quote_timestamp": str(info.get("timestamp")),
                "source": "quant_ladder",
                "min_confidence_override": 45,
                "move_zscore": info.get("move_zscore"),
            },
            action_bias="WATCH",
            evidence=evidence,
            cooldown_key=f"{ticker_symbol}_breakout_quant",
            timestamp=datetime.now(),
        )
        signals.append(sig)

    if crossed_down_steps:
        evidence = [{"type": "pullback_support", "note": f"crossed ${step}"} for step in crossed_down_steps]
        vol_ratio_down = info.get("volume_ratio") or 0
        if vol_ratio_down >= 1.5:
            evidence.append({"type": "volume_unusual", "note": f"vol_ratio={vol_ratio_down:.2f}"})
        score_raw = compute_score_from_evidence(evidence, bonuses={"no_duplicate": True}, base_score=45)
        confs_down = ["ladder_pullback_down", "volume_confirming"] if vol_ratio_down >= 1.5 else ["ladder_pullback_down"]
        sig = Signal(
            ticker=ticker_symbol,
            signal_type="dip",
            brain="Quant",
            direction="down",
            score_raw=score_raw,
            confidence=score_raw,
            priority="strong",
            reason=f"Crossed down ladder steps: {', '.join(str(s) for s in crossed_down_steps)}",
            why_it_matters="Controlled pullbacks can provide better entries when trend structure holds.",
            confirmations=confs_down,
            suppressions=[],
            price=current_price,
            change_pct=info.get("move_1d"),
            volume_ratio=info.get("volume_ratio"),
            metadata={
                "quote_timestamp": str(info.get("timestamp")),
                "source": "quant_ladder",
                "min_confidence_override": 45,
                "move_zscore": info.get("move_zscore"),
            },
            action_bias="WATCH",
            evidence=evidence,
            cooldown_key=f"{ticker_symbol}_dip_quant",
            timestamp=datetime.now(),
        )
        signals.append(sig)

    # Volume projection signal
    if current_volume is not None and average_volume is not None and day_progress > 0:
        projected_volume = current_volume / day_progress
        volume_trigger_level = average_volume * config.get("volume_threshold", 1.5)
        volume_triggered = projected_volume >= volume_trigger_level
        already_sent = state.get("volume_alerts_sent", {}).get(ticker_symbol, False)

        if volume_triggered and not already_sent:
            evidence = [
                {"type": "quant_volume_anomaly", "note": f"proj={projected_volume:,.0f}, lvl={volume_trigger_level:,.0f}"},
                {"type": "volume_unusual", "note": f"ratio={info.get('volume_ratio') or 0:.2f}"},
            ]
            # Add price-move evidence when volume coincides with a meaningful daily move.
            move = info.get("move_1d") or 0
            if abs(move) >= 0.01:
                evidence.append({"type": "quant_move_anomaly", "note": f"1d move={move:.2%}"})
            score_raw = compute_score_from_evidence(evidence, bonuses={"no_duplicate": True}, base_score=45)
            sig = Signal(
                ticker=ticker_symbol,
                signal_type="unusual_volume",
                brain="Quant",
                direction="up" if move > 0 else ("down" if move < 0 else "neutral"),
                score_raw=score_raw,
                confidence=score_raw,
                priority="moderate",
                reason="Projected full-day volume exceeds threshold",
                why_it_matters="Abnormal participation can confirm or invalidate trend breaks.",
                confirmations=["volume_unusual", "quant_volume_anomaly"] + (["price_move_confirming"] if abs(move) >= 0.01 else []),
                suppressions=[],
                price=current_price,
                change_pct=info.get("move_1d"),
                volume_ratio=info.get("volume_ratio"),
                metadata={
                    "quote_timestamp": str(info.get("timestamp")),
                    "source": "quant_volume",
                    "min_confidence_override": 45,
                    "move_zscore": info.get("move_zscore"),
                },
                action_bias="WATCH",
                evidence=evidence,
                cooldown_key=f"{ticker_symbol}_unusual_volume_quant",
                timestamp=datetime.now(),
            )
            signals.append(sig)
            state.setdefault("volume_alerts_sent", {})[ticker_symbol] = True

    # Move z-score proxy and volatility expansion used as a confirmation layer.
    move_1d = info.get("move_1d")
    if isinstance(move_1d, (int, float)) and abs(move_1d) >= 0.03:
        direction = "up" if move_1d > 0 else "down"
        evidence = [
            {"type": "quant_move_anomaly", "note": f"1d move={move_1d:.2%}"},
            {"type": "volatility_expansion", "note": "daily range expansion proxy"},
        ]
        score_raw = compute_score_from_evidence(evidence, base_score=45)
        signals.append(
            Signal(
                ticker=ticker_symbol,
                signal_type="quant_anomaly",
                brain="Quant",
                direction=direction,
                score_raw=score_raw,
                confidence=score_raw,
                priority="moderate" if score_raw < 80 else "high",
                reason="Standardized move/volatility anomaly detected",
                why_it_matters="Anomalies can confirm breakouts or flag unstable tape conditions.",
                confirmations=["quant_move_anomaly", "volatility_expansion"],
                suppressions=[],
                price=current_price,
                change_pct=move_1d,
                volume_ratio=info.get("volume_ratio"),
                metadata={
                    "quote_timestamp": str(info.get("timestamp")),
                    "source": "quant_anomaly",
                    "min_confidence_override": 45,
                    "move_zscore": info.get("move_zscore"),
                },
                action_bias="WATCH",
                evidence=evidence,
                cooldown_key=f"{ticker_symbol}_quant_anomaly_quant",
                timestamp=datetime.now(),
            )
        )

    return signals
