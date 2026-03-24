import json
from datetime import datetime
from zoneinfo import ZoneInfo

import bot
from engine.signal_models import Signal
from web.app import app


def _write_json(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def test_full_pipeline_sends_expected_alerts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "storage").mkdir()

    _write_json(
        tmp_path / "config.json",
        {
            "stocks": ["NVDA"],
            "ladder_step": 5,
            "volume_threshold": 1.5,
            "discord_webhook": "",
        },
    )
    _write_json(
        tmp_path / "anchors.json",
        {"NVDA": {"anchor": 100.0, "next_up": 105.0, "next_down": 95.0}},
    )
    _write_json(tmp_path / "state.json", {})
    _write_json(
        tmp_path / "config" / "portfolio.json",
        {"positions": [{"ticker": "NVDA", "shares": 10, "sector": "tech"}], "cash": 10000},
    )
    (tmp_path / "config" / "thresholds.yaml").write_text(
        """
confidence:
  min_send_score: 50
  high_conviction_score: 80
alerts:
  max_per_ticker_per_hour: 2
  max_per_run: 5
runtime:
  alert_cooldown_minutes: 0
  earnings_risk_window_days: 7
  min_confirmations_normal: 2
  min_confirmations_high: 3
  log_level: INFO
market:
  stale_quote_max_age_seconds: 300
  breakout_volume_ratio: 1.5
  strong_breakout_volume_ratio: 2.0
portfolio:
  max_position_weight_add: 0.15
  trim_warning_weight: 0.20
""",
        encoding="utf-8",
    )
    (tmp_path / "config" / "features.yaml").write_text(
        """
digest:
  enabled: false
feature_flags:
  enable_outcome_tracking: false
runtime:
  enable_after_hours_alerts: false
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.com/webhook")

    sent_messages = []

    def fake_quote(_ticker):
        return {
            "ticker": "NVDA",
            "currentPrice": 110.0,
            "volume": 2_000_000,
            "averageVolume": 1_000_000,
            "timestamp": datetime.now(),
            "earnings_days": 30,
        }

    def fake_signal(*_args, **_kwargs):
        return [
            Signal(
                ticker="NVDA",
                signal_type="breakout",
                brain="Quant",
                direction="up",
                confidence=82,
                priority="high",
                action_bias="WATCH",
                reason="mock breakout",
                why_it_matters="mock reason",
                confirmations=["breakout_confirmed", "volume_unusual", "trend_ma_align"],
                suppressions=[],
                price=110.0,
                metadata={"quote_timestamp": datetime.now().isoformat(), "earnings_days": 30},
            )
        ]

    monkeypatch.setattr(bot, "fetch_quote", fake_quote)
    monkeypatch.setattr(bot, "process_ladder_and_volume", fake_signal)
    monkeypatch.setattr(bot, "buffett_analyze", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(bot, "druck_analyze", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(bot, "lynch_analyze", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(bot, "analyst_analyze", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(bot, "soros_analyze", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(bot, "dalio_analyze", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(bot.AlertRouter, "filter_signals", lambda _self, signals: (signals, {}))
    monkeypatch.setattr(bot, "send_discord_message", lambda _u, msg: sent_messages.append(msg) or True)

    now_et = datetime(2026, 3, 23, 10, 0, tzinfo=ZoneInfo("US/Eastern"))
    result = bot.run_once(now_et_override=now_et)

    assert result["status"] == "ok"
    assert result["sent_count"] == 1
    assert len(sent_messages) >= 1


def test_dashboard_config_save_invalid_yaml_returns_error(monkeypatch):
    monkeypatch.setenv("STOCK_ALERT_DASHBOARD_KEY", "test-key")
    client = app.test_client()
    resp = client.post(
        "/config",
        data={"thresholds": "a: [", "features": "b: true"},
    )
    assert resp.status_code == 400
    assert b"YAML parse error" in resp.data
