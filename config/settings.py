"""Runtime settings with YAML + environment overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict

from utils.config import load_features, load_thresholds, get_discord_webhook_url


@dataclass
class RuntimeSettings:
    discord_webhook_url: str
    alert_min_confidence: int = 50
    alert_cooldown_minutes: int = 90
    max_position_weight_add: float = 0.15
    trim_warning_weight: float = 0.20
    earnings_risk_window_days: int = 7
    enable_after_hours_alerts: bool = False
    log_level: str = "INFO"
    dashboard_port: int = 8000
    min_confirmations_normal: int = 2
    min_confirmations_high: int = 3
    stale_quote_max_age_seconds: int = 300
    breakout_volume_ratio: float = 1.5
    strong_breakout_volume_ratio: float = 2.0
    market_timezone: str = "US/Eastern"
    market_open: str = "09:30"
    market_close: str = "16:00"
    report_time: str = "21:00"
    report_days: int = 1


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


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


def build_runtime_settings(config_json: Dict[str, Any]) -> RuntimeSettings:
    thresholds = load_thresholds()
    features = load_features()

    confidence_cfg = thresholds.get("confidence", {})
    runtime_cfg = thresholds.get("runtime", {})
    portfolio_cfg = thresholds.get("portfolio", {})
    market_cfg = thresholds.get("market", {})
    market_hours_cfg = config_json.get("market_hours", {}) if isinstance(config_json.get("market_hours"), dict) else {}
    reporting_cfg = config_json.get("reporting", {}) if isinstance(config_json.get("reporting"), dict) else {}

    webhook = get_discord_webhook_url()

    return RuntimeSettings(
        discord_webhook_url=webhook,
        alert_min_confidence=_env_int("ALERT_MIN_CONFIDENCE", int(confidence_cfg.get("min_send_score", 50))),
        alert_cooldown_minutes=_env_int("ALERT_COOLDOWN_MINUTES", int(runtime_cfg.get("alert_cooldown_minutes", 90))),
        max_position_weight_add=_env_float("MAX_POSITION_WEIGHT_ADD", float(portfolio_cfg.get("max_position_weight_add", 0.15))),
        trim_warning_weight=_env_float("TRIM_WARNING_WEIGHT", float(portfolio_cfg.get("trim_warning_weight", 0.20))),
        earnings_risk_window_days=_env_int("EARNINGS_RISK_WINDOW_DAYS", int(runtime_cfg.get("earnings_risk_window_days", 7))),
        enable_after_hours_alerts=_env_bool("ENABLE_AFTER_HOURS_ALERTS", bool(features.get("runtime", {}).get("enable_after_hours_alerts", False))),
        log_level=os.getenv("LOG_LEVEL", str(runtime_cfg.get("log_level", "INFO"))),
        dashboard_port=_env_int("DASHBOARD_PORT", int(runtime_cfg.get("dashboard_port", 8000))),
        min_confirmations_normal=int(runtime_cfg.get("min_confirmations_normal", 2)),
        min_confirmations_high=int(runtime_cfg.get("min_confirmations_high", 3)),
        stale_quote_max_age_seconds=int(market_cfg.get("stale_quote_max_age_seconds", 300)),
        breakout_volume_ratio=float(market_cfg.get("breakout_volume_ratio", 1.5)),
        strong_breakout_volume_ratio=float(market_cfg.get("strong_breakout_volume_ratio", 2.0)),
        market_timezone=_env_str("MARKET_TIMEZONE", str(market_hours_cfg.get("timezone", "US/Eastern"))),
        market_open=_env_str("MARKET_OPEN", str(market_hours_cfg.get("open", "09:30"))),
        market_close=_env_str("MARKET_CLOSE", str(market_hours_cfg.get("close", "16:00"))),
        report_time=_env_str("REPORT_TIME", str(reporting_cfg.get("report_time", "21:00"))),
        report_days=_env_int("REPORT_DAYS", int(reporting_cfg.get("report_days", 1))),
    )
