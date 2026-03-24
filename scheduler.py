"""Cross-platform internal scheduler for recurring bot cycles."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta
from dataclasses import dataclass

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
except Exception:  # pragma: no cover
    @dataclass
    class _FallbackJob:
        id: str

    class BackgroundScheduler:  # type: ignore[override]
        def __init__(self, timezone=None):
            self.timezone = timezone
            self._jobs = []

        def add_job(self, func, trigger, id, replace_existing=True):
            self._jobs = [j for j in self._jobs if j.id != id]
            self._jobs.append(_FallbackJob(id=id))

        def get_jobs(self):
            return list(self._jobs)

        def start(self):
            return None

        def shutdown(self, wait=False):
            return None

    class CronTrigger:  # type: ignore[override]
        def __init__(self, **kwargs):
            self.kwargs = kwargs

from config.settings import RuntimeSettings, build_runtime_settings
from market_update.config import load_market_update_settings
from market_update.generator import run_market_update_job
from sp500_overview.config import load_sp500_overview_settings
from sp500_overview.job import run_sp500_overview_job
from services.reporting import generate_report

logger = logging.getLogger(__name__)


def _parse_hhmm(value: str, default_hour: int, default_minute: int) -> tuple[int, int]:
    try:
        hh, mm = value.split(":", 1)
        return int(hh), int(mm)
    except Exception:
        return default_hour, default_minute


def run_report_job(report_days: int, report_func=generate_report) -> None:
    try:
        output = report_func(days=report_days)
        logger.info("nightly_report_generated days=%s output=%s", report_days, output)
    except Exception as exc:
        logger.exception("nightly_report_failed days=%s error=%s", report_days, exc)


def build_scheduler(settings: RuntimeSettings, run_job) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=settings.market_timezone)
    market_update_settings = load_market_update_settings()
    sp500_overview_settings = load_sp500_overview_settings()

    open_hour, open_minute = _parse_hhmm(settings.market_open, 9, 30)
    scheduler.add_job(
        run_job,
        CronTrigger(day_of_week="mon-fri", hour=open_hour, minute=open_minute, timezone=settings.market_timezone),
        id="market_open_cycle",
        replace_existing=True,
    )

    if os.environ.get("SCHEDULER_RUN_NEAR_CLOSE", "1").strip().lower() in {"1", "true", "yes", "on"}:
        close_hour, close_minute = _parse_hhmm(settings.market_close, 16, 0)
        close_dt = datetime(2000, 1, 1, close_hour, close_minute)
        offset = int(os.environ.get("SCHEDULER_CLOSE_OFFSET_MINUTES", "10"))
        near_close = close_dt - timedelta(minutes=max(0, offset))
        scheduler.add_job(
            run_job,
            CronTrigger(
                day_of_week="mon-fri",
                hour=near_close.hour,
                minute=near_close.minute,
                timezone=settings.market_timezone,
            ),
            id="near_close_cycle",
            replace_existing=True,
        )

    report_hour, report_minute = _parse_hhmm(settings.report_time, 21, 0)
    scheduler.add_job(
        lambda: run_report_job(settings.report_days),
        CronTrigger(day_of_week="mon-sun", hour=report_hour, minute=report_minute, timezone=settings.market_timezone),
        id="nightly_report",
        replace_existing=True,
    )

    if market_update_settings.enabled:
        update_hour, update_minute = _parse_hhmm(market_update_settings.schedule_time, 7, 0)
        scheduler.add_job(
            run_market_update_job,
            CronTrigger(
                day_of_week="mon-fri",
                hour=update_hour,
                minute=update_minute,
                timezone=market_update_settings.schedule_timezone,
            ),
            id="daily_market_update",
            replace_existing=True,
        )

    if sp500_overview_settings.enabled:
        sp500_hour, sp500_minute = _parse_hhmm(sp500_overview_settings.schedule_time, 7, 0)
        scheduler.add_job(
            run_sp500_overview_job,
            CronTrigger(
                day_of_week="mon-fri",
                hour=sp500_hour,
                minute=sp500_minute,
                timezone=sp500_overview_settings.schedule_timezone,
            ),
            id="daily_sp500_overview",
            replace_existing=True,
        )

    return scheduler


def run_internal_scheduler(run_job) -> None:
    if os.environ.get("DISABLE_INTERNAL_SCHEDULER", "0").strip().lower() in {"1", "true", "yes", "on"}:
        logger.info("internal_scheduler_disabled")
        return

    try:
        import json

        with open("config.json", "r") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}

    settings = build_runtime_settings(cfg)
    scheduler = build_scheduler(settings, run_job)
    scheduler.start()
    logger.info(
        "internal_scheduler_started timezone=%s open=%s close=%s",
        settings.market_timezone,
        settings.market_open,
        settings.market_close,
    )

    try:
        while True:
            time.sleep(30)
    except KeyboardInterrupt:
        logger.info("internal_scheduler_stopping")
    finally:
        scheduler.shutdown(wait=False)
