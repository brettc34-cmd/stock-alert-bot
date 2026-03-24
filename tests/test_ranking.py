from engine.ranking_engine import rank_signals
from engine.signal_models import Signal
from datetime import datetime


def test_ranking_prefers_confidence():
    s1 = Signal("AAA", "breakout", "X", "up", 80, "high", "HOLD_ADD_ON_STRENGTH", "", "", ["a", "b"], [], 100.0, 0.01, 1.7, None, {"quote_timestamp": datetime.now().isoformat()}, datetime.now(), 10, "k1", [], "", "", "")
    s2 = Signal("BBB", "dip", "X", "down", 60, "moderate", "WATCH", "", "", ["a", "b"], [], 90.0, -0.01, 1.0, None, {"quote_timestamp": datetime.now().isoformat()}, datetime.now(), 10, "k2", [], "", "", "")
    ranked = rank_signals([s1, s2], top_n=2)
    assert ranked[0].ticker == "AAA"
