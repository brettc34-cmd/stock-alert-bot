from datetime import datetime

from engine.context_overlay import apply_context_overlays
from engine.signal_models import Signal


def _sig(signal_type: str = "breakout", confidence: int = 75) -> Signal:
    return Signal(
        ticker="AAPL",
        signal_type=signal_type,
        brain="Druckenmiller",
        direction="up",
        confidence=confidence,
        priority="high",
        action_bias="WATCH",
        reason="test",
        why_it_matters="test",
        confirmations=["a", "b"],
        suppressions=[],
        metadata={"sector": "Technology", "iv_rank": 0.8, "peer_relative_strength": -0.04},
        timestamp=datetime.now(),
    )


def test_context_overlay_penalizes_breakout_in_risk_off_context():
    signal = _sig("breakout", 80)
    macro = {
        "vix": 31.0,
        "yield_curve_10y_3m": -0.01,
        "sector_returns_20d": {"Technology": -0.04},
    }
    out = apply_context_overlays([signal], macro=macro, regime="risk_off")
    assert out[0].confidence < 80
    assert "regime_risk_off_penalty" in out[0].metadata["context_adjustments"]


def test_context_overlay_boosts_risk_signal_in_risk_off_context():
    signal = _sig("risk", 60)
    macro = {
        "vix": 29.0,
        "yield_curve_10y_3m": -0.005,
        "sector_returns_20d": {"Technology": -0.02},
    }
    out = apply_context_overlays([signal], macro=macro, regime="risk_off")
    assert out[0].confidence >= 60
