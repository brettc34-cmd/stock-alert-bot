"""Alert routing helpers for final quality filter and dispatch reporting."""

import logging
from typing import Any, Dict, List, Tuple

from engine.signal_models import Signal
from engine import verification_engine

logger = logging.getLogger(__name__)


class AlertRouter:
    def __init__(self, state: Dict[str, Any], settings: Any, high_conviction_score: int = 80):
        self.state = state
        self.settings = settings
        self.high_conviction_score = high_conviction_score

    def filter_signals(self, signals: List[Signal]) -> Tuple[List[Signal], Dict[str, int]]:
        approved: List[Signal] = []
        suppressed: Dict[str, int] = {}

        for signal in signals:
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
                "suppressed ticker=%s brain=%s signal_type=%s reason=%s top_reasons=%s confidence=%s confirmations=%s",
                signal.ticker, signal.brain, signal.signal_type, reason,
                diag[:3], signal.confidence, signal.confirmations,
            )

        return approved, suppressed
