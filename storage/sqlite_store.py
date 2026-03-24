import json
import logging
import sqlite3
import uuid
from pathlib import Path


logger = logging.getLogger("storage.sqlite_store")


def _json_dumps_safe(value) -> str:
    """Serialize payloads that may contain datetimes or other non-JSON-native values."""
    return json.dumps(value, default=str)


DB_SCHEMA = '''
CREATE TABLE IF NOT EXISTS signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  alert_id TEXT UNIQUE,
  ticker TEXT,
  brain TEXT,
  category TEXT,
  confidence INTEGER,
  summary TEXT,
  raw_quote TEXT,
  brain_scores TEXT,
  ranking_score REAL,
  gating_reasons TEXT,
  payload TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
'''


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = cur.fetchall()
    return any(c[1] == column for c in cols)


def init_db(db_path: str = "./storage/stock_alerts.db") -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30.0)
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.executescript(DB_SCHEMA)

    if not _has_column(conn, "signals", "alert_id"):
        cur.execute("ALTER TABLE signals ADD COLUMN alert_id TEXT")
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_signals_alert_id ON signals(alert_id)")
    if not _has_column(conn, "signals", "raw_quote"):
        cur.execute("ALTER TABLE signals ADD COLUMN raw_quote TEXT")
    if not _has_column(conn, "signals", "brain_scores"):
        cur.execute("ALTER TABLE signals ADD COLUMN brain_scores TEXT")
    if not _has_column(conn, "signals", "ranking_score"):
        cur.execute("ALTER TABLE signals ADD COLUMN ranking_score REAL")
    if not _has_column(conn, "signals", "gating_reasons"):
        cur.execute("ALTER TABLE signals ADD COLUMN gating_reasons TEXT")

    _backfill_ranking_scores(conn)
    conn.commit()
    return conn


def _backfill_ranking_scores(conn: sqlite3.Connection) -> None:
    """Compute and persist ranking_score for any rows where it is NULL."""
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, payload FROM signals WHERE ranking_score IS NULL AND payload IS NOT NULL")
        rows = cur.fetchall()

        category_priority = {
            "unusual_volume": 3,
            "breakout": 5,
            "trend_continuation": 5,
            "dip": 4,
            "quality_dip": 4,
            "buy_the_dip": 4,
            "risk": 2,
            "concentration_risk": 2,
            "macro_divergence": 2,
        }

        for row_id, payload_str in rows:
            try:
                payload = json.loads(payload_str or "{}")
                if not payload:
                    continue
                signal_type = payload.get("signal_type") or payload.get("category", "unknown")
                confidence = int(payload.get("confidence") or 0)
                pr = category_priority.get(signal_type, 1)
                score = (confidence * 10) + (pr * 100)
                cur.execute("UPDATE signals SET ranking_score = ? WHERE id = ?", (float(score), row_id))
            except Exception:
                continue
        conn.commit()
    except Exception:
        pass


def save_signal(conn: sqlite3.Connection, signal, analytics_context=None) -> str | None:
    analytics_context = analytics_context or {}
    raw_quote = analytics_context.get("raw_quote")
    brain_scores = analytics_context.get("brain_scores", {signal.brain: signal.confidence})
    ranking_score = analytics_context.get("ranking_score")
    gating_reasons = analytics_context.get("gating_reasons", signal.suppressions or [])

    for attempt in range(3):
        try:
            cur = conn.cursor()
            existing_alert_id = (signal.metadata or {}).get("alert_id")
            alert_id = existing_alert_id or str(uuid.uuid4())
            signal.metadata["alert_id"] = alert_id
            payload = _json_dumps_safe(
                {
                    "alert_id": alert_id,
                    "ticker": signal.ticker,
                    "brain": signal.brain,
                    "category": signal.signal_type,
                    "signal_type": signal.signal_type,
                    "direction": signal.direction,
                    "score_raw": signal.score_raw,
                    "confidence": signal.confidence,
                    "priority": signal.priority,
                    "summary": signal.summary,
                    "reason": signal.reason,
                    "why_it_matters": signal.why_it_matters,
                    "action_bias": signal.action_bias,
                    "confirmations": signal.confirmations,
                    "suppressions": signal.suppressions,
                    "evidence": signal.evidence,
                    "price": signal.price,
                    "change_pct": signal.change_pct,
                    "volume_ratio": signal.volume_ratio,
                    "portfolio_weight": signal.portfolio_weight,
                    "portfolio_note": signal.portfolio_note,
                    "metadata": signal.metadata,
                    "timestamp": str(signal.timestamp),
                }
            )
            cur.execute(
                """
                INSERT INTO signals (
                  alert_id, ticker, brain, category, confidence, summary,
                  raw_quote, brain_scores, ranking_score, gating_reasons, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert_id,
                    signal.ticker,
                    signal.brain,
                    signal.category,
                    signal.confidence,
                    signal.summary,
                    _json_dumps_safe(raw_quote) if raw_quote is not None else None,
                    _json_dumps_safe(brain_scores),
                    float(ranking_score) if ranking_score is not None else None,
                    _json_dumps_safe(gating_reasons),
                    payload,
                ),
            )
            conn.commit()
            return alert_id
        except sqlite3.IntegrityError as exc:
            # If an alert_id collided, regenerate and retry. Any other integrity error should stop.
            if "alert_id" in str(exc).lower() and attempt < 2:
                signal.metadata["alert_id"] = str(uuid.uuid4())
                continue
            logger.exception(
                "save_signal_integrity_error ticker=%s brain=%s error=%s",
                signal.ticker,
                signal.brain,
                exc,
            )
            return None
        except sqlite3.OperationalError as exc:
            # Retries improve resilience against transient "database is locked" errors.
            if "locked" in str(exc).lower() and attempt < 2:
                continue
            logger.exception(
                "save_signal_operational_error ticker=%s brain=%s error=%s",
                signal.ticker,
                signal.brain,
                exc,
            )
            return None
        except Exception as exc:
            logger.exception(
                "save_signal_error ticker=%s brain=%s error=%s",
                signal.ticker,
                signal.brain,
                exc,
            )
            return None
    return None
