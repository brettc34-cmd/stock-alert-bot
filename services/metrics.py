"""Prometheus metrics for stock-alert-bot observability."""

from __future__ import annotations

from typing import Dict

try:
    from prometheus_client import Counter, Histogram, CONTENT_TYPE_LATEST, generate_latest
except Exception:  # pragma: no cover - optional metrics dependency
    Counter = None
    Histogram = None
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4"

    def generate_latest() -> bytes:
        return b""


QUOTE_FETCH_TOTAL = Counter(
    "stock_alert_quote_fetch_total",
    "Market quote fetch outcomes",
    ["status"],
) if Counter else None

QUOTE_FETCH_LATENCY_SECONDS = Histogram(
    "stock_alert_quote_fetch_latency_seconds",
    "Market quote fetch latency seconds",
    buckets=(0.1, 0.3, 0.6, 1.0, 2.0, 5.0, 10.0),
) if Histogram else None

CYCLE_TOTAL = Counter(
    "stock_alert_cycle_total",
    "Pipeline signal counts per cycle",
    ["stage"],
) if Counter else None

SUPPRESSIONS_TOTAL = Counter(
    "stock_alert_suppressions_total",
    "Suppressed signals by reason",
    ["reason"],
) if Counter else None

INTERACTIVE_COMMAND_TOTAL = Counter(
    "stock_alert_interactive_command_total",
    "Interactive Discord command executions",
    ["command", "status"],
) if Counter else None

INTERACTIVE_COMMAND_LATENCY_SECONDS = Histogram(
    "stock_alert_interactive_command_latency_seconds",
    "Interactive Discord command latency",
    ["command"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
) if Histogram else None


def record_quote_fetch(status: str, duration_seconds: float) -> None:
    if QUOTE_FETCH_TOTAL is not None:
        QUOTE_FETCH_TOTAL.labels(status=status).inc()
    if QUOTE_FETCH_LATENCY_SECONDS is not None:
        QUOTE_FETCH_LATENCY_SECONDS.observe(max(0.0, float(duration_seconds)))


def record_cycle_metrics(raw_count: int, approved_count: int, sent_count: int) -> None:
    if CYCLE_TOTAL is None:
        return
    CYCLE_TOTAL.labels(stage="raw").inc(max(0, int(raw_count)))
    CYCLE_TOTAL.labels(stage="approved").inc(max(0, int(approved_count)))
    CYCLE_TOTAL.labels(stage="sent").inc(max(0, int(sent_count)))


def record_suppressions(suppressed_counts: Dict[str, int]) -> None:
    if SUPPRESSIONS_TOTAL is None:
        return
    for reason, count in (suppressed_counts or {}).items():
        SUPPRESSIONS_TOTAL.labels(reason=str(reason)).inc(max(0, int(count)))


def render_metrics_payload() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST


def record_interactive_command(command: str, status: str, duration_seconds: float) -> None:
    if INTERACTIVE_COMMAND_TOTAL is not None:
        INTERACTIVE_COMMAND_TOTAL.labels(command=command, status=status).inc()
    if INTERACTIVE_COMMAND_LATENCY_SECONDS is not None:
        INTERACTIVE_COMMAND_LATENCY_SECONDS.labels(command=command).observe(max(0.0, float(duration_seconds)))
