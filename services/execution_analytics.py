"""Execution analytics for dispatch latency and proxy slippage."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


SCHEMA = """
CREATE TABLE IF NOT EXISTS execution_metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  alert_id TEXT,
  ticker TEXT,
  decision_time TEXT,
  dispatch_time TEXT,
  latency_ms REAL,
  decision_price REAL,
  dispatch_price REAL,
  proxy_slippage_bps REAL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def init_execution_db(db_path: str = "./storage/stock_alerts.db") -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30.0)
    cur = conn.cursor()
    cur.executescript(SCHEMA)
    conn.commit()
    return conn


def record_execution_metric(
    conn: sqlite3.Connection,
    *,
    alert_id: str,
    ticker: str,
    decision_time: datetime,
    dispatch_time: datetime,
    decision_price: float | None,
    dispatch_price: float | None,
) -> None:
    latency_ms = max(0.0, (dispatch_time - decision_time).total_seconds() * 1000.0)
    slip_bps = None
    if isinstance(decision_price, (int, float)) and isinstance(dispatch_price, (int, float)) and decision_price != 0:
        slip_bps = ((dispatch_price - decision_price) / decision_price) * 10000.0

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO execution_metrics(alert_id, ticker, decision_time, dispatch_time, latency_ms, decision_price, dispatch_price, proxy_slippage_bps)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            alert_id,
            ticker,
            decision_time.isoformat(),
            dispatch_time.isoformat(),
            float(latency_ms),
            float(decision_price) if isinstance(decision_price, (int, float)) else None,
            float(dispatch_price) if isinstance(dispatch_price, (int, float)) else None,
            float(slip_bps) if isinstance(slip_bps, (int, float)) else None,
        ),
    )
    conn.commit()


def execution_summary(conn: sqlite3.Connection, limit: int = 500) -> Dict[str, Any]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT latency_ms, proxy_slippage_bps
        FROM execution_metrics
        ORDER BY id DESC
        LIMIT ?
        """,
        (int(limit),),
    )
    rows = cur.fetchall()
    if not rows:
        return {"count": 0, "avg_latency_ms": 0.0, "avg_proxy_slippage_bps": 0.0}

    latencies = [float(r[0]) for r in rows if isinstance(r[0], (int, float))]
    slips = [float(r[1]) for r in rows if isinstance(r[1], (int, float))]
    return {
        "count": len(rows),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
        "avg_proxy_slippage_bps": round(sum(slips) / len(slips), 2) if slips else 0.0,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
