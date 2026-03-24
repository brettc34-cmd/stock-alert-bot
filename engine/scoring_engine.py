"""Scoring engine implementation.

Balanced weighted scoring prevents any single factor (for example volume) from
dominating the final confidence score.
"""

from typing import List, Dict, Any


WEIGHTS = {
    "trend_breakout": 25,
    "breakout_confirmation": 20,
    "value_dip_quality": 15,
    "quant_anomaly": 12,
    "portfolio_context": 18,
    "macro_divergence": 10,
}

EVIDENCE_MAP = {
    "breakout_20d": "trend_breakout",
    "breakout_50d": "trend_breakout",
    "trend_ma_align": "trend_breakout",
    "ma20_slope_positive": "trend_breakout",
    "confirmation": "breakout_confirmation",
    "volume_unusual": "breakout_confirmation",
    "relative_strength_positive": "breakout_confirmation",
    "pullback_support": "value_dip_quality",
    "quality_dip": "value_dip_quality",
    "no_thesis_break": "value_dip_quality",
    "quant_volume_anomaly": "quant_anomaly",
    "quant_move_anomaly": "quant_anomaly",
    "volatility_expansion": "quant_anomaly",
    "portfolio_fit": "portfolio_context",
    "concentration": "portfolio_context",
    "overlap_warning": "portfolio_context",
    "macro_align": "macro_divergence",
    "macro_divergence": "macro_divergence",
    "analyst_key": "breakout_confirmation",
    "analyst_mean": "breakout_confirmation",
    "analyst_target_upside": "value_dip_quality",
    "analyst_coverage": "breakout_confirmation",
    "earnings_proximity": "macro_divergence",
    "earnings_catalyst": "breakout_confirmation",
    "sector_rotation": "macro_divergence",
    "peer_relative_strength": "breakout_confirmation",
}

DEFAULT_MIN_CONFIDENCE = 50


def confidence_band(confidence: int) -> str:
    if confidence < 40:
        return "low"
    if confidence < 60:
        return "moderate"
    if confidence < 80:
        return "strong"
    return "high"


def _normalize_weighted(score_by_factor: Dict[str, int]) -> int:
    total_weight = sum(WEIGHTS.values())
    weighted_sum = 0.0
    for factor, weight in WEIGHTS.items():
        factor_score = max(0, min(100, score_by_factor.get(factor, 0)))
        weighted_sum += weight * (factor_score / 100.0)
    return int(round((weighted_sum / total_weight) * 100))


def score_factors_from_evidence(evidence: List[Dict[str, Any]], bonuses: Dict[str, bool] = None, penalties: Dict[str, bool] = None) -> Dict[str, int]:
    bonuses = bonuses or {}
    penalties = penalties or {}
    factors = {name: 0 for name in WEIGHTS.keys()}

    for item in evidence:
        if not isinstance(item, dict):
            continue
        ev_type = item.get("type")
        factor = EVIDENCE_MAP.get(ev_type)
        if factor:
            factors[factor] = max(factors[factor], 100)

    # targeted boosts
    if bonuses.get("strong_breakout"):
        factors["trend_breakout"] = max(factors["trend_breakout"], 90)
    if bonuses.get("portfolio_fit"):
        factors["portfolio_context"] = max(factors["portfolio_context"], 80)
    if bonuses.get("no_earnings_nearby"):
        factors["breakout_confirmation"] = max(factors["breakout_confirmation"], 75)

    # penalties reduce specific factors first, then global clamp occurs later
    if penalties.get("stale_data"):
        for factor in factors:
            factors[factor] = max(0, factors[factor] - 45)
    if penalties.get("oversized_position"):
        factors["portfolio_context"] = max(0, factors["portfolio_context"] - 35)
    if penalties.get("conflict"):
        factors["macro_divergence"] = max(0, factors["macro_divergence"] - 25)

    return factors


def compute_score_from_evidence(
    evidence: List[Dict[str, Any]],
    bonuses: Dict[str, bool] = None,
    penalties: Dict[str, bool] = None,
    base_score: int = 0,
) -> int:
    """Compute a balanced 0-100 score from evidence and flags."""
    factors = score_factors_from_evidence(evidence, bonuses=bonuses, penalties=penalties)
    score = max(_normalize_weighted(factors), int(base_score or 0))
    active_factors = sum(1 for _, value in factors.items() if value > 0)

    # Modest boost for multi-confirmation setups.
    evidence_types = {e.get("type") for e in evidence if isinstance(e, dict)}
    if active_factors >= 2:
        score = min(100, score + 15)
    if active_factors >= 3:
        score = min(100, score + 10)
    if len(evidence_types) >= 3:
        score = min(100, score + 5)

    # Never allow a single evidence item to create premium confidence.
    if len(evidence_types) <= 1:
        score = min(score, 55)

    return score


def passes_min_alert_threshold(confidence: int, min_threshold: int = DEFAULT_MIN_CONFIDENCE) -> bool:
    return confidence >= min_threshold


__all__ = [
    "WEIGHTS",
    "confidence_band",
    "score_factors_from_evidence",
    "compute_score_from_evidence",
    "passes_min_alert_threshold",
    "DEFAULT_MIN_CONFIDENCE",
]
