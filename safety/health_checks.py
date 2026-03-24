"""Health checks and watchdog logic."""

from datetime import datetime, timedelta, timezone
from typing import Dict, Any


def _is_readable(path: str) -> bool:
    try:
        with open(path, "r"):
            return True
    except Exception:
        return False


def heartbeat_ok(last_run: datetime, max_age_minutes: int = 60) -> bool:
    now = datetime.now(timezone.utc)
    if last_run.tzinfo is None:
        last_run = last_run.replace(tzinfo=timezone.utc)
    return (now - last_run) <= timedelta(minutes=max_age_minutes)


def ensure_state_has_keys(state: Dict[str, Any]) -> None:
    state.setdefault("last_run", datetime.now(timezone.utc).isoformat())
    state.setdefault("errors", 0)
    state.setdefault("last_error", None)
    state.setdefault("suppression_counts", {})
    state.setdefault("cycle_metrics", {})


def health_status(state: Dict[str, Any], discord_webhook: str, portfolio_path: str = "config/portfolio.json") -> Dict[str, Any]:
    last_run_str = state.get("last_run")
    last_run = None
    if isinstance(last_run_str, str):
        try:
            last_run = datetime.fromisoformat(last_run_str)
        except ValueError:
            last_run = None

    heartbeat = heartbeat_ok(last_run) if isinstance(last_run, datetime) else False
    return {
        "status": "ok" if heartbeat else "degraded",
        "heartbeat_ok": heartbeat,
        "last_run": last_run_str,
        "discord_webhook_configured": bool(discord_webhook),
        "portfolio_readable": _is_readable(portfolio_path),
        "last_error": state.get("last_error"),
        "error_count": state.get("errors", 0),
        "suppression_counts": state.get("suppression_counts", {}),
        "cycle_metrics": state.get("cycle_metrics", {}),
    }
