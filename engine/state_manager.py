"""Premium state initialization and persistence layer.

Ensures state dictionary always has required keys and valid defaults,
preventing KeyError and maintaining consistent behavior across runs.
"""

from datetime import datetime, timezone
from typing import Dict, Any


PREMIUM_STATE_SCHEMA = {
    # Core tracking
    "last_run": None,  # Will be set to current ISO string
    "last_reset_date": "",  # YYYY-MM-DD format
    "errors": 0,
    "last_error": None,
    "error_details": [],
    
    # Suppression tracking
    "suppression_counts": {},
    "suppressed_signals": [],
    
    # Cycle metrics
    "cycle_metrics": {},
    
    # Signal state tracking
    "sent_signals": {},
    "cooldowns": {},
    "volume_alerts_sent": {},
    
    # Anchors (separate but related)
    # "anchor": ticker -> {"anchor": price, "next_up": price, "next_down": price}
}


def initialize_premium_state(existing_state: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Initialize or upgrade state dictionary to premium grade.
    
    Args:
        existing_state: Existing state dict (can be None or incomplete)
    
    Returns:
        Complete state dict with all required keys
    """
    if existing_state is None:
        existing_state = {}
    
    state = dict(existing_state)  # Copy to avoid mutating input
    
    # Ensure all premium schema keys exist
    for key, default_value in PREMIUM_STATE_SCHEMA.items():
        if key not in state:
            if default_value is not None:
                state[key] = default_value
            elif key == "last_run":
                state[key] = datetime.now(timezone.utc).isoformat()
            elif key == "suppression_counts":
                state[key] = {}
            elif key == "cycle_metrics":
                state[key] = {}
            elif key == "sent_signals":
                state[key] = {}
            elif key == "cooldowns":
                state[key] = {}
            elif key == "error_details":
                state[key] = []
            elif key == "suppressed_signals":
                state[key] = []
    
    # Type validation and repair
    if not isinstance(state.get("suppression_counts"), dict):
        state["suppression_counts"] = {}
    
    if not isinstance(state.get("cycle_metrics"), dict):
        state["cycle_metrics"] = {}
    
    if not isinstance(state.get("sent_signals"), dict):
        state["sent_signals"] = {}
    
    if not isinstance(state.get("cooldowns"), dict):
        state["cooldowns"] = {}
    
    if not isinstance(state.get("error_details"), list):
        state["error_details"] = []
    
    if not isinstance(state.get("suppressed_signals"), list):
        state["suppressed_signals"] = []
    
    # Recover from iso string format for last_run
    last_run_val = state.get("last_run")
    if last_run_val and isinstance(last_run_val, str):
        try:
            datetime.fromisoformat(last_run_val)  # Validate format
        except (ValueError, TypeError):
            state["last_run"] = datetime.now(timezone.utc).isoformat()
    elif not last_run_val:
        state["last_run"] = datetime.now(timezone.utc).isoformat()
    
    return state


def record_cycle_error(state: Dict[str, Any], error_msg: str, error_type: str = "generic") -> None:
    """
    Record an error in state for observability.
    
    Args:
        state: State dictionary
        error_msg: Error message
        error_type: Classification of error
    """
    error_details = state.get("error_details", [])
    if not isinstance(error_details, list):
        error_details = []
    
    error_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": error_type,
        "message": error_msg,
    }
    error_details.append(error_record)
    
    # Keep last 100 errors
    state["error_details"] = error_details[-100:]
    state["errors"] = state.get("errors", 0) + 1
    state["last_error"] = error_msg


def update_cycle_metrics(
    state: Dict[str, Any],
    raw_count: int,
    approved_count: int,
    sent_count: int,
    webhook_sent_count: int,
    persist_failed_count: int,
    suppressed_counts: Dict[str, int],
    regime: str = "",
    regime_drivers: list = None,
    event_risk_active: bool = False,
) -> None:
    """
    Update cycle metrics in state for observability and analytics.
    """
    state.setdefault("cycle_metrics", {}).update({
        "raw_signal_count": raw_count,
        "approved_signal_count": approved_count,
        "sent_signal_count": sent_count,
        "webhook_sent_count": webhook_sent_count,
        "persist_failed_count": persist_failed_count,
        "total_suppressed": sum(suppressed_counts.values()),
        "suppressed_by_reason": dict(suppressed_counts),
        "market_regime": regime,
        "regime_drivers": regime_drivers or [],
        "event_risk_active": event_risk_active,
        "cycle_timestamp": datetime.now(timezone.utc).isoformat(),
    })
    state["last_run"] = datetime.now(timezone.utc).isoformat()


def safe_get_anchor(state: Dict[str, Any], anchors: Dict[str, Dict[str, float]], ticker: str) -> Dict[str, float]:
    """
    Safely retrieve or initialize anchor for a ticker.
    """
    if ticker not in anchors:
        anchors[ticker] = {"anchor": 0.0, "next_up": 0.0, "next_down": 0.0}
    return anchors[ticker]


def sanitize_state_for_json(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Remove any datetime objects or non-serializable values before JSON persistence.
    """
    sanitized = {}
    for key, value in state.items():
        if isinstance(value, datetime):
            sanitized[key] = value.isoformat()
        elif isinstance(value, dict):
            sanitized[key] = {k: v.isoformat() if isinstance(v, datetime) else v for k, v in value.items()}
        elif isinstance(value, list):
            santized_list = []
            for item in value:
                if isinstance(item, dict):
                    santized_list.append({k: v.isoformat() if isinstance(v, datetime) else v for k, v in item.items()})
                elif isinstance(item, datetime):
                    santized_list.append(item.isoformat())
                else:
                    santized_list.append(item)
            sanitized[key] = santized_list
        else:
            sanitized[key] = value
    return sanitized


__all__ = [
    "initialize_premium_state",
    "record_cycle_error",
    "update_cycle_metrics",
    "safe_get_anchor",
    "sanitize_state_for_json",
    "PREMIUM_STATE_SCHEMA",
]
