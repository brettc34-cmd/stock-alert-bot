"""Offline analytics reporting helpers."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List


def _markdown_table(headers: List[str], rows: List[List[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(item) for item in row) + " |")
    return "\n".join(lines)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    for parser in (datetime.fromisoformat,):
        try:
            dt = parser(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            continue
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def generate_markdown_report(days: int = 7, db_path: str = "./storage/stock_alerts.db", reports_dir: str = "reports") -> Path:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT alert_id, ticker, brain, confidence, ranking_score, gating_reasons, created_at FROM signals ORDER BY created_at DESC"
    )
    rows = cur.fetchall()

    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, days))
    filtered = []
    for row in rows:
        created = _parse_dt(row[6])
        if created is None or created < cutoff:
            continue
        filtered.append(
            {
                "alert_id": row[0],
                "ticker": row[1],
                "brain": row[2],
                "confidence": row[3],
                "ranking_score": float(row[4]) if row[4] is not None else None,
                "gating_reasons": json.loads(row[5]) if row[5] else [],
                "created_at": created,
            }
        )

    alerts_sent = len(filtered)
    ranking_values = [row["ranking_score"] for row in filtered if row["ranking_score"] is not None]
    avg_ranking_score = round(sum(ranking_values) / len(ranking_values), 2) if ranking_values else 0.0

    suppression_counts = Counter()
    ticker_counts = Counter()
    hour_counts = Counter()
    brain_scores: Dict[str, List[float]] = defaultdict(list)
    brain_counts = Counter()

    for row in filtered:
        ticker_counts[row["ticker"]] += 1
        hour_counts[row["created_at"].strftime("%H:00")] += 1
        brain_counts[row["brain"]] += 1
        if row["ranking_score"] is not None:
            brain_scores[row["brain"]].append(row["ranking_score"])
        for reason in row["gating_reasons"]:
            suppression_counts[reason] += 1

    avg_by_brain = sorted(
        ((brain, round(sum(vals) / len(vals), 2)) for brain, vals in brain_scores.items() if vals),
        key=lambda item: item[1],
        reverse=True,
    )
    freq_by_brain = brain_counts.most_common()

    report_lines = [
        f"# Stock Alert Report ({days} day window)",
        "",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        f"Alerts sent: {alerts_sent}",
        f"Average ranking score: {avg_ranking_score}",
        "",
        "## Suppression reason distribution",
        _markdown_table(["Reason", "Count"], [[k, v] for k, v in suppression_counts.most_common()] or [["none", 0]]),
        "",
        "## Top brains by average ranking score",
        _markdown_table(["Brain", "Avg ranking score"], [[k, v] for k, v in avg_by_brain] or [["none", 0]]),
        "",
        "## Top brains by frequency",
        _markdown_table(["Brain", "Alert count"], [[k, v] for k, v in freq_by_brain] or [["none", 0]]),
        "",
        "## Alert frequency by ticker",
        _markdown_table(["Ticker", "Alerts"], [[k, v] for k, v in ticker_counts.most_common()] or [["none", 0]]),
        "",
        "## Alert frequency by time of day (UTC)",
        _markdown_table(["Hour", "Alerts"], [[k, v] for k, v in sorted(hour_counts.items())] or [["none", 0]]),
        "",
    ]

    out_dir = Path(reports_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.md"
    out_path.write_text("\n".join(report_lines), encoding="utf-8")
    return out_path


def list_reports(reports_dir: str = "reports") -> List[Path]:
    path = Path(reports_dir)
    if not path.exists():
        return []
    return sorted([item for item in path.iterdir() if item.is_file()], reverse=True)


def generate_report(days: int = 7, db_path: str = "./storage/stock_alerts.db", reports_dir: str = "reports") -> Path:
    return generate_markdown_report(days=days, db_path=db_path, reports_dir=reports_dir)
