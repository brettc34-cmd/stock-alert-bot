from __future__ import annotations

import json
from datetime import datetime

from sp500_overview.config import SP500OverviewSettings
from sp500_overview.headlines import classify_driver_labels, _is_market_relevant
from sp500_overview.job import build_sp500_overview, send_sp500_overview, should_run_now
from sp500_overview.models import Headline, SP500Snapshot


class FakeMarketDataFetcher:
    session = object()

    def fetch_snapshot(self, now=None):
        return SP500Snapshot(
            as_of=datetime(2026, 3, 24, 7, 0),
            sp500_level=6577.49,
            sp500_daily_change_pct=-0.05,
            sp500_ytd_change_pct=7.84,
            treasury_10y_yield_pct=4.40,
            treasury_10y_change_pct=1.57,
            vix_level=26.68,
            vix_change_pct=2.03,
            wti_change_pct=0.68,
            fed_funds_rate=3.64,
            fed_funds_as_of="2026-02-01",
            strongest_sectors=[("Energy", 1.20), ("Technology", 0.84)],
            weakest_sectors=[("Utilities", -0.52), ("Real Estate", -0.31)],
            warnings=[],
        )


class FakeHeadlineFetcher:
    def fetch_headlines(self, per_feed_limit: int = 4, total_limit: int = 6):
        return [
            Headline(source="CNBC Markets", title="Fed still expects to cut rates once this year despite spiking oil prices"),
            Headline(source="CNBC Economy", title="Jobs data keeps labor market resilience in focus"),
            Headline(source="Federal Reserve", title="Federal Reserve releases policy statement"),
        ]


def test_build_sp500_overview_contains_required_sections_and_disclaimer():
    result = build_sp500_overview(
        now=datetime(2026, 3, 24, 7, 0),
        settings=SP500OverviewSettings(max_words=250, schedule_timezone="America/Chicago"),
        market_data_fetcher=FakeMarketDataFetcher(),
        headline_fetcher=FakeHeadlineFetcher(),
    )

    assert result.body.startswith("S&P 500 Daily Overview")
    assert "- Index level:" in result.body
    assert "- Daily move:" in result.body
    assert "- YTD:" in result.body
    assert "- Top drivers:" in result.body
    assert "- Key headlines:" in result.body
    assert "- Bull case:" in result.body
    assert "- Bear case:" in result.body
    assert "- Bottom line:" in result.body
    assert result.body.endswith("“This is general information only and not financial advice. For personal guidance, please talk to a licensed professional.”")
    assert result.word_count <= 250


def test_send_sp500_overview_logs_result(monkeypatch, tmp_path):
    monkeypatch.setattr("sp500_overview.job.get_discord_webhook_url", lambda: "https://example.com/webhook")
    monkeypatch.setattr("sp500_overview.job.send_discord_message", lambda webhook_url, message_text: True)

    settings = SP500OverviewSettings(
        schedule_timezone="America/Chicago",
        log_path=str(tmp_path / "sp500_history.jsonl"),
    )
    message = build_sp500_overview(
        now=datetime(2026, 3, 24, 7, 0),
        settings=settings,
        market_data_fetcher=FakeMarketDataFetcher(),
        headline_fetcher=FakeHeadlineFetcher(),
    )
    result = send_sp500_overview(message=message, settings=settings)

    assert result.sent is True
    assert result.destination == "discord-webhook"
    payload = json.loads((tmp_path / "sp500_history.jsonl").read_text(encoding="utf-8").strip())
    assert payload["sent"] is True
    assert payload["delivery_method"] == "discord"
    assert payload["subject"] == message.subject


def test_classify_driver_labels_assigns_correct_themes():
    labels = classify_driver_labels(
        [
            Headline(source="CNBC Economy", title="Fed signals one rate cut this year amid stubborn inflation"),
            Headline(source="CNBC Markets", title="Crude oil surges as OPEC announces surprise production cut"),
        ],
        limit=3,
    )

    assert "Fed expectations" in labels
    assert "Oil" in labels


def test_market_relevance_filter_blocks_non_financial_headlines():
    assert _is_market_relevant("White House to pay TotalEnergies $1 billion to kill off East Coast wind farm projects", "") is False
    assert _is_market_relevant("Elizabeth Warren demands answers on bank merger", "") is False
    assert _is_market_relevant("S&P 500 falls as inflation data spooks investors", "") is True
    assert _is_market_relevant("Fed holds rates steady, signals two cuts in 2026", "") is True


def test_should_run_now_respects_configured_schedule():
    settings = SP500OverviewSettings(schedule_time="07:00", schedule_timezone="America/Chicago")
    assert should_run_now(now=datetime(2026, 3, 24, 7, 5), settings=settings, tolerance_minutes=10) is True
    assert should_run_now(now=datetime(2026, 3, 24, 7, 30), settings=settings, tolerance_minutes=10) is False