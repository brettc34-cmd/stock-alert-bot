"""Alert throttling manager.

Controls maximum alerts sent per ticker and per run.
"""
from typing import Dict, Any
from datetime import datetime, timedelta, timezone


def should_send_alert(state: Dict[str, Any], ticker: str, max_per_ticker_per_hour: int, max_per_run: int) -> bool:
    sent = state.setdefault("alert_history", {})
    now = datetime.now(timezone.utc)

    # Prune older than 1 hour
    cutoff = now - timedelta(hours=1)
    for k, times in list(sent.items()):
        parsed = []
        for t in times:
            if isinstance(t, str):
                try:
                    dt = datetime.fromisoformat(t)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    parsed.append(dt)
                except ValueError:
                    continue
            elif isinstance(t, datetime):
                dt = t
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                parsed.append(dt)
        sent[k] = [t.isoformat() for t in parsed if t >= cutoff]
        if not sent[k]:
            del sent[k]

    per_ticker = sent.get(ticker, [])
    if len(per_ticker) >= max_per_ticker_per_hour:
        return False

    total_sent = sum(len(v) for v in sent.values())
    if total_sent >= max_per_run:
        return False

    return True


def record_alert(state: Dict[str, Any], ticker: str) -> None:
    sent = state.setdefault("alert_history", {})
    sent.setdefault(ticker, []).append(datetime.now(timezone.utc).isoformat())


__all__ = ["should_send_alert", "record_alert"]
