"""Daily/periodic summary generation for premium decision visibility."""

from collections import Counter
from typing import Any, Dict, List

from engine.signal_models import Signal


def build_daily_summary(signals: List[Signal], suppressed_counts: Dict[str, int], health: Dict[str, Any]) -> Dict[str, Any]:
    opportunities = [s for s in signals if s.signal_type in {"breakout", "quality_dip", "dip", "buy_the_dip", "trend_continuation"}]
    risks = [s for s in signals if s.signal_type in {"risk", "concentration_risk", "macro_divergence", "overlap_exposure_warning"}]

    by_brain = Counter(s.brain for s in signals)
    by_type = Counter(s.signal_type for s in signals)

    top_opportunities = sorted(opportunities, key=lambda s: s.confidence, reverse=True)[:5]
    top_risks = sorted(risks, key=lambda s: s.confidence, reverse=True)[:5]

    return {
        "top_opportunities": [
            {
                "ticker": s.ticker,
                "type": s.signal_type,
                "brain": s.brain,
                "confidence": s.confidence,
                "action_bias": s.action_bias,
                "portfolio_note": s.portfolio_note,
            }
            for s in top_opportunities
        ],
        "top_risks": [
            {
                "ticker": s.ticker,
                "type": s.signal_type,
                "brain": s.brain,
                "confidence": s.confidence,
                "action_bias": s.action_bias,
                "portfolio_note": s.portfolio_note,
            }
            for s in top_risks
        ],
        "signal_counts_by_brain": dict(by_brain),
        "signal_counts_by_type": dict(by_type),
        "suppressed_counts_by_reason": dict(suppressed_counts),
        "health": health,
    }
