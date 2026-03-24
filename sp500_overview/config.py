"""Environment-backed settings for the S&P 500 overview feature."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


@dataclass
class SP500OverviewSettings:
    enabled: bool = True
    schedule_time: str = "07:00"
    schedule_timezone: str = "America/Chicago"
    max_words: int = 250
    subject_prefix: str = ""
    log_path: str = "storage/sp500_overview_history.jsonl"


def load_sp500_overview_settings() -> SP500OverviewSettings:
    return SP500OverviewSettings(
        enabled=_env_bool("SP500_OVERVIEW_ENABLED", True),
        schedule_time=_env_str("SP500_OVERVIEW_TIME", "07:00"),
        schedule_timezone=_env_str("SP500_OVERVIEW_TIMEZONE", "America/Chicago"),
        max_words=max(120, _env_int("SP500_OVERVIEW_MAX_WORDS", 250)),
        subject_prefix=_env_str("SP500_OVERVIEW_SUBJECT_PREFIX", ""),
        log_path=_env_str("SP500_OVERVIEW_LOG_PATH", "storage/sp500_overview_history.jsonl"),
    )