"""Shared core service routines for dashboards, CLIs, and Discord interfaces."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from engine.ranking_engine import rank_signals
from engine.signal_models import Signal
from storage.sqlite_store import init_db
from config.settings import build_runtime_settings
from utils.config import load_json_file, save_json_file


def load_state(path: str = "state.json") -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    with open(p, "r") as f:
        return json.load(f)


def status_snapshot(state: Dict[str, Any] | None = None) -> Dict[str, Any]:
    state = state or load_state()
    cycle = state.get("cycle_metrics", {})
    return {
        "last_run": state.get("last_run"),
        "raw_signal_count": cycle.get("raw_signal_count", 0),
        "approved_count": cycle.get("approved_count", 0),
        "sent_count": cycle.get("sent_count", 0),
        "suppressed_counts": cycle.get("suppressed_counts", {}),
    }


def _signal_from_payload(payload: Dict[str, Any]) -> Signal:
    ts_raw = payload.get("timestamp")
    try:
        ts = datetime.fromisoformat(ts_raw) if isinstance(ts_raw, str) else datetime.now(timezone.utc)
    except ValueError:
        ts = datetime.now(timezone.utc)
    return Signal(
        ticker=payload.get("ticker", ""),
        signal_type=payload.get("signal_type") or payload.get("category", "unknown"),
        brain=payload.get("brain", "unknown"),
        direction=payload.get("direction", "neutral"),
        confidence=int(payload.get("confidence") or 0),
        priority=payload.get("priority", "moderate"),
        action_bias=payload.get("action_bias", "WATCH"),
        reason=payload.get("reason") or payload.get("summary") or "",
        why_it_matters=payload.get("why_it_matters") or payload.get("reason") or "",
        confirmations=payload.get("confirmations") or [],
        suppressions=payload.get("suppressions") or [],
        price=payload.get("price"),
        change_pct=payload.get("change_pct"),
        volume_ratio=payload.get("volume_ratio"),
        portfolio_weight=payload.get("portfolio_weight"),
        metadata=payload.get("metadata") or {},
        timestamp=ts,
        score_raw=int(payload.get("score_raw") or 0),
        cooldown_key=payload.get("cooldown_key") or "",
        evidence=payload.get("evidence") or [],
        portfolio_note=payload.get("portfolio_note") or "",
        summary=payload.get("summary") or payload.get("reason") or "",
    )


def get_top_signals(top_n: int = 5, limit: int = 100) -> List[Signal]:
    conn = init_db()
    cur = conn.cursor()
    cur.execute("SELECT payload FROM signals ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    signals: List[Signal] = []
    for row in rows:
        try:
            payload = json.loads(row[0] or "{}")
        except Exception:
            continue
        if not payload:
            continue
        signals.append(_signal_from_payload(payload))
    return rank_signals(signals, top_n=top_n) if signals else []


def run_pipeline(now_et_override: datetime | None = None) -> Dict[str, Any]:
    from bot import run_once

    return run_once(exit_on_market_closed=False, now_et_override=now_et_override)


def load_app_config(path: str = "config.json") -> Dict[str, Any]:
    return load_json_file(path)


def save_app_config(config: Dict[str, Any], path: str = "config.json") -> None:
    save_json_file(path, config)


def recent_alert_rows(limit: int = 5) -> List[Dict[str, Any]]:
    from engine.ranking_engine import ranking_score as _compute_ranking_score
    conn = init_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT ticker, brain, category, confidence, summary, ranking_score, created_at, payload
        FROM signals
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cur.fetchall()
    result = []
    for row in rows:
        ranking = row[5]
        if ranking is None:
            try:
                payload = json.loads(row[7] or "{}")
                if payload:
                    ranking = _compute_ranking_score(_signal_from_payload(payload))
            except Exception:
                ranking = None
        result.append({
            "ticker": row[0],
            "brain": row[1],
            "signal_type": row[2],
            "confidence": row[3],
            "summary": row[4],
            "ranking_score": ranking,
            "created_at": row[6],
        })
    return result


def alert_summary(limit: int = 5, state: Dict[str, Any] | None = None) -> Dict[str, Any]:
    rows = recent_alert_rows(limit=limit)
    state_snapshot = state or load_state()
    cycle = state_snapshot.get("cycle_metrics", {}) or {}
    suppressions = cycle.get("suppressed_counts", {}) or {}
    avg_ranking = 0.0
    ranking_values = [float(r["ranking_score"]) for r in rows if r.get("ranking_score") is not None]
    if ranking_values:
        avg_ranking = sum(ranking_values) / len(ranking_values)
    top_suppressions = sorted(suppressions.items(), key=lambda kv: kv[1], reverse=True)[:3]
    return {
        "last_run": state_snapshot.get("last_run"),
        "recent_alerts": rows,
        "average_ranking_score": round(avg_ranking, 2),
        "top_suppression_reasons": top_suppressions,
        "last_cycle_raw_signal_count": int(cycle.get("raw_signal_count", 0) or 0),
        "last_cycle_approved_count": int(cycle.get("approved_count", 0) or 0),
        "last_cycle_sent_count": int(cycle.get("sent_count", 0) or 0),
        "last_cycle_webhook_sent_count": int(cycle.get("webhook_sent_count", 0) or 0),
        "last_cycle_persist_failed_count": int(cycle.get("persist_failed_count", 0) or 0),
        "last_cycle_suppressed_counts": suppressions,
    }


def get_market_session_config(config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    cfg = config or load_app_config()
    settings = build_runtime_settings(cfg)
    return {
        "market_open": settings.market_open,
        "market_close": settings.market_close,
        "market_timezone": settings.market_timezone,
        "stocks": cfg.get("stocks", []),
    }


def update_market_config(market_open: str | None = None, market_close: str | None = None, tickers: List[str] | None = None, path: str = "config.json") -> Dict[str, Any]:
    cfg = load_app_config(path)
    market_hours = cfg.setdefault("market_hours", {})
    if market_open:
        market_hours["open"] = market_open
    if market_close:
        market_hours["close"] = market_close
    if tickers is not None:
        cfg["stocks"] = tickers
    save_app_config(cfg, path)
    return get_market_session_config(cfg)
