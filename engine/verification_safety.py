"""Enhanced verification utilities for premium decision-grade quality.

Adds defensive accessors and better error handling.
"""

from typing import Any, Optional, Dict, List


def safe_get_meta(signal: Any, key: str, default: Any = None) -> Any:
    """
    Safely get metadata value from signal with fallback.
    """
    try:
        meta = signal.metadata or {}
        val = meta.get(key, default)
        return val if val is not None else default
    except (AttributeError, TypeError):
        return default


def safe_get_float(signal: Any, attr_name: str, default: float = 0.0) -> float:
    """Safely retrieve and guarantee float type."""
    try:
        val = getattr(signal, attr_name, default)
        if val is None:
            return default
        return float(val)
    except (ValueError, TypeError, AttributeError):
        return default


def safe_get_list(signal: Any, attr_name: str, default: List = None) -> List:
    """Safely retrieve and guarantee list type."""
    if default is None:
        default = []
    try:
        val = getattr(signal, attr_name, default)
        if val is None:
            return default
        if isinstance(val, list):
            return val
        return list(val)
    except (TypeError, AttributeError):
        return default


def safe_get_dict(signal: Any, attr_name: str, default: Dict = None) -> Dict:
    """Safely retrieve and guarantee dict type."""
    if default is None:
        default = {}
    try:
        val = getattr(signal, attr_name, default)
        if val is None:
            return default
        if isinstance(val, dict):
            return val
        return default
    except (TypeError, AttributeError):
        return default


def safe_signal_fingerprint(signal: Any) -> str:
    """
    Create a signal fingerprint with defensive type checks.
    """
    try:
        ticker = str(signal.ticker or "NONE")
        signal_type = str(signal.signal_type or "unknown")
        brain = str(signal.brain or "unknown")
        direction = str(signal.direction or "neutral")
        
        confirmations = safe_get_list(signal, "confirmations", [])
        confirmation_key = "|".join(sorted(str(c) for c in confirmations))
        
        return f"{ticker}|{signal_type}|{brain}|{direction}|{confirmation_key}"
    except Exception:
        return "INVALID_SIGNAL"


def validate_required_fields(signal: Any) -> tuple[bool, str]:
    """
    Quick validation that signal has required fields for processing.
    
    Returns:
        (is_valid, error_message)
    """
    if not getattr(signal, "ticker", None):
        return False, "ticker_missing"
    if not getattr(signal, "signal_type", None):
        return False, "signal_type_missing"
    if not getattr(signal, "brain", None):
        return False, "brain_missing"
    if getattr(signal, "confidence", None) is None:
        return False, "confidence_missing"
    
    confidence = safe_get_float(signal, "confidence", 0)
    if confidence < 0 or confidence > 100:
        return False, f"confidence_out_of_range_{confidence}"
    
    direction = getattr(signal, "direction", None)
    if direction not in {"up", "down", "neutral"}:
        return False, f"direction_invalid_{direction}"
    
    return True, ""


__all__ = [
    "safe_get_meta",
    "safe_get_float",
    "safe_get_list",
    "safe_get_dict",
    "safe_signal_fingerprint",
    "validate_required_fields",
]
