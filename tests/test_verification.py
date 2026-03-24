from engine import verification_engine
from engine.signal_models import Signal
from datetime import datetime, timezone


def test_confidence_thresholds():
    assert verification_engine.passes_min_confidence(60, 55) is True
    assert verification_engine.passes_min_confidence(54, 55) is False


def test_verify_signal_rejects_insufficient_confirmations():
    signal = Signal(
        ticker="NVDA",
        signal_type="breakout",
        brain="Quant",
        direction="up",
        confidence=70,
        priority="strong",
        action_bias="WATCH",
        reason="test",
        why_it_matters="test",
        confirmations=["breakout_confirmed"],
        suppressions=[],
        metadata={"quote_timestamp": datetime.now(timezone.utc).isoformat()},
    )
    ok, reason = verification_engine.verify_signal(signal, state={})
    assert ok is False
    assert reason == "insufficient_confirmations"


def test_verify_signal_rejects_low_confidence():
    signal = Signal(
        ticker="NVDA",
        signal_type="breakout",
        brain="Quant",
        direction="up",
        confidence=40,
        priority="moderate",
        action_bias="WATCH",
        reason="test",
        why_it_matters="test",
        confirmations=["a", "b"],
        suppressions=[],
        metadata={"quote_timestamp": datetime.now(timezone.utc).isoformat()},
    )
    ok, reason = verification_engine.verify_signal(signal, state={})
    assert ok is False
    assert reason == "low_confidence"
