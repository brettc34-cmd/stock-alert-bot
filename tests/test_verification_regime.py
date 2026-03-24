from datetime import datetime, timezone

from engine.signal_models import Signal
from engine.verification_engine import verify_signal


def test_verify_signal_blocks_regime_mismatch():
    signal = Signal(
        ticker="AAPL",
        signal_type="breakout",
        brain="Druckenmiller",
        direction="up",
        confidence=75,
        priority="strong",
        action_bias="WATCH",
        reason="test",
        why_it_matters="test",
        confirmations=["breakout_confirmed", "above_key_mas"],
        suppressions=[],
        metadata={"quote_timestamp": datetime.now(timezone.utc).isoformat(), "regime_blocked": True},
        timestamp=datetime.now(),
    )

    ok, reason = verify_signal(signal, state={})
    assert ok is False
    assert reason == "regime_mismatch"
