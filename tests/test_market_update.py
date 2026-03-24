from __future__ import annotations

from datetime import datetime

from market_update.data_fetcher import QuoteSpec, _normalize_value
from market_update.config import MarketUpdateSettings
from market_update.generator import build_market_update
from market_update.formatter import format_discord_update
from market_update.models import Headline, InstrumentQuote, MarketUpdateResult
from market_update.news import summarize_market_drivers


class FakeFetcher:
    session = object()

    def fetch_major_indexes(self):
        return [
            InstrumentQuote("sp500", "S&P 500", "^GSPC", "Yahoo Finance", 5218.44, 0.48, datetime(2026, 3, 24), "number"),
            InstrumentQuote("dow", "Dow Jones Industrial Average", "^DJI", "Yahoo Finance", 39411.20, 0.31, datetime(2026, 3, 24), "number"),
            InstrumentQuote("nasdaq", "Nasdaq Composite", "^IXIC", "Yahoo Finance", 16402.18, 0.76, datetime(2026, 3, 24), "number"),
        ]

    def fetch_rates_and_macro(self):
        return [
            InstrumentQuote("us10y", "U.S. 10-year Treasury yield", "^TNX", "Yahoo Finance", 4.23, 0.95, datetime(2026, 3, 24), "yield_pct"),
            InstrumentQuote("dxy", "U.S. dollar index", "DX-Y.NYB", "Yahoo Finance", 103.82, -0.14, datetime(2026, 3, 24), "number"),
        ]

    def fetch_commodities(self):
        return [
            InstrumentQuote("wti", "WTI crude oil", "CL=F", "Yahoo Finance", 81.22, 0.91, datetime(2026, 3, 24), "currency"),
            InstrumentQuote("gold", "Gold", "GC=F", "Yahoo Finance", 2184.60, 0.34, datetime(2026, 3, 24), "currency"),
        ]

    def fetch_crypto(self):
        return [
            InstrumentQuote("bitcoin", "Bitcoin", "BTC-USD", "Yahoo Finance", 67422.00, 1.35, datetime(2026, 3, 24), "currency"),
            InstrumentQuote("ethereum", "Ethereum", "ETH-USD", "Yahoo Finance", 3482.15, 0.88, datetime(2026, 3, 24), "currency"),
        ]

    def fetch_vix(self):
        return InstrumentQuote("vix", "VIX", "^VIX", "Yahoo Finance", 14.82, -2.10, datetime(2026, 3, 24), "number")

    def fetch_sector_strength(self):
        return [
            InstrumentQuote("technology", "Technology", "XLK", "Yahoo Finance", 210.0, 1.02, datetime(2026, 3, 24), "number"),
            InstrumentQuote("energy", "Energy", "XLE", "Yahoo Finance", 88.0, 0.84, datetime(2026, 3, 24), "number"),
            InstrumentQuote("real_estate", "Real Estate", "XLRE", "Yahoo Finance", 40.0, -0.36, datetime(2026, 3, 24), "number"),
            InstrumentQuote("utilities", "Utilities", "XLU", "Yahoo Finance", 66.0, -0.41, datetime(2026, 3, 24), "number"),
        ]

    def fetch_effective_fed_funds_rate(self):
        return 4.33, "2026-03-01"


class FakeNewsFetcher:
    def fetch_headlines(self, per_feed_limit: int = 6, total_limit: int = 12):
        return [
            Headline(source="CNBC Markets", title="Investors recalibrate the path of Fed easing"),
            Headline(source="CNBC Markets", title="Oil rises as traders track supply concerns"),
            Headline(source="CNBC Markets", title="Large-cap earnings keep guidance in focus"),
        ]


def test_build_market_update_contains_required_sections():
    result = build_market_update(
        now=datetime(2026, 3, 24, 7, 0),
        settings=MarketUpdateSettings(schedule_timezone="America/Chicago"),
        data_fetcher=FakeFetcher(),
        news_fetcher=FakeNewsFetcher(),
    )

    assert "Big picture" in result.body
    assert "Major U.S. indexes" in result.body
    assert "Rates and macro" in result.body
    assert "Commodities" in result.body
    assert "Crypto" in result.body
    assert "Market drivers" in result.body
    assert "Sector color" in result.body
    assert "Volatility" in result.body
    assert "What to watch next" in result.body
    # email-format headers must not appear
    assert "Subject:" not in result.body
    assert "Timestamp:" not in result.body


def test_yield_normalization_keeps_already_percent_values():
    spec = QuoteSpec("us10y", "U.S. 10-year Treasury yield", "^TNX", "Yahoo Finance", format_hint="yield_pct")
    assert _normalize_value(spec, 4.4079) == 4.4079


def test_yield_normalization_scales_legacy_tnx_style_values():
    spec = QuoteSpec("us10y", "U.S. 10-year Treasury yield", "^TNX", "Yahoo Finance", format_hint="yield_pct")
    assert _normalize_value(spec, 44.079) == 4.4079


def test_build_market_update_uses_afternoon_phrase():
    result = build_market_update(
        now=datetime(2026, 3, 24, 13, 28),
        settings=MarketUpdateSettings(schedule_timezone="America/Chicago"),
        data_fetcher=FakeFetcher(),
        news_fetcher=FakeNewsFetcher(),
    )

    assert "this afternoon" in result.body
    assert "this morning" not in result.body.split("Big picture", 1)[1]


def test_build_market_update_uses_morning_phrase():
    result = build_market_update(
        now=datetime(2026, 3, 24, 7, 0),
        settings=MarketUpdateSettings(schedule_timezone="America/Chicago"),
        data_fetcher=FakeFetcher(),
        news_fetcher=FakeNewsFetcher(),
    )

    assert "this morning" in result.body


def test_market_driver_keywords_use_word_boundaries():
    drivers = summarize_market_drivers(
        [Headline(source="CNBC", title="Small cap-focused Russell 2000 becomes first U.S. benchmark to enter correction territory")],
        limit=5,
    )

    assert drivers == [
        "Headline flow is also tracking Small cap-focused Russell 2000 becomes first U.S. benchmark to enter correction territory."
    ]


def test_market_driver_summary_does_not_classify_oil_from_single_summary_reference():
    drivers = summarize_market_drivers(
        [
            Headline(
                source="CNBC Markets",
                title="Small cap-focused Russell 2000 becomes first U.S. benchmark to enter correction territory",
                summary="Small caps are especially sensitive to changes in oil prices and a slowdown in the economic cycle.",
            )
        ],
        limit=5,
    )

    assert drivers == [
        "Headline flow is also tracking Small cap-focused Russell 2000 becomes first U.S. benchmark to enter correction territory."
    ]


def test_format_discord_update_excludes_email_headers_and_respects_max_chars():
    result = build_market_update(
        now=datetime(2026, 3, 24, 13, 28),
        settings=MarketUpdateSettings(schedule_timezone="America/Chicago"),
        data_fetcher=FakeFetcher(),
        news_fetcher=FakeNewsFetcher(),
    )
    preview = format_discord_update(result, max_chars=350)

    assert "Subject:" not in preview
    assert "Timestamp:" not in preview
    assert "Big picture" in preview
    assert len(preview) <= 350


def test_format_discord_update_full_within_default_limit():
    result = build_market_update(
        now=datetime(2026, 3, 24, 7, 0),
        settings=MarketUpdateSettings(schedule_timezone="America/Chicago"),
        data_fetcher=FakeFetcher(),
        news_fetcher=FakeNewsFetcher(),
    )
    preview = format_discord_update(result)

    assert "Big picture" in preview
    assert "Major U.S. indexes" in preview
    assert "Rates and macro" in preview
    assert "Commodities" in preview
    assert "Crypto" in preview
    assert "Market drivers" in preview
    # Sector color and Volatility are excluded from Discord preview
    assert "Sector color" not in preview
    # "Volatility" appears in the Big picture prose (VIX mention), but the
    # Volatility section header should not appear as a standalone section.
    assert "\nVolatility\n" not in preview
    assert len(preview) <= 1800