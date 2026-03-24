from brains.quant_brain import process_ladder_and_volume
from brains.lynch_brain import analyze as lynch_analyze
from brains.analyst_brain import analyze as analyst_analyze
from engine.signal_models import Signal
from datetime import datetime


def test_ladder_cross_and_volume_signal():
    info = {
        "currentPrice": 210.0,
        "volume": 5000000,
        "averageVolume": 1000000,
    }
    anchor_entry = {"anchor": 186.0, "next_up": 191.0, "next_down": 181.0}
    config = {"ladder_step": 5, "volume_threshold": 1.5}
    state = {"volume_alerts_sent": {}}
    timestamp_text = datetime.now().isoformat()
    day_progress = 0.5

    signals = process_ladder_and_volume("NVDA", info, anchor_entry, config, state, timestamp_text, day_progress)
    assert isinstance(signals, list)
    assert all(isinstance(s, Signal) for s in signals)
    assert any(s.category in ("breakout", "unusual_volume", "dip") for s in signals)


def test_lynch_brain_fires_with_growth_and_value_data():
    info = {
        "currentPrice": 120.0,
        "revenueGrowth": 0.22,
        "pegRatio": 1.6,
        "ma20": 115.0,
        "ma50": 110.0,
        "move_1d": 0.02,
        "timestamp": datetime.now(),
    }
    signals = lynch_analyze("NVDA", info, {}, {})
    assert len(signals) >= 1
    assert any(s.signal_type == "growth_value" for s in signals)


def test_analyst_brain_fires_with_recommendation_and_target_upside():
    info = {
        "currentPrice": 100.0,
        "recommendationKey": "buy",
        "recommendationMean": 1.9,
        "targetMeanPrice": 115.0,
        "numberOfAnalystOpinions": 12,
        "earnings_days": 14,
        "timestamp": datetime.now(),
    }
    signals = analyst_analyze("AAPL", info, {}, {})
    assert len(signals) >= 1
    assert any(s.signal_type == "catalyst_watch" for s in signals)


def test_analyst_brain_adds_earnings_catalyst_near_event_window():
    info = {
        "currentPrice": 100.0,
        "recommendationKey": "buy",
        "recommendationMean": 1.8,
        "targetMeanPrice": 116.0,
        "numberOfAnalystOpinions": 14,
        "earnings_days": 3,
        "iv_rank": 0.75,
        "timestamp": datetime.now(),
    }
    signals = analyst_analyze("AAPL", info, {}, {"earnings_risk_window_days": 7})
    assert any(s.signal_type == "earnings_catalyst" for s in signals)
