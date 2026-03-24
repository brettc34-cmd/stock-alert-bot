"""Outcome analytics used to adapt brain weight multipliers."""

from __future__ import annotations

import sqlite3
from typing import Dict


def compute_brain_multipliers(conn: sqlite3.Connection, lookback: int = 250) -> Dict[str, float]:
    """Compute conservative multipliers from realized outcomes.

    Returns multipliers in range [0.85, 1.15] keyed by brain name.
    """
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT s.brain, o.return_pct
            FROM outcomes o
            JOIN signals s ON s.alert_id = o.alert_id
            WHERE o.return_pct IS NOT NULL
            ORDER BY o.close_time DESC
            LIMIT ?
            """,
            (int(lookback),),
        )
        rows = cur.fetchall()
    except sqlite3.OperationalError:
        return {}
    if not rows:
        return {}

    totals: Dict[str, float] = {}
    counts: Dict[str, int] = {}
    wins: Dict[str, int] = {}
    for brain, ret in rows:
        if not isinstance(brain, str):
            continue
        value = float(ret or 0.0)
        totals[brain] = totals.get(brain, 0.0) + value
        counts[brain] = counts.get(brain, 0) + 1
        if value > 0:
            wins[brain] = wins.get(brain, 0) + 1

    multipliers: Dict[str, float] = {}
    for brain, n in counts.items():
        if n < 10:
            continue
        avg_ret = totals.get(brain, 0.0) / n
        win_rate = wins.get(brain, 0) / n
        # Reward consistency and positive expectancy, clipped for stability.
        raw = 1.0 + (avg_ret * 2.0) + ((win_rate - 0.5) * 0.3)
        multipliers[brain] = max(0.85, min(1.15, raw))
    return multipliers
