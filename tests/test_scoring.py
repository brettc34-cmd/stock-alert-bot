from engine.scoring_engine import compute_score_from_evidence, confidence_band


def test_compute_score_basic():
    evidence = [{"type": "confirmation"}, {"type": "volume_unusual"}]
    score = compute_score_from_evidence(evidence, bonuses={"no_earnings_nearby": True})
    assert isinstance(score, int)
    assert score > 0


def test_single_factor_does_not_dominate():
    score = compute_score_from_evidence([{"type": "volume_unusual"}])
    assert score <= 55


def test_confidence_bands():
    assert confidence_band(20) == "low"
    assert confidence_band(45) == "moderate"
    assert confidence_band(70) == "strong"
    assert confidence_band(95) == "high"
