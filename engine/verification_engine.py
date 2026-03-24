"""Verification engine.

Provides final alert quality filtering with suppression taxonomy.
"""
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, List

from engine import cooldowns
from engine.scoring_engine import passes_min_alert_threshold


SUPPRESSION_REASONS = {
    "cooldown_active",
    "stale_data",
    "low_confidence",
    "insufficient_confirmations",
    "conflicting_brains",
    "earnings_risk_nearby",
    "already_overweight",
    "data_error",
    "market_closed_rule",
    "duplicate_state",
    "regime_mismatch",
    "event_risk_window",
}


def is_data_fresh(price_timestamp_age_seconds: float, max_age_seconds: int = 180) -> bool:
    return price_timestamp_age_seconds <= max_age_seconds


def passes_min_confidence(confidence: int, min_threshold: int) -> bool:
    return passes_min_alert_threshold(confidence, min_threshold)


def _signal_fingerprint(signal: Any) -> str:
    confirmation_key = "|".join(sorted(signal.confirmations or []))
    return f"{signal.ticker}|{signal.signal_type}|{signal.brain}|{signal.direction}|{confirmation_key}"


def _quote_age_seconds(signal: Any) -> float:
    quote_ts = (signal.metadata or {}).get("quote_timestamp")
    if quote_ts is None:
        return 10**9
    if isinstance(quote_ts, str):
        try:
            quote_ts = datetime.fromisoformat(quote_ts)
        except ValueError:
            return 10**9
    if not isinstance(quote_ts, datetime):
        return 10**9
    if quote_ts.tzinfo is None:
        quote_ts = quote_ts.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return max(0.0, (now - quote_ts).total_seconds())


def _required_confirmations(signal: Any, high_conviction_score: int, default_normal: int, default_high: int) -> int:
    if signal.signal_type in {"dip", "buy_the_dip", "quality_dip", "quant_anomaly", "unusual_volume"}:
        return 2
    return default_high if signal.confidence >= high_conviction_score else default_normal


def _is_quant_pass_through(signal: Any) -> bool:
    if signal.brain != "Quant":
        return False
    vol = signal.volume_ratio
    meta = signal.metadata or {}
    mz = meta.get("move_zscore")
    if not isinstance(mz, (int, float)):
        move_1d = signal.change_pct if isinstance(signal.change_pct, (int, float)) else 0.0
        mz = abs(move_1d) / 0.02 if move_1d else 0.0
    return (isinstance(vol, (int, float)) and vol >= 2.0) or (isinstance(mz, (int, float)) and mz >= 2.0)


def _is_risk_priority_bypass(signal: Any) -> bool:
    is_risk_signal = signal.signal_type in {
        "concentration_risk",
        "risk",
        "overlap_exposure_warning",
        "macro_divergence",
        "trim_watch",
    }
    if not is_risk_signal:
        return False
    meta = signal.metadata or {}
    trim_threshold = float(meta.get("trim_warning_weight", 0.2))
    overweight = (signal.portfolio_weight or 0.0) > trim_threshold
    extended = bool(meta.get("extended"))
    explicit = bool(meta.get("risk_priority_bypass"))
    return overweight or extended or explicit


def quality_gate(signal: Any, min_threshold: int, high_conviction_score: int, min_confirmations_normal: int, min_confirmations_high: int, stale_quote_max_age_seconds: int) -> Tuple[bool, str]:
    if not signal.ticker or not signal.signal_type or not signal.brain:
        return False, "data_error"
    if not passes_min_confidence(signal.confidence, min_threshold):
        return False, "low_confidence"

    required = _required_confirmations(signal, high_conviction_score, min_confirmations_normal, min_confirmations_high)
    if len(signal.confirmations or []) < required:
        return False, "insufficient_confirmations"

    age = _quote_age_seconds(signal)
    if not is_data_fresh(age, stale_quote_max_age_seconds):
        return False, "stale_data"

    return True, ""


def verify_signal(
    signal,
    state: Dict[str, Any],
    min_threshold: int = 50,
    cooldown_seconds: int = 60 * 90,
    high_conviction_score: int = 80,
    min_confirmations_normal: int = 2,
    min_confirmations_high: int = 3,
    stale_quote_max_age_seconds: int = 300,
    suppressed_signal_types_on_earnings: List[str] = None,
) -> Tuple[bool, str]:
    """Return (True, "") when the signal should be sent, else (False, reason)."""
    suppressed_signal_types_on_earnings = suppressed_signal_types_on_earnings or ["breakout", "trend_continuation", "buy_the_dip", "dip", "quality_dip", "growth_value"]

    effective_min_threshold = min_threshold
    meta = signal.metadata or {}
    if signal.brain == "Quant" and _is_quant_pass_through(signal):
        effective_min_threshold = min(effective_min_threshold, int(meta.get("min_confidence_override", 45)))
    if _is_risk_priority_bypass(signal):
        effective_min_threshold = 0

    ok, reason = quality_gate(
        signal,
        min_threshold=effective_min_threshold,
        high_conviction_score=high_conviction_score,
        min_confirmations_normal=min_confirmations_normal,
        min_confirmations_high=min_confirmations_high,
        stale_quote_max_age_seconds=stale_quote_max_age_seconds,
    )
    if not ok:
        return False, reason

    key = signal.cooldown_key or f"sig_{signal.ticker}"
    if cooldowns.is_on_cooldown(state, key, cooldown_seconds):
        return False, "cooldown_active"

    # stateful duplicate detection
    sent = state.setdefault("sent_signals", {})
    fp = _signal_fingerprint(signal)
    if sent.get(key) == fp:
        return False, "duplicate_state"

    # earnings risk guardrail for add/dip signals
    earnings_days = (signal.metadata or {}).get("earnings_days")
    if isinstance(earnings_days, (int, float)) and earnings_days >= 0:
        if signal.signal_type in suppressed_signal_types_on_earnings and earnings_days <= int((signal.metadata or {}).get("earnings_risk_window_days", 7)):
            return False, "earnings_risk_nearby"

    # Regime guardrail from context overlays.
    if signal.metadata.get("regime_blocked"):
        return False, "regime_mismatch"

    if signal.metadata.get("event_risk_blocked"):
        return False, "event_risk_window"

    if signal.metadata.get("conflicting_brains"):
        return False, "conflicting_brains"

    if (signal.portfolio_weight or 0.0) > float((signal.metadata or {}).get("trim_warning_weight", 0.2)) and signal.action_bias in {"ADD_SMALL", "SCALE_IN", "HOLD_ADD_ON_STRENGTH"}:
        return False, "already_overweight"

    return True, ""


def suppression_diagnostics(
    signal,
    state: Dict[str, Any],
    min_threshold: int = 50,
    cooldown_seconds: int = 60 * 90,
    high_conviction_score: int = 80,
    min_confirmations_normal: int = 2,
    min_confirmations_high: int = 3,
    stale_quote_max_age_seconds: int = 300,
    suppressed_signal_types_on_earnings: List[str] = None,
) -> List[str]:
    reasons: List[str] = []
    suppressed_signal_types_on_earnings = suppressed_signal_types_on_earnings or ["breakout", "trend_continuation", "buy_the_dip", "dip", "quality_dip", "growth_value"]

    if not signal.ticker or not signal.signal_type or not signal.brain:
        reasons.append("data_error")

    effective_min_threshold = min_threshold
    meta = signal.metadata or {}
    if signal.brain == "Quant" and _is_quant_pass_through(signal):
        effective_min_threshold = min(effective_min_threshold, int(meta.get("min_confidence_override", 45)))
    if _is_risk_priority_bypass(signal):
        effective_min_threshold = 0

    if not passes_min_confidence(signal.confidence, effective_min_threshold):
        reasons.append("low_confidence")

    required = _required_confirmations(signal, high_conviction_score, min_confirmations_normal, min_confirmations_high)
    if len(signal.confirmations or []) < required:
        reasons.append("insufficient_confirmations")

    age = _quote_age_seconds(signal)
    if not is_data_fresh(age, stale_quote_max_age_seconds):
        reasons.append("stale_data")

    key = signal.cooldown_key or f"sig_{signal.ticker}"
    if cooldowns.is_on_cooldown(state, key, cooldown_seconds):
        reasons.append("cooldown_active")

    sent = state.setdefault("sent_signals", {})
    fp = _signal_fingerprint(signal)
    if sent.get(key) == fp:
        reasons.append("duplicate_state")

    earnings_days = (signal.metadata or {}).get("earnings_days")
    if isinstance(earnings_days, (int, float)) and earnings_days >= 0:
        if signal.signal_type in suppressed_signal_types_on_earnings and earnings_days <= int((signal.metadata or {}).get("earnings_risk_window_days", 7)):
            reasons.append("earnings_risk_nearby")

    if signal.metadata.get("regime_blocked"):
        reasons.append("regime_mismatch")

    if signal.metadata.get("event_risk_blocked"):
        reasons.append("event_risk_window")

    if signal.metadata.get("conflicting_brains"):
        reasons.append("conflicting_brains")

    if (signal.portfolio_weight or 0.0) > float((signal.metadata or {}).get("trim_warning_weight", 0.2)) and signal.action_bias in {"ADD_SMALL", "SCALE_IN", "HOLD_ADD_ON_STRENGTH"}:
        reasons.append("already_overweight")

    return reasons


def mark_sent(signal, state: Dict[str, Any]) -> None:
    key = signal.cooldown_key or f"sig_{signal.ticker}"
    cooldowns.mark_sent(state, key)
    state.setdefault("sent_signals", {})[key] = _signal_fingerprint(signal)
    counts = state.setdefault("suppression_counts", {})
    for reason in signal.suppressions:
        counts[reason] = counts.get(reason, 0) + 1


def mark_suppressed(state: Dict[str, Any], reason: str) -> None:
    counts = state.setdefault("suppression_counts", {})
    counts[reason] = counts.get(reason, 0) + 1


__all__ = [
    "SUPPRESSION_REASONS",
    "is_data_fresh",
    "passes_min_confidence",
    "quality_gate",
    "verify_signal",
    "suppression_diagnostics",
    "mark_sent",
    "mark_suppressed",
]
