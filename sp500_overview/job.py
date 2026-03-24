"""Build, send, and schedule the S&P 500 overview."""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from alerts.discord_formatter import send_discord_message
from sp500_overview.config import SP500OverviewSettings, load_sp500_overview_settings
from sp500_overview.headlines import HeadlineFetcher
from sp500_overview.log_store import MessageLogStore
from sp500_overview.market_data import MarketDataFetcher
from sp500_overview.models import DeliveryResult, SP500OverviewMessage
from sp500_overview.summary import generate_summary
from utils.config import get_discord_webhook_url

logger = logging.getLogger(__name__)


def _resolve_now(now: datetime | None, timezone_name: str) -> datetime:
    tz = ZoneInfo(timezone_name)
    if now is None:
        return datetime.now(tz)
    if now.tzinfo is None:
        return now.replace(tzinfo=tz)
    return now.astimezone(tz)


def build_sp500_overview(
    now: datetime | None = None,
    settings: SP500OverviewSettings | None = None,
    market_data_fetcher: MarketDataFetcher | None = None,
    headline_fetcher: HeadlineFetcher | None = None,
) -> SP500OverviewMessage:
    settings = settings or load_sp500_overview_settings()
    generated_at = _resolve_now(now, settings.schedule_timezone)

    market_data_fetcher = market_data_fetcher or MarketDataFetcher()
    headline_fetcher = headline_fetcher or HeadlineFetcher(market_data_fetcher.session)

    snapshot = market_data_fetcher.fetch_snapshot(now=generated_at)
    try:
        headlines = headline_fetcher.fetch_headlines()
    except Exception as exc:
        logger.warning("sp500_overview_headlines_failed error=%s", exc)
        snapshot.warnings.append(f"Headline data could not be retrieved: {exc}")
        headlines = []

    return generate_summary(snapshot=snapshot, headlines=headlines, generated_at=generated_at, settings=settings)


def generate_sp500_overview() -> str:
    return build_sp500_overview().body


def send_sp500_overview(
    message: SP500OverviewMessage | None = None,
    settings: SP500OverviewSettings | None = None,
    log_store: MessageLogStore | None = None,
) -> DeliveryResult:
    settings = settings or load_sp500_overview_settings()
    message = message or build_sp500_overview(settings=settings)
    warnings = list(message.warnings)

    try:
        webhook_url = get_discord_webhook_url()
        sent = send_discord_message(webhook_url, message.body)
        destination = "discord-webhook" if sent else ""
        if not sent:
            warnings.append("Discord webhook delivery failed.")
    except Exception as exc:
        sent = False
        destination = ""
        warnings.append(f"Delivery failed: {exc}")
        logger.warning("sp500_overview_delivery_failed error=%s", exc)

    result = DeliveryResult(
        subject=message.subject,
        body=message.body,
        timestamp_label=message.timestamp_label,
        delivery_method="discord",
        destination=destination,
        sent=sent,
        warnings=warnings,
    )
    (log_store or MessageLogStore(settings.log_path)).append(result)
    return result


def run_sp500_overview_job() -> DeliveryResult:
    settings = load_sp500_overview_settings()
    result = send_sp500_overview(settings=settings)
    logger.info(
        "sp500_overview_job_completed method=%s sent=%s destination=%s warnings=%d",
        result.delivery_method,
        result.sent,
        result.destination,
        len(result.warnings),
    )
    return result


def should_run_now(now: datetime | None = None, settings: SP500OverviewSettings | None = None, tolerance_minutes: int = 10) -> bool:
    settings = settings or load_sp500_overview_settings()
    current = _resolve_now(now, settings.schedule_timezone)
    try:
        hour_text, minute_text = settings.schedule_time.split(":", 1)
        scheduled_hour = int(hour_text)
        scheduled_minute = int(minute_text)
    except Exception:
        scheduled_hour = 7
        scheduled_minute = 0
    delta_minutes = abs((current.hour * 60 + current.minute) - (scheduled_hour * 60 + scheduled_minute))
    return delta_minutes <= max(0, tolerance_minutes)