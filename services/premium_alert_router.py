"""Enhanced alert router with premium diagnostics and resilience.

Improves logging and error handling in the final quality gate.
"""

import logging
from typing import Any, Dict, List, Tuple

from engine.signal_models import Signal
from engine import verification_engine
from engine.verification_safety import validate_required_fields

logger = logging.getLogger(__name__)


class PremiumAlertRouter:
    """
    Enhanced router with premium-grade diagnostics and error resilience.
    
    This is a wrapper around the standard AlertRouter that adds:
    - Better error diagnostics
    - Resilience to signal malformation
    - Premium-grade logging
    - Signal quality attestation
    """
    
    def __init__(self, state: Dict[str, Any], settings: Any, high_conviction_score: int = 80):
        self.state = state
        self.settings = settings
        self.high_conviction_score = high_conviction_score
    
    def _audit_signal(self, signal: Signal) -> Tuple[bool, List[str]]:
        """Validate signal before verification."""
        issues = []
        
        # Check required fields
        valid, err = validate_required_fields(signal)
        if not valid:
            issues.append(f"validation_error:{err}")
            return False, issues
        
        # Check for evidence
        if not signal.confirmations and not signal.evidence:
            issues.append("no_confirmations_or_evidence")
        
        # Check for rationale
        if not signal.reason or len(signal.reason) < 5:
            issues.append("reason_too_short")
        
        # Check metadata
        meta = signal.metadata or {}
        if not meta.get("quote_timestamp"):
            issues.append("missing_quote_timestamp")
        
        # Check price context
        if signal.direction in {"up", "down"}:
            if not isinstance(signal.price, (int, float)) or signal.price <= 0:
                issues.append("invalid_price_context")
        
        return len(issues) == 0, issues
    
    def filter_signals(self, signals: List[Signal]) -> Tuple[List[Signal], Dict[str, int]]:
        """
        Filter signals with premium-grade quality assurance.
        
        Returns:
            (approved_signals, suppression_counts)
        """
        approved: List[Signal] = []
        suppressed: Dict[str, int] = {}
        
        for signal in signals:
            try:
                # Audit signal structure first
                audit_ok, audit_issues = self._audit_signal(signal)
                if not audit_ok:
                    for issue in audit_issues:
                        suppressed[issue] = suppressed.get(issue, 0) + 1
                    logger.debug(
                        "signal_audit_failed ticker=%s brain=%s issues=%s",
                        signal.ticker, signal.brain, audit_issues
                    )
                    continue
                
                # Standard verification
                ok, reason = verification_engine.verify_signal(
                    signal,
                    self.state,
                    min_threshold=self.settings.alert_min_confidence,
                    cooldown_seconds=int(self.settings.alert_cooldown_minutes * 60),
                    high_conviction_score=self.high_conviction_score,
                    min_confirmations_normal=self.settings.min_confirmations_normal,
                    min_confirmations_high=self.settings.min_confirmations_high,
                    stale_quote_max_age_seconds=self.settings.stale_quote_max_age_seconds,
                )
                
                if ok:
                    approved.append(signal)
                    continue
                
                signal.suppressions.append(reason)
                suppressed[reason] = suppressed.get(reason, 0) + 1
                verification_engine.mark_suppressed(self.state, reason)
                
                diag = verification_engine.suppression_diagnostics(
                    signal,
                    self.state,
                    min_threshold=self.settings.alert_min_confidence,
                    cooldown_seconds=int(self.settings.alert_cooldown_minutes * 60),
                    high_conviction_score=self.high_conviction_score,
                    min_confirmations_normal=self.settings.min_confirmations_normal,
                    min_confirmations_high=self.settings.min_confirmations_high,
                    stale_quote_max_age_seconds=self.settings.stale_quote_max_age_seconds,
                )
                
                logger.debug(
                    "signal_suppressed ticker=%s brain=%s signal_type=%s reason=%s confidence=%s confirmations=%s",
                    signal.ticker, signal.brain, signal.signal_type, reason,
                    signal.confidence, len(signal.confirmations or [])
                )
            
            except Exception as exc:
                logger.error(
                    "signal_routing_error ticker=%s brain=%s error=%s",
                    getattr(signal, "ticker", "UNKNOWN"),
                    getattr(signal, "brain", "UNKNOWN"),
                    str(exc),
                    exc_info=True
                )
                suppressed["internal_error"] = suppressed.get("internal_error", 0) + 1
        
        return approved, suppressed


__all__ = ["PremiumAlertRouter"]
