"""Event calendar helpers for pre-trade event risk gating."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml


@dataclass
class EventRiskContext:
    active: bool
    horizon_hours: int
    events: List[Dict[str, Any]]


DEFAULT_MACRO_EVENTS = [
    {"name": "FOMC", "importance": "high"},
    {"name": "CPI", "importance": "high"},
    {"name": "PPI", "importance": "medium"},
    {"name": "NFP", "importance": "high"},
]


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def load_event_calendar(path: str = "config/events.yaml") -> Dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        return {"events": []}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            return {"events": []}
        events = data.get("events")
        if not isinstance(events, list):
            data["events"] = []
        return data
    except Exception:
        return {"events": []}


def resolve_event_risk(now: datetime, *, horizon_hours: int = 24, calendar: Dict[str, Any] | None = None) -> EventRiskContext:
    """Return events within horizon and whether high-impact risk is active."""
    cal = calendar or {"events": []}
    events = list(cal.get("events") or [])
    if not events:
        return EventRiskContext(active=False, horizon_hours=horizon_hours, events=[])

    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    horizon = now + timedelta(hours=max(1, int(horizon_hours)))

    in_window: List[Dict[str, Any]] = []
    high_count = 0
    for event in events:
        if not isinstance(event, dict):
            continue
        dt = _parse_iso(event.get("datetime"))
        if dt is None:
            continue
        if now <= dt <= horizon:
            item = {
                "name": str(event.get("name") or "event"),
                "importance": str(event.get("importance") or "low").lower(),
                "datetime": dt.isoformat(),
                "type": str(event.get("type") or "macro").lower(),
                "tickers": list(event.get("tickers") or []),
            }
            in_window.append(item)
            if item["importance"] == "high":
                high_count += 1

    return EventRiskContext(active=high_count > 0, horizon_hours=horizon_hours, events=in_window)
