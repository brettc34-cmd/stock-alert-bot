"""Attribution analytics by brain, regime, and action bias."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from typing import Any, Dict, Iterable


def _aggregate(rows: Iterable[tuple[str, float]]) -> Dict[str, Dict[str, Any]]:
    acc: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"count": 0, "wins": 0, "avg_return_pct": 0.0, "sum_ret": 0.0})
    for key, ret in rows:
        bucket = acc[key]
        bucket["count"] += 1
        value = float(ret or 0.0)
        bucket["sum_ret"] += value
        if value > 0:
            bucket["wins"] += 1

    out: Dict[str, Dict[str, Any]] = {}
    for key, bucket in acc.items():
        n = max(1, bucket["count"])
        out[key] = {
            "count": bucket["count"],
            "win_rate": round(bucket["wins"] / n, 4),
            "avg_return_pct": round((bucket["sum_ret"] / n) * 100.0, 3),
        }
    return out


def attribution_summary(conn: sqlite3.Connection, limit: int = 1000) -> Dict[str, Any]:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT s.brain, o.return_pct, s.payload
            FROM outcomes o
            JOIN signals s ON s.alert_id = o.alert_id
            WHERE o.return_pct IS NOT NULL
            ORDER BY o.close_time DESC
            LIMIT ?
            """,
            (int(limit),),
        )
        rows = cur.fetchall()
    except sqlite3.OperationalError:
        rows = []
    if not rows:
        return {
            "by_brain": {},
            "by_regime": {},
            "by_action_bias": {},
        }

    by_brain_input = []
    by_regime_input = []
    by_action_input = []

    for brain, ret, payload in rows:
        by_brain_input.append((str(brain), float(ret or 0.0)))
        regime = "unknown"
        action = "unknown"
        try:
            p = json.loads(payload or "{}")
            meta = p.get("metadata") or {}
            regime = str(meta.get("market_regime") or "unknown")
            action = str(p.get("action_bias") or "unknown")
        except Exception:
            pass
        by_regime_input.append((regime, float(ret or 0.0)))
        by_action_input.append((action, float(ret or 0.0)))

    return {
        "by_brain": _aggregate(by_brain_input),
        "by_regime": _aggregate(by_regime_input),
        "by_action_bias": _aggregate(by_action_input),
    }
