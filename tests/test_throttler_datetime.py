"""Tests for throttler timezone-aware datetime normalization."""
from datetime import datetime, timezone, timedelta

from engine.throttler import should_send_alert, record_alert


def _make_state_with_naive_history(ticker: str, when: str) -> dict:
    return {"alert_history": {ticker: [when]}}


def test_should_send_alert_handles_naive_iso_timestamps():
    """Old state.json entries lack timezone — must not raise TypeError."""
    # Naive timestamp that is > 1 hour ago (epoch-style, very old)
    state = _make_state_with_naive_history("AAPL", "2020-01-01T12:00:00")
    # Should not raise and should allow sending (stale entry pruned)
    result = should_send_alert(state, "AAPL", max_per_ticker_per_hour=2, max_per_run=5)
    assert result is True


def test_should_send_alert_handles_aware_iso_timestamps():
    """Timezone-aware timestamps from current records must work correctly."""
    recent = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    state = _make_state_with_naive_history("NVDA", recent)
    # 1 recent entry, limit is 2 — should allow sending
    result = should_send_alert(state, "NVDA", max_per_ticker_per_hour=2, max_per_run=5)
    assert result is True


def test_should_send_alert_blocks_when_limit_reached():
    recent1 = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    recent2 = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()
    state = _make_state_with_naive_history("TSLA", recent1)
    state["alert_history"]["TSLA"].append(recent2)
    result = should_send_alert(state, "TSLA", max_per_ticker_per_hour=2, max_per_run=5)
    assert result is False
