from config.settings import build_runtime_settings


def test_market_session_settings_from_config_json(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.com/webhook")
    # Isolate from developer-local .env values so config precedence is tested reliably.
    monkeypatch.delenv("MARKET_OPEN", raising=False)
    monkeypatch.delenv("MARKET_CLOSE", raising=False)
    monkeypatch.delenv("MARKET_TIMEZONE", raising=False)
    cfg = {
        "market_hours": {
            "open": "09:45",
            "close": "15:30",
            "timezone": "America/New_York",
        }
    }
    settings = build_runtime_settings(cfg)
    assert settings.market_open == "09:45"
    assert settings.market_close == "15:30"
    assert settings.market_timezone == "America/New_York"
