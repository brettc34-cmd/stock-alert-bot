"""Market regime classification and signal policy helpers."""

from __future__ import annotations

from typing import Any, Dict


REGIME_RISK_ON = "risk_on"
REGIME_BALANCED = "balanced"
REGIME_RISK_OFF = "risk_off"


def classify_regime(macro: Dict[str, Any]) -> Dict[str, Any]:
    vix = macro.get("vix")
    spx_price = macro.get("spx_price")
    spx_ma200 = macro.get("spx_ma200")
    spx_return_20d = macro.get("spx_return_20d")
    curve = macro.get("yield_curve_10y_3m")
    credit = macro.get("credit_risk_proxy_20d")

    score = 0
    drivers = []

    if isinstance(vix, (int, float)):
        if vix >= 35:
            score -= 3
            drivers.append("crisis_vix")
        elif vix >= 28:
            score -= 2
            drivers.append("high_vix")
        elif vix <= 18:
            score += 1
            drivers.append("calm_vix")

    if isinstance(spx_price, (int, float)) and isinstance(spx_ma200, (int, float)) and spx_ma200 > 0:
        if spx_price < spx_ma200:
            score -= 2
            drivers.append("spx_below_ma200")
        else:
            score += 1
            drivers.append("spx_above_ma200")

    if isinstance(spx_return_20d, (int, float)):
        if spx_return_20d <= -0.05:
            score -= 2
            drivers.append("momentum_negative")
        elif spx_return_20d >= 0.05:
            score += 1
            drivers.append("momentum_positive")

    if isinstance(curve, (int, float)):
        if curve < 0:
            score -= 1
            drivers.append("curve_inversion")
        else:
            score += 1
            drivers.append("curve_positive")

    if isinstance(credit, (int, float)):
        if credit < -0.015:
            score -= 1
            drivers.append("credit_weak")
        elif credit > 0.015:
            score += 1
            drivers.append("credit_strong")

    if score <= -2:
        regime = REGIME_RISK_OFF
    elif score >= 2:
        regime = REGIME_RISK_ON
    else:
        regime = REGIME_BALANCED

    return {
        "regime": regime,
        "score": score,
        "drivers": drivers,
    }


def regime_allows_signal(signal_type: str, regime: str) -> bool:
    """Return whether a signal type should pass regime policy checks."""
    if regime == REGIME_RISK_OFF:
        # In risk-off, directional add-style signals are heavily filtered.
        return signal_type not in {"breakout", "trend_continuation", "buy_the_dip", "dip", "quality_dip", "growth_value"}
    if regime == REGIME_RISK_ON:
        return True
    # Balanced: allow all, downstream engines will still score/suppress.
    return True
