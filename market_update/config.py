"""Settings for the daily market update."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


@dataclass
class MarketUpdateSettings:
    enabled: bool = True
    schedule_time: str = "07:00"
    schedule_timezone: str = "America/Chicago"


def load_market_update_settings() -> MarketUpdateSettings:
    return MarketUpdateSettings(
        enabled=_env_bool("MARKET_UPDATE_ENABLED", True),
        schedule_time=_env_str("MARKET_UPDATE_TIME", "07:00"),
        schedule_timezone=_env_str("MARKET_UPDATE_TIMEZONE", "America/Chicago"),
    )