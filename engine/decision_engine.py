"""Portfolio decision engine (PM/CIO layer).

Consumes signals and portfolio state to recommend actions (hold/add/trim).
"""

from typing import List, Dict

from engine.signal_models import Signal


ADD_BIASES = {"ADD_SMALL", "SCALE_IN", "HOLD_ADD_ON_STRENGTH"}


def _position_weight(portfolio: Dict[str, any], ticker: str, prices: Dict[str, float]) -> float:
    total = 0.0
    ticker_value = 0.0
    for p in portfolio.get("positions", []):
        t = p.get("ticker")
        value = p.get("shares", 0) * prices.get(t, 0)
        total += value
        if t == ticker:
            ticker_value = value
    if total <= 0:
        return 0.0
    return ticker_value / total


def _portfolio_total_value(portfolio: Dict[str, any], prices: Dict[str, float]) -> float:
    total_positions = 0.0
    for p in portfolio.get("positions", []):
        t = p.get("ticker")
        total_positions += p.get("shares", 0) * prices.get(t, 0)
    cash = float(portfolio.get("cash", 0.0) or 0.0)
    return total_positions + cash


def _target_weight(signal: Signal, weight: float, max_add_weight: float, trim_weight: float) -> float:
    """Map confidence and volatility context to a target position weight."""
    conf = max(0, min(100, int(signal.confidence or 0)))
    move_1d = signal.change_pct if isinstance(signal.change_pct, (int, float)) else 0.0
    vol_proxy = max(0.01, min(0.06, abs(move_1d) * 1.5 + 0.01))

    # Higher confidence increases risk budget, higher volatility decreases it.
    base_budget = (conf / 100.0) * 0.05
    risk_adjusted = base_budget * (0.02 / vol_proxy)
    risk_adjusted = max(0.005, min(0.04, risk_adjusted))

    if signal.signal_type in {"risk", "concentration_risk", "macro_divergence"}:
        return max(0.0, min(weight, trim_weight - 0.02))

    if signal.signal_type in {"breakout", "trend_continuation", "buy_the_dip", "dip", "quality_dip", "growth_value"}:
        target = weight + risk_adjusted
        return max(0.0, min(max_add_weight, target))

    return max(0.0, min(max_add_weight, weight))


def _infer_action_bias(signal: Signal, weight: float, max_add_weight: float = 0.15, trim_weight: float = 0.20) -> str:
    sig_type = signal.signal_type
    priority = signal.priority
    conflicting = bool(signal.metadata.get("conflicting_brains"))
    extended = bool(signal.metadata.get("extended"))

    if conflicting:
        return "HIGH_CAUTION"
    if sig_type in {"concentration_risk", "risk", "macro_divergence"}:
        return "REDUCE_RISK" if weight > trim_weight else "WATCH"
    if extended and weight > trim_weight:
        return "TRIM_WATCH"
    if sig_type in {"breakout", "trend_continuation"}:
        if weight > trim_weight:
            return "HOLD"
        if weight > max_add_weight:
            return "ADD_SMALL"
        return "HOLD_ADD_ON_STRENGTH" if priority in {"strong", "high"} else "WATCH"
    if sig_type in {"dip", "buy_the_dip", "quality_dip"}:
        if signal.metadata.get("no_thesis_break") is False:
            return "NO_ACTION"
        if weight > trim_weight:
            return "HOLD"
        return "SCALE_IN" if priority in {"strong", "high"} else "ADD_SMALL"
    return "WATCH"


def decide(signals: List[Signal], portfolio: Dict[str, any], prices: Dict[str, float]) -> List[Signal]:
    """Annotate signals with premium action bias using portfolio context."""
    max_add_weight = float(portfolio.get("rules", {}).get("max_position_weight_add", 0.15))
    trim_weight = float(portfolio.get("rules", {}).get("trim_warning_weight", 0.20))

    portfolio_value = _portfolio_total_value(portfolio, prices)

    for s in signals:
        weight = _position_weight(portfolio, s.ticker, prices)
        target_weight = _target_weight(s, weight, max_add_weight=max_add_weight, trim_weight=trim_weight)
        delta_weight = target_weight - weight
        target_notional = portfolio_value * target_weight if portfolio_value > 0 else 0.0
        delta_notional = portfolio_value * delta_weight if portfolio_value > 0 else 0.0

        s.portfolio_weight = weight
        s.metadata["max_add_weight"] = max_add_weight
        s.metadata["trim_warning_weight"] = trim_weight
        s.metadata["target_weight"] = round(target_weight, 4)
        s.metadata["delta_weight"] = round(delta_weight, 4)
        s.metadata["target_notional"] = round(target_notional, 2)
        s.metadata["delta_notional"] = round(delta_notional, 2)
        s.metadata["portfolio_value"] = round(portfolio_value, 2)
        s.action_bias = _infer_action_bias(s, weight, max_add_weight=max_add_weight, trim_weight=trim_weight)

        if weight > trim_weight and s.action_bias in ADD_BIASES:
            s.action_bias = "HOLD"
        if weight > trim_weight:
            s.portfolio_note = f"{s.ticker} weight {weight:.1%} is above trim watch threshold."
        elif weight > max_add_weight:
            s.portfolio_note = f"{s.ticker} weight {weight:.1%} is above ideal add size."
        else:
            s.portfolio_note = f"{s.ticker} weight {weight:.1%} supports incremental adds."

    return signals
