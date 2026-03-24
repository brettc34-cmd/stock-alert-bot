from datetime import datetime, timezone

from services.ticker_research import build_ticker_research


def test_build_ticker_research_returns_insights(monkeypatch):
    monkeypatch.setattr(
        "services.ticker_research.fetch_quote",
        lambda _ticker: {
            "ticker": "NVDA",
            "currentPrice": 100.0,
            "move_1d": 0.01,
            "volume_ratio": 1.6,
            "timestamp": datetime.now(timezone.utc),
            "earnings_days": 14,
            "sector": "Technology",
            "iv_rank": 0.4,
        },
    )
    monkeypatch.setattr("services.ticker_research.fetch_macro_snapshot", lambda: {"vix": 18.0, "spx_price": 5000.0, "spx_ma200": 4900.0, "yield_curve_10y_3m": 0.01, "credit_risk_proxy_20d": 0.01, "sector_returns_20d": {"Technology": 0.05}})
    monkeypatch.setattr("services.ticker_research.load_json_file", lambda _p: {"ladder_step": 5})
    monkeypatch.setattr("services.ticker_research.load_thresholds", lambda: {"market": {"breakout_volume_ratio": 1.5, "strong_breakout_volume_ratio": 2.0, "stale_quote_max_age_seconds": 300}, "runtime": {"earnings_risk_window_days": 7, "min_confirmations_normal": 1, "min_confirmations_high": 2}, "confidence": {"min_send_score": 1, "high_conviction_score": 80}, "portfolio": {"trim_warning_weight": 0.2}, "premium": {"sector_leader_return_20d": 0.03, "sector_laggard_return_20d": -0.03}})
    monkeypatch.setattr("services.ticker_research.load_portfolio", lambda: {"positions": [{"ticker": "NVDA", "shares": 10}], "cash": 10000, "rules": {"max_position_weight_add": 0.15, "trim_warning_weight": 0.2}})
    monkeypatch.setattr("services.ticker_research.load_event_calendar", lambda _p: {"events": []})
    monkeypatch.setattr("services.ticker_research.resolve_event_risk", lambda *_a, **_k: type("X", (), {"active": False, "horizon_hours": 24, "events": []})())

    monkeypatch.setattr("services.ticker_research.process_ladder_and_volume", lambda *_a, **_k: [])
    monkeypatch.setattr("services.ticker_research.buffett_analyze", lambda *_a, **_k: [])
    monkeypatch.setattr("services.ticker_research.druck_analyze", lambda *_a, **_k: [])
    monkeypatch.setattr("services.ticker_research.lynch_analyze", lambda *_a, **_k: [])
    monkeypatch.setattr("services.ticker_research.soros_analyze", lambda *_a, **_k: [])
    monkeypatch.setattr("services.ticker_research.dalio_analyze", lambda *_a, **_k: [])
    monkeypatch.setattr("services.ticker_research.sector_rotation_analyze", lambda *_a, **_k: [])
    monkeypatch.setattr(
        "services.ticker_research.analyst_analyze",
        lambda *_a, **_k: [],
    )

    text = build_ticker_research("NVDA")

    assert "Research: NVDA" in text
    assert "Market regime:" in text


def test_build_ticker_research_handles_missing_ticker():
    text = build_ticker_research("")
    assert "Please provide a ticker symbol" in text
