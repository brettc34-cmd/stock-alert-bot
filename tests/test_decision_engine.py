from engine.decision_engine import decide
from engine.signal_models import Signal
from datetime import datetime


def test_decision_downgrades_overweight_add():
    portfolio = {"positions": [{"ticker": "AAPL", "shares": 100}], "cash": 0}
    prices = {"AAPL": 200}
    sig = Signal(
        ticker="AAPL",
        signal_type="breakout",
        brain="Test",
        direction="up",
        score_raw=80,
        confidence=80,
        priority="high",
        reason="test",
        why_it_matters="test",
        confirmations=["breakout_confirmed", "above_key_mas", "volume_ratio_above_threshold"],
        suppressions=[],
        action_bias="HOLD_ADD_ON_STRENGTH",
        metadata={"quote_timestamp": datetime.now().isoformat()},
        evidence=[],
        portfolio_note="",
        cooldown_key="test",
        timestamp=datetime.now(),
    )
    out = decide([sig], portfolio, prices)
    assert out[0].action_bias in ("HOLD", "TRIM_WATCH", "REDUCE_RISK")
    assert "target_weight" in out[0].metadata
    assert "delta_notional" in out[0].metadata
