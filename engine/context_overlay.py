"""Contextual confidence overlays for premium signal quality."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from engine.signal_models import Signal


ADD_SIGNAL_TYPES = {"breakout", "trend_continuation", "buy_the_dip", "dip", "quality_dip", "growth_value"}
RISK_SIGNAL_TYPES = {"risk", "concentration_risk", "macro_divergence"}


def _sector_strength_for_signal(signal: Signal, macro: Dict[str, Any]) -> float | None:
    sector = (signal.metadata or {}).get("sector")
    if not isinstance(sector, str):
        return None
    sector_returns = macro.get("sector_returns_20d") or {}
    value = sector_returns.get(sector)
    return float(value) if isinstance(value, (int, float)) else None


def _peer_relative_strength(signal: Signal) -> float | None:
    value = (signal.metadata or {}).get("peer_relative_strength")
    return float(value) if isinstance(value, (int, float)) else None


def apply_context_overlays(
    signals: Iterable[Signal],
    *,
    macro: Dict[str, Any],
    regime: str,
    brain_multipliers: Dict[str, float] | None = None,
) -> List[Signal]:
    """Adjust confidence using macro, sector, peer, volatility, and outcome context."""
    brain_multipliers = brain_multipliers or {}
    out: List[Signal] = []

    for signal in signals:
        adjustments: List[str] = []
        conf = int(signal.confidence)
        sig_type = signal.signal_type

        if regime == "risk_off" and sig_type in ADD_SIGNAL_TYPES:
            conf -= 12
            adjustments.append("regime_risk_off_penalty")
        elif regime == "risk_off" and sig_type in RISK_SIGNAL_TYPES:
            conf += 8
            adjustments.append("regime_risk_off_risk_bonus")
        elif regime == "risk_on" and sig_type in ADD_SIGNAL_TYPES:
            conf += 5
            adjustments.append("regime_risk_on_add_bonus")

        vix = macro.get("vix")
        if isinstance(vix, (int, float)) and vix >= 30 and sig_type in ADD_SIGNAL_TYPES:
            conf -= 8
            adjustments.append("high_vix_penalty")

        curve = macro.get("yield_curve_10y_3m")
        if isinstance(curve, (int, float)) and curve < 0 and sig_type in ADD_SIGNAL_TYPES:
            conf -= 4
            adjustments.append("curve_inversion_penalty")

        sector_strength = _sector_strength_for_signal(signal, macro)
        if isinstance(sector_strength, float):
            signal.metadata["sector_return_20d"] = sector_strength
            if sector_strength <= -0.03 and sig_type in ADD_SIGNAL_TYPES:
                conf -= 6
                adjustments.append("sector_weakness_penalty")
            elif sector_strength >= 0.03 and sig_type in ADD_SIGNAL_TYPES:
                conf += 4
                adjustments.append("sector_strength_bonus")

        peer_rs = _peer_relative_strength(signal)
        if isinstance(peer_rs, float):
            if peer_rs <= -0.03 and sig_type in ADD_SIGNAL_TYPES:
                conf -= 5
                adjustments.append("peer_relative_weakness_penalty")
            elif peer_rs >= 0.03 and sig_type in ADD_SIGNAL_TYPES:
                conf += 5
                adjustments.append("peer_relative_strength_bonus")

        iv_rank = (signal.metadata or {}).get("iv_rank")
        if isinstance(iv_rank, (int, float)):
            if iv_rank >= 0.7 and sig_type in {"breakout", "trend_continuation"}:
                conf -= 4
                adjustments.append("high_iv_penalty")
            elif iv_rank <= 0.25 and sig_type in {"breakout", "trend_continuation"}:
                conf += 2
                adjustments.append("low_iv_bonus")

        multiplier = float(brain_multipliers.get(signal.brain, 1.0))
        if multiplier != 1.0:
            raw_scaled = int(round(conf * multiplier))
            conf = raw_scaled
            adjustments.append(f"brain_multiplier_{multiplier:.2f}")
            signal.metadata["brain_weight_multiplier"] = multiplier

        signal.confidence = max(0, min(100, conf))
        signal.score_raw = signal.confidence
        signal.metadata["context_adjustments"] = adjustments
        signal.metadata["market_regime"] = regime
        out.append(signal)

    return out
