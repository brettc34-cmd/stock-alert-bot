from datetime import datetime

from engine.portfolio_optimizer import optimize_targets
from engine.signal_models import Signal


def _sig(ticker: str, confidence: int, sector: str) -> Signal:
    return Signal(
        ticker=ticker,
        signal_type="breakout",
        brain="Druckenmiller",
        direction="up",
        confidence=confidence,
        priority="high",
        action_bias="WATCH",
        reason="x",
        why_it_matters="x",
        confirmations=["a", "b"],
        suppressions=[],
        price=100.0,
        change_pct=0.02,
        metadata={"sector": sector},
        timestamp=datetime.now(),
    )


def test_optimizer_returns_bounded_targets_and_sector_caps():
    plan = optimize_targets(
        [_sig("AAPL", 85, "Technology"), _sig("MSFT", 80, "Technology"), _sig("JPM", 75, "Financial Services")],
        max_single_name_weight=0.12,
        max_sector_weight=0.18,
        gross_risk_budget=0.30,
    )
    assert plan["gross_target"] <= 0.30
    assert all(v <= 0.12 for v in plan["targets"].values())
    assert all(v <= 0.18 for v in plan["sector_targets"].values())
