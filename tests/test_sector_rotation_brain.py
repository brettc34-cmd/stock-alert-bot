from datetime import datetime

from brains.sector_rotation_brain import analyze


def test_sector_rotation_brain_fires_leader_signal():
    info = {
        "sector": "Technology",
        "sector_return_20d": 0.06,
        "currentPrice": 200.0,
        "move_1d": 0.01,
        "volume_ratio": 1.4,
        "timestamp": datetime.now(),
    }
    signals = analyze("AAPL", info, {}, {"sector_leader_return_20d": 0.03, "sector_laggard_return_20d": -0.03})
    assert len(signals) >= 1
    assert signals[0].signal_type in {"trend_continuation", "risk"}


def test_sector_rotation_brain_fires_laggard_risk_signal():
    info = {
        "sector": "Financial Services",
        "sector_return_20d": -0.05,
        "currentPrice": 150.0,
        "move_1d": -0.01,
        "volume_ratio": 1.2,
        "timestamp": datetime.now(),
    }
    signals = analyze("JPM", info, {}, {"sector_leader_return_20d": 0.03, "sector_laggard_return_20d": -0.03})
    assert len(signals) >= 1
    assert signals[0].signal_type == "risk"
