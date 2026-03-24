from engine.signal_models import Signal
from alerts.discord_formatter import format_signal
from datetime import datetime


def test_format_signal_contains_ticker_and_category():
    sig = Signal(
        ticker="NVDA",
        signal_type="breakout",
        brain="Quant",
        direction="up",
        score_raw=30,
        confidence=65,
        priority="strong",
        reason="Test summary",
        why_it_matters="Test summary",
        action_bias="WATCH",
        confirmations=["breakout_confirmed", "volume_ratio_above_threshold"],
        suppressions=[],
        price=100.0,
        change_pct=0.01,
        volume_ratio=1.8,
        metadata={"quote_timestamp": datetime.now().isoformat()},
        evidence=[{"note": "test"}],
        portfolio_note="size:5%",
        cooldown_key="ladder_NVDA",
        timestamp=datetime.now(),
    )
    txt = format_signal(sig)
    assert "NVDA" in txt
    assert "breakout" in txt.lower()
