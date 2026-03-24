from telemetry import configure_opentelemetry
import interactive_discord_bot
from web.app import app


def test_configure_opentelemetry_without_endpoint(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    result = configure_opentelemetry(service_name="test-service")
    assert result["configured"] is True


def test_flask_app_instrumented():
    assert getattr(app, "_is_instrumented_by_opentelemetry", False) is True


def test_interactive_bot_telemetry_context_initializes(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    result = configure_opentelemetry(service_name="interactive-bot-test")
    assert result["configured"] is True
    assert interactive_discord_bot.tracer is not None
