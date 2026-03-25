"""Tests for architecture improvements:
- Ranking engine covers all brain-produced signal types
- Regime engine uses SPX 20d momentum as a driver
- Portfolio optimizer includes catalyst_watch and earnings_catalyst
- Context overlay covers analyst signal types and VIX crisis tier
"""

from datetime import datetime
from engine.signal_models import Signal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sig(signal_type: str, confidence: int = 70, brain: str = "Analyst", direction: str = "up") -> Signal:
    return Signal(
        ticker="AAPL",
        signal_type=signal_type,
        brain=brain,
        direction=direction,
        confidence=confidence,
        priority="moderate",
        action_bias="WATCH",
        reason="test",
        why_it_matters="test",
        confirmations=["a", "b"],
        suppressions=[],
        metadata={},
        timestamp=datetime.now(),
    )


# ---------------------------------------------------------------------------
# Ranking engine — signal type coverage
# ---------------------------------------------------------------------------

class TestRankingEngineCoverage:
    def test_catalyst_watch_has_nonzero_priority(self):
        from engine.ranking_engine import ranking_score
        s = _sig("catalyst_watch", confidence=70)
        assert ranking_score(s) > 0

    def test_earnings_catalyst_ranked_higher_than_catalyst_watch(self):
        from engine.ranking_engine import ranking_score
        ec = _sig("earnings_catalyst", confidence=70)
        cw = _sig("catalyst_watch", confidence=70)
        assert ranking_score(ec) >= ranking_score(cw)

    def test_growth_value_has_priority(self):
        from engine.ranking_engine import ranking_score
        s = _sig("growth_value", confidence=65)
        assert ranking_score(s) > 0

    def test_quant_anomaly_has_priority(self):
        from engine.ranking_engine import ranking_score
        s = _sig("quant_anomaly", confidence=65)
        assert ranking_score(s) > 0

    def test_overlap_exposure_warning_has_priority(self):
        from engine.ranking_engine import ranking_score
        s = _sig("overlap_exposure_warning", confidence=65)
        assert ranking_score(s) > 0

    def test_trim_watch_has_priority(self):
        from engine.ranking_engine import ranking_score
        s = _sig("trim_watch", confidence=65)
        assert ranking_score(s) > 0

    def test_unknown_type_still_produces_nonzero_score(self):
        from engine.ranking_engine import ranking_score
        s = _sig("unrecognized_type", confidence=60)
        # Falls back to default priority 1 — should still score
        assert ranking_score(s) > 0


# ---------------------------------------------------------------------------
# Regime engine — SPX 20d momentum driver
# ---------------------------------------------------------------------------

class TestRegimeEngineMomentum:
    def test_negative_momentum_adds_risk_off_driver(self):
        from engine.regime_engine import classify_regime
        result = classify_regime({
            "vix": 20.0,
            "spx_price": 5200.0,
            "spx_ma200": 5000.0,
            "spx_return_20d": -0.07,
            "yield_curve_10y_3m": 0.01,
        })
        assert "momentum_negative" in result["drivers"]

    def test_positive_momentum_adds_risk_on_driver(self):
        from engine.regime_engine import classify_regime
        result = classify_regime({
            "vix": 15.0,
            "spx_price": 5200.0,
            "spx_ma200": 5000.0,
            "spx_return_20d": 0.06,
            "yield_curve_10y_3m": 0.02,
        })
        assert "momentum_positive" in result["drivers"]

    def test_moderate_momentum_not_flagged(self):
        from engine.regime_engine import classify_regime
        result = classify_regime({
            "vix": 20.0,
            "spx_price": 5100.0,
            "spx_ma200": 5000.0,
            "spx_return_20d": 0.02,
        })
        assert "momentum_positive" not in result["drivers"]
        assert "momentum_negative" not in result["drivers"]

    def test_crisis_vix_produces_risk_off(self):
        from engine.regime_engine import classify_regime, REGIME_RISK_OFF
        result = classify_regime({
            "vix": 42.0,
            "spx_price": 4600.0,
            "spx_ma200": 5000.0,
        })
        assert result["regime"] == REGIME_RISK_OFF
        assert "crisis_vix" in result["drivers"]

    def test_missing_momentum_field_does_not_crash(self):
        from engine.regime_engine import classify_regime
        result = classify_regime({"vix": 18.0})
        assert "regime" in result

    def test_strong_negative_momentum_lowers_regime_score(self):
        from engine.regime_engine import classify_regime, REGIME_RISK_OFF
        # Calm VIX but heavy negative momentum + curve inversion should tip risk_off
        result = classify_regime({
            "vix": 22.0,
            "spx_price": 4900.0,
            "spx_ma200": 5000.0,  # below MA200: -2
            "spx_return_20d": -0.06,  # momentum neg: -2
        })
        assert result["regime"] == REGIME_RISK_OFF


# ---------------------------------------------------------------------------
# Portfolio optimizer — ADD_TYPES coverage
# ---------------------------------------------------------------------------

class TestPortfolioOptimizerAddTypes:
    def test_earnings_catalyst_included_in_optimizer(self):
        from engine.portfolio_optimizer import ADD_TYPES
        assert "earnings_catalyst" in ADD_TYPES

    def test_catalyst_watch_included_in_optimizer(self):
        from engine.portfolio_optimizer import ADD_TYPES
        assert "catalyst_watch" in ADD_TYPES

    def test_optimizer_considers_catalyst_watch_signal(self):
        from engine.portfolio_optimizer import optimize_targets
        signals = [
            _sig("catalyst_watch", confidence=75),
            _sig("breakout", confidence=80, brain="Druckenmiller"),
        ]
        result = optimize_targets(signals)
        # catalyst_watch signal should appear in targets
        assert "AAPL" in result["targets"]
        assert result["gross_target"] > 0


# ---------------------------------------------------------------------------
# Context overlay — analyst signal types and VIX crisis tier
# ---------------------------------------------------------------------------

class TestContextOverlayCoverage:
    def test_catalyst_watch_penalized_in_risk_off(self):
        from engine.context_overlay import apply_context_overlays
        sig = _sig("catalyst_watch", confidence=75)
        out = apply_context_overlays([sig], macro={"vix": 32.0}, regime="risk_off")
        assert out[0].confidence < 75
        assert "regime_risk_off_penalty" in out[0].metadata["context_adjustments"]

    def test_earnings_catalyst_penalized_in_risk_off(self):
        from engine.context_overlay import apply_context_overlays
        sig = _sig("earnings_catalyst", confidence=70)
        out = apply_context_overlays([sig], macro={"vix": 29.0}, regime="risk_off")
        assert out[0].confidence < 70

    def test_crisis_vix_penalty_greater_than_high_vix(self):
        from engine.context_overlay import apply_context_overlays
        crisis_sig = _sig("breakout", confidence=80)
        high_sig = _sig("breakout", confidence=80)
        crisis_out = apply_context_overlays([crisis_sig], macro={"vix": 42.0}, regime="balanced")
        high_out = apply_context_overlays([high_sig], macro={"vix": 32.0}, regime="balanced")
        # Crisis VIX should penalize more than high VIX
        assert crisis_out[0].confidence < high_out[0].confidence

    def test_crisis_vix_penalty_applied_to_add_signals(self):
        from engine.context_overlay import apply_context_overlays
        sig = _sig("breakout", confidence=80)
        out = apply_context_overlays([sig], macro={"vix": 41.0}, regime="balanced")
        assert "crisis_vix_penalty" in out[0].metadata["context_adjustments"]

    def test_high_vix_still_uses_smaller_penalty(self):
        from engine.context_overlay import apply_context_overlays
        sig = _sig("breakout", confidence=80)
        out = apply_context_overlays([sig], macro={"vix": 32.0}, regime="balanced")
        assert "high_vix_penalty" in out[0].metadata["context_adjustments"]
        assert "crisis_vix_penalty" not in out[0].metadata["context_adjustments"]

    def test_risk_signal_type_unaffected_by_vix(self):
        from engine.context_overlay import apply_context_overlays
        sig = _sig("risk", confidence=65, direction="down")
        out = apply_context_overlays([sig], macro={"vix": 45.0}, regime="balanced")
        # Risk signals are not in ADD_SIGNAL_TYPES — no VIX penalty
        adj = out[0].metadata["context_adjustments"]
        assert "crisis_vix_penalty" not in adj
        assert "high_vix_penalty" not in adj
