"""Walk-forward analytics for rolling out-of-sample stability checks."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from statistics import mean, pstdev
from typing import Any, Dict, List


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except Exception:
            return None


def _window_stats(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"count": 0, "mean_pct": 0.0, "vol_pct": 0.0, "sharpe_like": 0.0}
    mu = mean(values)
    vol = pstdev(values) if len(values) > 1 else 0.0
    sharpe = (mu / vol) if vol > 0 else 0.0
    return {
        "count": len(values),
        "mean_pct": round(mu * 100.0, 3),
        "vol_pct": round(vol * 100.0, 3),
        "sharpe_like": round(sharpe, 3),
    }


def walkforward_summary(conn: sqlite3.Connection, *, train_days: int = 90, test_days: int = 30, steps: int = 4) -> Dict[str, Any]:
    cur = conn.cursor()
    try:
        cur.execute("SELECT close_time, return_pct FROM outcomes WHERE return_pct IS NOT NULL ORDER BY close_time ASC")
        rows = cur.fetchall()
    except sqlite3.OperationalError:
        return {"windows": [], "note": "missing_outcomes_table"}
    series = []
    for close_time, ret in rows:
        dt = _parse_dt(close_time)
        if dt is None:
            continue
        series.append((dt, float(ret or 0.0)))

    if len(series) < 20:
        return {"windows": [], "note": "insufficient_outcomes"}

    end = series[-1][0]
    windows = []
    for i in range(max(1, steps)):
        test_end = end - timedelta(days=i * test_days)
        test_start = test_end - timedelta(days=test_days)
        train_start = test_start - timedelta(days=train_days)

        train_vals = [ret for dt, ret in series if train_start <= dt < test_start]
        test_vals = [ret for dt, ret in series if test_start <= dt < test_end]
        if not train_vals and not test_vals:
            continue
        windows.append(
            {
                "train_start": train_start.isoformat(),
                "train_end": test_start.isoformat(),
                "test_start": test_start.isoformat(),
                "test_end": test_end.isoformat(),
                "train": _window_stats(train_vals),
                "test": _window_stats(test_vals),
            }
        )

    return {"windows": windows}
