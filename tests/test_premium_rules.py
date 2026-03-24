from datetime import datetime, timedelta, timezone

from engine.signal_models import Signal
from engine import verification_engine
from engine.decision_engine import decide


def _base_signal(**kwargs):
    data = {
        "ticker": "NVDA",
        "signal_type": "breakout",
        "brain": "Quant",
        "direction": "up",
        "confidence": 75,
        "priority": "strong",
        "action_bias": "HOLD_ADD_ON_STRENGTH",
        "reason": "test",
        "why_it_matters": "test",
        "confirmations": ["breakout_confirmed", "above_key_mas"],
        "suppressions": [],
        "metadata": {
            "quote_timestamp": datetime.now(timezone.utc).isoformat(),
            "earnings_days": 20,
            "earnings_risk_window_days": 7,
            "trim_warning_weight": 0.2,
        },
    }
    data.update(kwargs)
    return Signal(**data)


def test_duplicate_alert_suppression():
    state = {"sent_signals": {}, "cooldowns": {}}
    s = _base_signal()
    ok, reason = verification_engine.verify_signal(s, state, cooldown_seconds=0)
    assert ok is True
    verification_engine.mark_sent(s, state)

    ok2, reason2 = verification_engine.verify_signal(s, state, cooldown_seconds=0)
    assert ok2 is False
    assert reason2 == "duplicate_state"


def test_stale_data_suppression():
    stale_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    s = _base_signal(metadata={"quote_timestamp": stale_ts})
    ok, reason = verification_engine.verify_signal(s, state={}, stale_quote_max_age_seconds=300)
    assert ok is False
    assert reason == "stale_data"


def test_earnings_risk_suppression_for_add_type():
    s = _base_signal(signal_type="dip", metadata={"quote_timestamp": datetime.now(timezone.utc).isoformat(), "earnings_days": 2, "earnings_risk_window_days": 7})
    ok, reason = verification_engine.verify_signal(s, state={})
    assert ok is False
    assert reason == "earnings_risk_nearby"


def test_portfolio_concentration_changes_action_bias():
    portfolio = {"positions": [{"ticker": "NVDA", "shares": 100}], "cash": 0, "rules": {"max_position_weight_add": 0.15, "trim_warning_weight": 0.20}}
    prices = {"NVDA": 100.0}
    s = _base_signal(action_bias="HOLD_ADD_ON_STRENGTH")
    out = decide([s], portfolio, prices)
    assert out[0].action_bias in {"HOLD", "TRIM_WATCH", "REDUCE_RISK"}
