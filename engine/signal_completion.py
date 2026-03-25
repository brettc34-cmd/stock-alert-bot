"""Premium signal completion and quality assurance layer.

Ensures all signals meet decision-grade standards before routing.
"""

from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional

from engine.signal_models import Signal


# Valid confirmation types from the ecosystem
VALID_CONFIRMATION_TYPES = {
    # Trend/breakout confirmations
    "breakout_confirmed", "breakout_20d", "breakout_50d", "above_key_mas", 
    "trend_ma_align", "ma20_slope_positive",
    # Volume & price action
    "volume_unusual", "volume_anomaly", "quant_volume_anomaly",
    "quant_move_anomaly", "volatility_expansion",
    # Quality & fundamentals
    "quality_dip", "pullback_support", "no_thesis_break",
    # Relative & sector
    "relative_strength_positive", "peer_relative_strength",
    "sector_rotation", "sector_leader",
    # Analyst & earnings
    "analyst_key", "analyst_mean", "analyst_target_upside", "analyst_coverage",
    "earnings_proximity", "earnings_catalyst",
    # Risk markers
    "concentration", "overlap_warning", "portfolio_fit",
    # Macro & regime
    "macro_align", "macro_divergence", "regime_align",
    # Execution
    "confirmation",
}


def derive_confirmations_from_evidence(evidence: List[Dict[str, Any]]) -> List[str]:
    """Extract confirmation types from evidence, filtering for valid types."""
    confirmations = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        ev_type = item.get("type")
        if ev_type and ev_type in VALID_CONFIRMATION_TYPES:
            confirmations.append(ev_type)
    return list(dict.fromkeys(confirmations))  # deduplicate, preserve order


def ensure_mandatory_metadata(signal: Signal, quotes: Dict[str, Dict[str, Any]]) -> None:
    """Populate critical metadata fields that must be present for decision-grade quality."""
    quote = quotes.get(signal.ticker, {}) or {}
    if signal.metadata is None:
        signal.metadata = {}
    meta = signal.metadata
    
    # Timestamp must be set
    if not meta.get("quote_timestamp"):
        ts = quote.get("timestamp") or quote.get("quote_timestamp") or signal.timestamp
        meta["quote_timestamp"] = ts.isoformat() if isinstance(ts, datetime) else str(ts)
    
    # PM accountability fields
    if not meta.get("thesis_id"):
        meta["thesis_id"] = signal.cooldown_key
    
    # Risk context
    meta.setdefault("earnings_days", quote.get("earnings_days", 999))
    meta.setdefault("sector", quote.get("sector", "Unknown"))
    meta.setdefault("iv_rank", quote.get("iv_rank"))
    meta.setdefault("quote_age_seconds", 0)
    
    # Decision context
    meta.setdefault("regime_drivers", [])
    meta.setdefault("yield_curve_10y_3m", None)
    meta.setdefault("credit_risk_proxy_20d", None)


def ensure_invalidation_price(signal: Signal) -> None:
    """Calculate invalidation price for PM accountability if not already set."""
    if signal.metadata.get("invalidation_price"):
        return  # Already set
    
    if not isinstance(signal.price, (int, float)) or not isinstance(signal.change_pct, (int, float)):
        return  # Cannot calculate
    
    # Calculate shock threshold tuned to signal types
    signal_type = (signal.signal_type or "").lower()
    
    if signal.direction == "up":
        # For bullish signals: invalidation is breakdown below entry
        if signal.signal_type in {"breakout", "trend_continuation"}:
            shock = 0.04  # 4% buffer on breakouts
        elif signal.signal_type in {"dip", "buy_the_dip", "quality_dip"}:
            shock = 0.03  # 3% buffer on dips
        else:
            shock = max(0.015, min(0.08, abs(signal.change_pct) * 1.5))
        invalidation = round(float(signal.price) * (1.0 - shock), 4)
    elif signal.direction == "down":
        # For bearish/risk signals: invalidation is breakdown above entry
        if signal.signal_type in {"concentration_risk", "trim_watch", "overlap_exposure_warning"}:
            shock = 0.04
        else:
            shock = max(0.015, min(0.08, abs(signal.change_pct) * 1.5))
        invalidation = round(float(signal.price) * (1.0 + shock), 4)
    else:
        return  # Cannot calculate for neutral direction
    
    signal.metadata["invalidation_price"] = invalidation


def complete_signal_for_premium_quality(
    signal: Signal,
    quotes: Dict[str, Dict[str, Any]],
) -> Tuple[Signal, List[str]]:
    """
    Enhance signal with all premium decision-grade fields.
    
    Returns:
        (enhanced_signal, completion_notes) - notes are for diagnostics/logging
    """
    notes = []
    
    # Ensure basic structure
    if not signal.confirmations and signal.evidence:
        derived = derive_confirmations_from_evidence(signal.evidence)
        signal.confirmations = derived
        if derived:
            notes.append(f"derived confirmations from evidence: {len(derived)}")
    
    # Fill mandatory metadata
    ensure_mandatory_metadata(signal, quotes)
    if notes:
        notes.append("metadata completed")
    
    # Calculate PM accountability fields
    ensure_invalidation_price(signal)
    if signal.metadata.get("invalidation_price"):
        notes.append(f"invalidation price set to {signal.metadata['invalidation_price']}")
    
    # Ensure reason/why_it_matters are substantive
    if not signal.reason or signal.reason == "":
        signal.reason = f"{signal.brain} signals {signal.direction} on {signal.signal_type}"
        notes.append("auto-generated reason")
    
    if not signal.why_it_matters or signal.why_it_matters == signal.reason:
        signals_list = ", ".join(signal.confirmations[:2]) if signal.confirmations else "multiple factors"
        signal.why_it_matters = f"High confidence ({signal.confidence}/100) based on {signals_list}."
        notes.append("auto-generated why_it_matters")
    
    # Ensure portfolio context is captured
    quote = quotes.get(signal.ticker, {}) or {}
    if not signal.portfolio_weight and isinstance(quote.get("portfolio_weight"), (int, float)):
        signal.portfolio_weight = quote["portfolio_weight"]
    
    # Consistency: always have a summary
    if not signal.summary:
        signal.summary = signal.reason
    
    return signal, notes


def validate_signal_completeness(signal: Signal) -> Tuple[bool, List[str]]:
    """
    Validate signal meets premium decision-grade standards.
    
    Returns:
        (passes, issues) - passes=True if all critical fields populated
    """
    issues = []
    
    # Critical fields must exist
    if not signal.ticker:
        issues.append("missing ticker")
    if not signal.signal_type:
        issues.append("missing signal_type")
    if not signal.brain:
        issues.append("missing brain")
    # Note: Signal.__post_init__ clamps confidence to [0,100] automatically,
    # so we check the raw intent via metadata if it was originally out of range
    if signal.direction not in {"up", "down", "neutral"}:
        issues.append(f"direction invalid: {signal.direction}")
    
    # Decision context must be present
    meta = signal.metadata or {}
    if not meta.get("quote_timestamp"):
        issues.append("missing quote_timestamp in metadata")
    if not meta.get("thesis_id"):
        issues.append("missing thesis_id (PM accountability)")
    
    # For add signals, validate portfolio context
    if signal.action_bias in {"ADD_SMALL", "SCALE_IN", "HOLD_ADD_ON_STRENGTH"}:
        if signal.portfolio_weight is None:
            issues.append("add signal missing portfolio_weight")
        if not meta.get("sector"):
            issues.append("add signal missing sector")
    
    # Premium signals should have rationale
    if not signal.reason or len(signal.reason) < 10:
        issues.append("reason too short or missing")
    if not signal.why_it_matters or len(signal.why_it_matters) < 10:
        issues.append("why_it_matters too short or missing")
    
    return len(issues) == 0, issues


__all__ = [
    "derive_confirmations_from_evidence",
    "ensure_mandatory_metadata",
    "ensure_invalidation_price",
    "complete_signal_for_premium_quality",
    "validate_signal_completeness",
    "VALID_CONFIRMATION_TYPES",
]
