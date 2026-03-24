"""Dalio brain.

Monitors portfolio regime and concentration risk.

This simplified implementation uses portfolio weights.
"""

from typing import Dict, Any, List
from datetime import datetime, timezone

from engine.signal_models import Signal
from engine.scoring_engine import compute_score_from_evidence


def analyze(portfolio: Dict[str, Any], prices: Dict[str, float]) -> List[Signal]:
    signals: List[Signal] = []

    # Check concentration and overlap risk.
    total = 0.0
    sector_exposure: Dict[str, float] = {}
    for p in portfolio.get("positions", []):
        t = p.get("ticker")
        shares = p.get("shares", 0)
        price = prices.get(t, 0)
        value = shares * price
        total += value
        sector = p.get("sector") or "unknown"
        sector_exposure[sector] = sector_exposure.get(sector, 0.0) + value

    if total <= 0:
        return signals

    for p in portfolio.get("positions", []):
        t = p.get("ticker")
        shares = p.get("shares", 0)
        price = prices.get(t, 0)
        value = shares * price
        weight = value / total

        if weight > 0.22:
            evidence = [{"type": "concentration", "note": f"{weight:.0%}"}]
            score = compute_score_from_evidence(evidence, bonuses={"no_duplicate": True}, base_score=50)
            sig = Signal(
                ticker=t,
                signal_type="concentration_risk",
                brain="Dalio",
                direction="down",
                score_raw=score,
                confidence=score,
                priority="high",
                reason="Concentration risk above 25% of portfolio",
                why_it_matters="Overconcentration raises single-name downside and reduces portfolio flexibility.",
                confirmations=["position_concentration", "trim_watch"],
                suppressions=[],
                price=prices.get(t),
                portfolio_weight=weight,
                metadata={
                    "source": "dalio_pm",
                    "trim_warning_weight": 0.20,
                    "quote_timestamp": str(datetime.now(timezone.utc)),
                    "risk_priority_bypass": True,
                },
                action_bias="TRIM_WATCH",
                evidence=evidence,
                portfolio_note=f"Weight: {weight:.1%}",
                cooldown_key=f"{t}_concentration_risk_dalio",
                timestamp=datetime.now(),
            )
            signals.append(sig)
        elif weight > 0.20:
            evidence = [{"type": "concentration", "note": f"trim-watch {weight:.0%}"}]
            score = compute_score_from_evidence(evidence, bonuses={"no_duplicate": True}, base_score=50)
            signals.append(
                Signal(
                    ticker=t,
                    signal_type="trim_watch",
                    brain="Dalio",
                    direction="down",
                    score_raw=score,
                    confidence=score,
                    priority="strong",
                    reason="Position size above trim-watch threshold",
                    why_it_matters="Elevated position size can increase downside concentration during pullbacks.",
                    confirmations=["position_concentration", "trim_watch"],
                    suppressions=[],
                    price=prices.get(t),
                    portfolio_weight=weight,
                    metadata={
                        "source": "dalio_pm",
                        "trim_warning_weight": 0.20,
                        "quote_timestamp": str(datetime.now(timezone.utc)),
                        "risk_priority_bypass": True,
                    },
                    action_bias="TRIM_WATCH",
                    evidence=evidence,
                    portfolio_note=f"Weight: {weight:.1%}",
                    cooldown_key=f"{t}_trim_watch_dalio",
                    timestamp=datetime.now(),
                )
            )

    if total > 0:
        for sector, sector_value in sector_exposure.items():
            sector_weight = sector_value / total
            if sector != "unknown" and sector_weight > 0.40:
                evidence = [{"type": "overlap_warning", "note": f"sector {sector} at {sector_weight:.0%}"}]
                score = compute_score_from_evidence(evidence, bonuses={"no_duplicate": True}, base_score=50)
                signals.append(
                    Signal(
                        ticker=sector.upper(),
                        signal_type="overlap_exposure_warning",
                        brain="Dalio",
                        direction="down",
                        score_raw=score,
                        confidence=score,
                        priority="strong",
                        reason=f"Sector overlap risk in {sector}",
                        why_it_matters="Excess thematic overlap can amplify drawdown correlation.",
                        confirmations=["overlapping_exposure_warning", "concentration_warning"],
                        suppressions=[],
                        metadata={
                            "source": "dalio_pm",
                            "sector_weight": sector_weight,
                            "quote_timestamp": str(datetime.now(timezone.utc)),
                            "risk_priority_bypass": True,
                        },
                        action_bias="REDUCE_RISK",
                        evidence=evidence,
                        portfolio_note=f"Sector {sector} exposure: {sector_weight:.1%}",
                        cooldown_key=f"{sector}_overlap_exposure_warning_dalio",
                        timestamp=datetime.now(),
                    )
                )

    return signals
