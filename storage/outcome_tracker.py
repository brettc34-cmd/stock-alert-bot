"""Track signal outcomes for later evaluation."""

import sqlite3
from pathlib import Path
import json
from typing import Any

SCHEMA = '''
CREATE TABLE IF NOT EXISTS outcomes (
    alert_id TEXT PRIMARY KEY,
  ticker TEXT,
  signal_time TIMESTAMP,
  action_bias TEXT,
  outcome TEXT,
  close_time TIMESTAMP,
  return_pct REAL
);
'''


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({table})")
        cols = cur.fetchall()
        return any(c[1] == column for c in cols)


def init_outcomes_db(db_path: str = "./storage/stock_alerts.db") -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript(SCHEMA)
    if not _has_column(conn, "outcomes", "alert_id"):
        cur.executescript(
            """
            ALTER TABLE outcomes RENAME TO outcomes_legacy;
            CREATE TABLE outcomes (
              alert_id TEXT PRIMARY KEY,
              ticker TEXT,
              signal_time TIMESTAMP,
              action_bias TEXT,
              outcome TEXT,
              close_time TIMESTAMP,
              return_pct REAL
            );
            INSERT INTO outcomes(alert_id, ticker, signal_time, action_bias, outcome, close_time, return_pct)
            SELECT CAST(id AS TEXT), ticker, signal_time, action_bias, outcome, close_time, return_pct
            FROM outcomes_legacy;
            DROP TABLE outcomes_legacy;
            """
        )
    conn.commit()
    return conn


def record_outcome(conn: sqlite3.Connection, signal: Any, outcome: str, return_pct: float) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR REPLACE INTO outcomes
        (alert_id, ticker, signal_time, action_bias, outcome, close_time, return_pct)
        VALUES (?, ?, ?, ?, ?, datetime('now'), ?)
        """,
        (signal.alert_id, signal.ticker, str(signal.timestamp), signal.action_bias, outcome, return_pct),
    )
    conn.commit()


def evaluate_pending_outcomes(conn: sqlite3.Connection, signal_db_path: str = "./storage/stock_alerts.db") -> None:
    """Evaluate outcome for signals that haven't been recorded yet."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT alert_id, ticker, payload
        FROM signals
        WHERE alert_id IS NOT NULL
          AND alert_id NOT IN (SELECT alert_id FROM outcomes)
        """
    )
    rows = cur.fetchall()

    for alert_id, ticker, payload_json in rows:
        try:
            payload = json.loads(payload_json)
        except Exception:
            continue

        price_then = payload.get("price")
        if price_then is None:
            continue

        # Use latest signal price in the database as the latest market price approximation
        cur.execute("SELECT payload FROM signals WHERE ticker = ? ORDER BY created_at DESC LIMIT 1", (ticker,))
        row = cur.fetchone()
        if not row:
            continue

        try:
            latest = json.loads(row[0])
        except Exception:
            continue

        price_now = latest.get("price")
        if price_now is None:
            continue

        return_pct = (price_now - price_then) / price_then if price_then else 0.0
        outcome = "win" if return_pct > 0 else "loss"

        # Use a minimal object for record_outcome
        class SigObj:
            def __init__(self, alert_id, ticker, timestamp, action_bias):
                self.alert_id = alert_id
                self.ticker = ticker
                self.timestamp = timestamp
                self.action_bias = action_bias

        record_outcome(
            conn,
            SigObj(alert_id, ticker, payload.get("timestamp"), payload.get("action_bias", "")),
            outcome,
            return_pct,
        )
