"""Generate the daily market update."""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from market_update.config import MarketUpdateSettings, load_market_update_settings
from market_update.data_fetcher import MarketDataFetcher
from market_update.formatter import format_body
from market_update.models import InstrumentQuote, MarketUpdateResult
from market_update.news import NewsFetcher, summarize_market_drivers

logger = logging.getLogger(__name__)


def _quote_lookup(quotes: list[InstrumentQuote]) -> dict[str, InstrumentQuote]:
    return {q.key: q for q in quotes}


def _session_phrase(now: datetime) -> str:
    hour = now.hour
    if hour < 12:
        return "this morning"
    if hour < 17:
        return "this afternoon"
    return "this evening"


def _directional_summary(quotes: list[InstrumentQuote], session: str) -> str:
    available = [q for q in quotes if q.change_pct is not None]
    if not available:
        return "Index performance was mixed, with incomplete live data at generation time."
    avg = sum(q.change_pct or 0.0 for q in available) / len(available)
    if avg >= 0.4:
        return f"U.S. risk sentiment is leaning constructive {session}."
    if avg <= -0.4:
        return f"U.S. risk sentiment is under pressure {session}."
    return f"U.S. markets are trading on a relatively balanced footing {session}."


def _big_picture(
    indexes: list[InstrumentQuote],
    rates: list[InstrumentQuote],
    commodities: list[InstrumentQuote],
    crypto: list[InstrumentQuote],
    vix: InstrumentQuote,
    drivers: list[str],
    generated_at: datetime,
) -> str:
    session = _session_phrase(generated_at)
    indexes_map = _quote_lookup(indexes)
    rates_map = _quote_lookup(rates)
    commodities_map = _quote_lookup(commodities)
    crypto_map = _quote_lookup(crypto)

    lines = [_directional_summary(indexes, session)]

    details = []
    spx = indexes_map.get("sp500")
    if spx and spx.change_pct is not None:
        details.append(f"The S&P 500 is {spx.change_pct:+.2f}% on the latest reading")
    us10y = rates_map.get("us10y")
    if us10y and us10y.price is not None:
        details.append(f"the 10-year Treasury yield is near {us10y.price:.2f}%")
    oil = commodities_map.get("wti")
    if oil and oil.change_pct is not None:
        details.append(f"WTI crude is {oil.change_pct:+.2f}%")
    bitcoin = crypto_map.get("bitcoin")
    if bitcoin and bitcoin.change_pct is not None:
        details.append(f"Bitcoin is {bitcoin.change_pct:+.2f}%")
    if details:
        lines.append(", ".join(details) + ".")

    if vix.change_pct is not None and vix.price is not None:
        lines.append(f"Volatility is running with VIX at {vix.price:,.2f} ({vix.change_pct:+.2f}%).")

    if drivers:
        lines.append(f"Headline backdrop: {drivers[0]}")
    return " ".join(lines)


def _fed_context(fetcher: MarketDataFetcher) -> str:
    try:
        result = fetcher.fetch_effective_fed_funds_rate()
    except Exception as exc:
        logger.warning("market_update_fed_context_failed error=%s", exc)
        return "Latest Fed funds context was unavailable from FRED at runtime."
    if not result:
        return "Latest Fed funds context was unavailable from FRED at runtime."
    rate, as_of = result
    return f"The latest effective fed funds rate on FRED was {rate:.2f}% as of {as_of}."


def _watch_next(
    drivers: list[str],
    rates: list[InstrumentQuote],
    commodities: list[InstrumentQuote],
) -> list[str]:
    items: list[str] = []
    if drivers:
        items.append("Whether the headline themes above intensify or fade through the session.")
    us10y = _quote_lookup(rates).get("us10y")
    if us10y and us10y.price is not None:
        items.append(f"Treasury yields around {us10y.price:.2f}% for confirmation of the rates backdrop.")
    oil = _quote_lookup(commodities).get("wti")
    if oil and oil.price is not None:
        items.append(f"Energy sensitivity if WTI crude keeps moving away from ${oil.price:,.2f}.")
    items.append("Whether leadership broadens beyond the strongest sectors in the early tape.")
    return items[:4]


def build_market_update(
    now: datetime | None = None,
    settings: MarketUpdateSettings | None = None,
    data_fetcher: MarketDataFetcher | None = None,
    news_fetcher: NewsFetcher | None = None,
) -> MarketUpdateResult:
    settings = settings or load_market_update_settings()
    tz = ZoneInfo(settings.schedule_timezone)
    if now is None:
        generated_at = datetime.now(tz)
    elif now.tzinfo is None:
        # Treat naive datetimes as already in the target timezone so test fixtures
        # and cron callers don't drift depending on the host machine's local zone.
        generated_at = now.replace(tzinfo=tz)
    else:
        generated_at = now.astimezone(tz)

    timestamp_label = generated_at.strftime("%Y-%m-%d %I:%M %p %Z")
    subject = f"Today's Market Update | {generated_at.strftime('%a %b %d, %Y')}"

    data_fetcher = data_fetcher or MarketDataFetcher()
    news_fetcher = news_fetcher or NewsFetcher(data_fetcher.session)

    warnings: list[str] = []

    indexes = data_fetcher.fetch_major_indexes()
    rates = data_fetcher.fetch_rates_and_macro()
    commodities = data_fetcher.fetch_commodities()
    crypto = data_fetcher.fetch_crypto()
    vix = data_fetcher.fetch_vix()
    sectors = data_fetcher.fetch_sector_strength()

    for quote in [*indexes, *rates, *commodities, *crypto, vix]:
        if not quote.is_available:
            warnings.append(f"{quote.label} could not be fetched from {quote.source}.")

    try:
        headlines = news_fetcher.fetch_headlines()
    except Exception as exc:
        logger.warning("market_update_headlines_failed error=%s", exc)
        warnings.append(f"Headline feeds unavailable at runtime: {exc}")
        headlines = []

    drivers = summarize_market_drivers(headlines, limit=5)
    fed_context = _fed_context(data_fetcher)
    big_picture = _big_picture(indexes, rates, commodities, crypto, vix, drivers, generated_at)
    watch_next = _watch_next(drivers, rates, commodities)

    body = format_body(
        big_picture=big_picture,
        indexes=indexes,
        rates_and_macro=rates,
        fed_context=fed_context,
        commodities=commodities,
        crypto=crypto,
        drivers=drivers,
        sectors=sectors,
        vix=vix,
        headlines=headlines,
        watch_next=watch_next,
        warnings=warnings,
    )

    return MarketUpdateResult(
        subject=subject,
        body=body,
        timestamp_label=timestamp_label,
        warnings=warnings,
    )


def generate_market_update() -> str:
    return build_market_update().body


def run_market_update_job() -> MarketUpdateResult:
    """Called by the APScheduler on weekday mornings.

    Generates the market update and logs it. To post to a Discord channel,
    wire in bot.get_channel(id).send() here or use a webhook.
    """
    result = build_market_update()
    logger.info(
        "market_update_job_completed subject=%s warnings=%d",
        result.subject,
        len(result.warnings),
    )
    return result