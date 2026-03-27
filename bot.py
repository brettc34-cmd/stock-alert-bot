import json
import logging
import argparse
from datetime import datetime, time, timezone
from typing import Any, Dict, List

try:
    import pytz
except Exception:  # pragma: no cover - fallback path for environments without pytz
    pytz = None

from alerts.digest_formatter import format_digest, format_digest_payload
from alerts.discord_formatter import (
    send_discord_message,
    send_discord_payload,
    format_signal,
    self_check_discord_webhook,
)
from brains.analyst_brain import analyze as analyst_analyze
from brains.buffett_brain import analyze as buffett_analyze
from brains.dalio_brain import analyze as dalio_analyze
from brains.druckenmiller_brain import analyze as druck_analyze
from brains.lynch_brain import analyze as lynch_analyze
from brains.quant_brain import process_ladder_and_volume
from brains.sector_rotation_brain import analyze as sector_rotation_analyze
from brains.soros_brain import analyze as soros_analyze
from config.settings import build_runtime_settings
from data.event_calendar import load_event_calendar, resolve_event_risk
from data.macro_data import fetch_macro_snapshot
from data.market_data import fetch_quote
from data.portfolio_data import load_portfolio
from engine.context_overlay import apply_context_overlays
from engine.portfolio_optimizer import optimize_targets
from engine.regime_engine import classify_regime, regime_allows_signal
from engine import decision_engine, throttler, verification_engine
from engine.ranking_engine import rank_signals, ranking_score
from engine.signal_models import Signal
from engine.signal_completion import complete_signal_for_premium_quality
from engine.state_manager import initialize_premium_state, update_cycle_metrics, sanitize_state_for_json
from safety.data_validation import validate_config, validate_quote
from safety.health_checks import ensure_state_has_keys
from services.alert_router import AlertRouter
from services.health import build_health
from services.execution_analytics import init_execution_db, record_execution_metric, execution_summary
from services.summary_engine import build_daily_summary
from services.metrics import record_cycle_metrics, record_suppressions
from services.attribution import attribution_summary
from services.walkforward import walkforward_summary
from storage.outcome_analytics import compute_brain_multipliers
from storage.outcome_tracker import evaluate_pending_outcomes, init_outcomes_db
from storage.sqlite_store import init_db, save_signal
from utils.config import load_features, load_thresholds


def _load_json(path: str) -> Dict:
    with open(path, "r") as f:
        return json.load(f)


def _save_json(path: str, data: Dict) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


DEFAULT_PEER_GROUPS = {
    "AAPL": ["MSFT", "GOOGL", "AMZN"],
    "MSFT": ["AAPL", "GOOGL", "AMZN"],
    "NVDA": ["AMD", "INTC", "AVGO", "TSM"],
    "META": ["GOOGL", "SNAP", "PINS"],
    "AMZN": ["WMT", "COST", "TGT"],
    "JPM": ["BAC", "C", "WFC", "GS"],
    "XOM": ["CVX", "COP", "OXY"],
}


def _get_day_progress_fraction(current_time: time, open_time: time, close_time: time) -> float:
    open_minutes = open_time.hour * 60 + open_time.minute
    close_minutes = close_time.hour * 60 + close_time.minute
    current_minutes = current_time.hour * 60 + current_time.minute

    if current_minutes <= open_minutes:
        return 0.0
    if current_minutes >= close_minutes:
        return 1.0
    total_minutes = close_minutes - open_minutes
    elapsed_minutes = current_minutes - open_minutes
    return elapsed_minutes / total_minutes


def _annotate_conflicting_brains(signals: List[Signal]) -> None:
    by_ticker = {}
    for s in signals:
        by_ticker.setdefault(s.ticker, []).append(s)

    for _, ticker_signals in by_ticker.items():
        has_up = any(s.direction == "up" for s in ticker_signals)
        has_down = any(s.direction == "down" for s in ticker_signals)
        if has_up and has_down:
            for s in ticker_signals:
                s.metadata["conflicting_brains"] = True


def _signal_analytics_context(signal: Signal, quotes: Dict[str, Dict]) -> Dict[str, Any]:
    quote = quotes.get(signal.ticker, {}) or {}
    return {
        "raw_quote": quote,
        "brain_scores": {signal.brain: signal.confidence},
        "ranking_score": ranking_score(signal),
        "gating_reasons": signal.suppressions or [],
    }


def _build_peer_relative_strength(quotes: Dict[str, Dict], peer_groups: Dict[str, List[str]]) -> Dict[str, float]:
    result: Dict[str, float] = {}
    for ticker, quote in quotes.items():
        move = quote.get("move_1d")
        if not isinstance(move, (int, float)):
            continue
        peers = peer_groups.get(ticker) or []
        peer_moves = []
        for peer in peers:
            pm = (quotes.get(peer) or {}).get("move_1d")
            if isinstance(pm, (int, float)):
                peer_moves.append(pm)
        if not peer_moves:
            continue
        result[ticker] = float(move - (sum(peer_moves) / len(peer_moves)))
    return result


def _parse_hhmm(value: str, default: time) -> time:
    try:
        hh, mm = value.split(":", 1)
        return time(hour=int(hh), minute=int(mm))
    except Exception:
        return default


def _resolve_now_market_tz(now_override: datetime | None, market_tz_name: str) -> datetime:
    if pytz is not None:
        tz = pytz.timezone(market_tz_name)
        if now_override is None:
            return datetime.now(tz)
        if now_override.tzinfo is None:
            return tz.localize(now_override)
        return now_override.astimezone(tz)

    from zoneinfo import ZoneInfo

    tz = ZoneInfo(market_tz_name)
    if now_override is None:
        return datetime.now(tz)
    if now_override.tzinfo is None:
        return now_override.replace(tzinfo=tz)
    return now_override.astimezone(tz)


def run_once(exit_on_market_closed: bool = False, now_et_override: datetime | None = None) -> Dict[str, Any]:
    config = _load_json("config.json")
    anchors = _load_json("anchors.json")
    state = _load_json("state.json")

    thresholds = load_thresholds()
    features = load_features()
    settings = build_runtime_settings(config)
    premium_cfg = thresholds.get("premium", {}) if isinstance(thresholds.get("premium"), dict) else {}
    regime_gating_enabled = bool(features.get("feature_flags", {}).get("enable_regime_gating", True))
    adaptive_weighting_enabled = bool(features.get("feature_flags", {}).get("enable_adaptive_brain_weighting", True))
    sector_rotation_enabled = bool(features.get("feature_flags", {}).get("enable_sector_rotation_brain", True))
    event_risk_enabled = bool(features.get("feature_flags", {}).get("enable_event_risk_gating", True))
    optimizer_enabled = bool(features.get("feature_flags", {}).get("enable_portfolio_optimizer", True))
    pm_briefing_enabled = bool(features.get("feature_flags", {}).get("enable_pm_briefing", True))

    logging.basicConfig(
        filename="bot.log",
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    ensure_state_has_keys(state)
    
    # Upgrade to premium state schema
    state = initialize_premium_state(state)

    if not validate_config(config):
        raise SystemExit("Invalid config.json")

    stocks = config.get("stocks", [])
    market_open = _parse_hhmm(settings.market_open, time(9, 30))
    market_close = _parse_hhmm(settings.market_close, time(16, 0))
    now_market_tz = _resolve_now_market_tz(now_et_override, settings.market_timezone)
    weekday = now_market_tz.weekday()

    if weekday > 4:
        logging.info("market_closed_rule weekend exit")
        if exit_on_market_closed:
            raise SystemExit
        return {"status": "skipped", "reason": "weekend", "last_run": state.get("last_run")}

    intraday_session = market_open <= now_market_tz.time() < market_close
    if not intraday_session and not settings.enable_after_hours_alerts:
        logging.info("market_closed_rule outside RTH and after-hours disabled")
        if exit_on_market_closed:
            raise SystemExit
        return {"status": "skipped", "reason": "outside_market_hours", "last_run": state.get("last_run")}

    today_date = now_market_tz.strftime("%Y-%m-%d")
    if state.get("last_reset_date") != today_date:
        state["last_reset_date"] = today_date
        state["volume_alerts_sent"] = {}

    day_progress = _get_day_progress_fraction(now_market_tz.time(), market_open, market_close) if intraday_session else 1.0

    portfolio = load_portfolio()
    portfolio.setdefault("rules", {})
    portfolio["rules"]["max_position_weight_add"] = settings.max_position_weight_add
    portfolio["rules"]["trim_warning_weight"] = settings.trim_warning_weight

    conn = init_db()
    exec_conn = init_execution_db()
    outcome_lookback = int(premium_cfg.get("outcome_lookback_signals", 250))
    brain_multipliers = compute_brain_multipliers(conn, lookback=outcome_lookback) if adaptive_weighting_enabled else {}

    macro = fetch_macro_snapshot()
    regime_info = classify_regime(macro)
    regime = regime_info.get("regime", "balanced")
    event_calendar = load_event_calendar("config/events.yaml")
    event_horizon_hours = int(premium_cfg.get("event_risk_horizon_hours", 24))
    event_risk = resolve_event_risk(now_market_tz, horizon_hours=event_horizon_hours, calendar=event_calendar)

    quotes: Dict[str, Dict] = {}
    raw_signals: List[Signal] = []

    peer_groups = dict(DEFAULT_PEER_GROUPS)
    portfolio_tickers = [p.get("ticker") for p in portfolio.get("positions", []) if p.get("ticker")]
    for t in portfolio_tickers:
        peer_groups.setdefault(t, [x for x in portfolio_tickers if x != t][:4])

    for ticker in stocks:
        quote = fetch_quote(ticker)
        if quote and quote.get("error"):
            logging.warning("data_error ticker=%s detail=%s", ticker, quote.get("error"))
        if not quote or not validate_quote(quote):
            verification_engine.mark_suppressed(state, "data_error")
            logging.warning("data_error ticker=%s", ticker)
            continue
        quotes[ticker] = quote
        sector_returns = macro.get("sector_returns_20d") or {}
        if isinstance(quote.get("sector"), str):
            quote["sector_return_20d"] = sector_returns.get(quote.get("sector"))

        anchor = anchors.get(ticker)
        if not anchor:
            px = float(quote.get("currentPrice") or 0)
            anchor = {"anchor": px, "next_up": px + config.get("ladder_step", 5), "next_down": px - config.get("ladder_step", 5)}
            anchors[ticker] = anchor

        # Run all market-data driven brains.
        raw_signals.extend(process_ladder_and_volume(ticker, quote, anchor, {
            "ladder_step": config.get("ladder_step", 5),
            "volume_threshold": config.get("volume_threshold", settings.breakout_volume_ratio),
            "strong_breakout_volume_ratio": settings.strong_breakout_volume_ratio,
            "earnings_risk_window_days": settings.earnings_risk_window_days,
        }, state, now_market_tz.isoformat(), day_progress))
        raw_signals.extend(buffett_analyze(ticker, quote, anchor, {"earnings_risk_window_days": settings.earnings_risk_window_days}))
        raw_signals.extend(druck_analyze(ticker, quote, anchor, {"strong_breakout_volume_ratio": settings.strong_breakout_volume_ratio}))
        raw_signals.extend(lynch_analyze(ticker, quote, anchor, {}))
        raw_signals.extend(analyst_analyze(ticker, quote, anchor, {}))
        raw_signals.extend(soros_analyze(ticker, quote, anchor, {}))
        if sector_rotation_enabled:
            raw_signals.extend(sector_rotation_analyze(ticker, quote, anchor, {
                "sector_leader_return_20d": float(premium_cfg.get("sector_leader_return_20d", 0.03)),
                "sector_laggard_return_20d": float(premium_cfg.get("sector_laggard_return_20d", -0.03)),
            }))

    prices = {t: q.get("currentPrice", 0.0) for t, q in quotes.items()}
    raw_signals.extend(dalio_analyze(portfolio, prices))
    peer_rs = _build_peer_relative_strength(quotes, peer_groups)

    # Common metadata used by verifier / formatter.
    for signal in raw_signals:
        quote = quotes.get(signal.ticker, {})
        signal.metadata.setdefault("quote_timestamp", str(quote.get("timestamp") or signal.timestamp))
        signal.metadata.setdefault("earnings_days", quote.get("earnings_days"))
        signal.metadata.setdefault("earnings_risk_window_days", settings.earnings_risk_window_days)
        signal.metadata.setdefault("trim_warning_weight", settings.trim_warning_weight)
        signal.metadata.setdefault("sector", quote.get("sector"))
        signal.metadata.setdefault("iv_rank", quote.get("iv_rank"))
        signal.metadata.setdefault("event_risk_active", event_risk.active)
        signal.metadata.setdefault("event_risk_horizon_hours", event_risk.horizon_hours)
        signal.metadata.setdefault("event_risk_events", event_risk.events[:5])
        signal.metadata.setdefault("decision_timestamp", datetime.now(timezone.utc).isoformat())
        # PM accountability fields.
        signal.metadata.setdefault("thesis_id", signal.cooldown_key)
        if isinstance(signal.price, (int, float)) and isinstance(signal.change_pct, (int, float)):
            shock = max(0.015, min(0.08, abs(signal.change_pct) * 1.5))
            if signal.direction == "up":
                signal.metadata.setdefault("invalidation_price", round(float(signal.price) * (1.0 - shock), 4))
            elif signal.direction == "down":
                signal.metadata.setdefault("invalidation_price", round(float(signal.price) * (1.0 + shock), 4))
        if signal.ticker in peer_rs:
            signal.metadata.setdefault("peer_relative_strength", peer_rs[signal.ticker])

    # Apply premium decision-grade signal completion
    for signal in raw_signals:
        try:
            complete_signal_for_premium_quality(signal, quotes)
        except Exception as exc:
            logging.warning("signal_completion_error ticker=%s brain=%s error=%s", signal.ticker, signal.brain, exc)

    _annotate_conflicting_brains(raw_signals)

    decided_signals = decision_engine.decide(raw_signals, portfolio, prices)
    decided_signals = apply_context_overlays(
        decided_signals,
        macro=macro,
        regime=regime,
        brain_multipliers=brain_multipliers,
    )

    for signal in decided_signals:
        if regime_gating_enabled and not regime_allows_signal(signal.signal_type, regime):
            signal.metadata["regime_blocked"] = True
        if event_risk_enabled and event_risk.active and signal.signal_type in {"breakout", "trend_continuation", "buy_the_dip", "dip", "quality_dip", "growth_value"}:
            signal.metadata["event_risk_blocked"] = True
        signal.metadata.setdefault("regime_drivers", regime_info.get("drivers", []))
        signal.metadata.setdefault("yield_curve_10y_3m", macro.get("yield_curve_10y_3m"))
        signal.metadata.setdefault("credit_risk_proxy_20d", macro.get("credit_risk_proxy_20d"))

    router = AlertRouter(state=state, settings=settings, high_conviction_score=thresholds.get("confidence", {}).get("high_conviction_score", 80))
    approved_signals, suppressed_counts = router.filter_signals(decided_signals)

    optimizer_plan = {
        "targets": {},
        "sector_targets": {},
        "gross_target": 0.0,
        "notes": ["disabled"],
    }
    if optimizer_enabled:
        optimizer_plan = optimize_targets(
            approved_signals,
            max_single_name_weight=float(premium_cfg.get("max_single_name_weight", 0.12)),
            max_sector_weight=float(premium_cfg.get("max_sector_weight", 0.35)),
            gross_risk_budget=float(premium_cfg.get("gross_risk_budget", 0.75)),
        )

    feature_digest = features.get("digest", {}).get("enabled", True)
    max_per_ticker_per_hour = thresholds.get("alerts", {}).get("max_per_ticker_per_hour", 2)
    max_per_run = thresholds.get("alerts", {}).get("max_per_run", 5)

    sent_signals: List[Signal] = []
    batched_messages: List[Signal] = []
    webhook_sent_count = 0
    persist_failed_count = 0

    for signal in approved_signals:
        if not throttler.should_send_alert(state, signal.ticker, max_per_ticker_per_hour, max_per_run):
            verification_engine.mark_suppressed(state, "duplicate_state")
            suppressed_counts["duplicate_state"] = suppressed_counts.get("duplicate_state", 0) + 1
            logging.info("suppressed reason=duplicate_state ticker=%s brain=%s", signal.ticker, signal.brain)
            continue

        if feature_digest:
            batched_messages.append(signal)
        else:
            decision_time = datetime.now(timezone.utc)
            ok = send_discord_message(settings.discord_webhook_url, format_signal(signal))
            if ok:
                webhook_sent_count += 1
                alert_id = save_signal(conn, signal, analytics_context=_signal_analytics_context(signal, quotes))
                if not alert_id:
                    persist_failed_count += 1
                    suppressed_counts["persist_failed"] = suppressed_counts.get("persist_failed", 0) + 1
                    logging.error("persist_failed ticker=%s brain=%s", signal.ticker, signal.brain)
                    continue
                dispatch_time = datetime.now(timezone.utc)
                record_execution_metric(
                    exec_conn,
                    alert_id=alert_id,
                    ticker=signal.ticker,
                    decision_time=decision_time,
                    dispatch_time=dispatch_time,
                    decision_price=signal.price,
                    dispatch_price=(quotes.get(signal.ticker) or {}).get("currentPrice"),
                )
                verification_engine.mark_sent(signal, state)
                throttler.record_alert(state, signal.ticker)
                sent_signals.append(signal)

    if feature_digest and batched_messages:
        max_signals = thresholds.get("digest", {}).get("max_signals", 8)
        digest_signals = batched_messages[:max_signals]
        digest_cfg = features.get("digest", {})
        digest_mode = digest_cfg.get("display_mode")
        prefer_embed = digest_cfg.get("use_embed")
        use_colored_embed = digest_cfg.get("use_colored_embed_scheme")
        show_signal_agreement = digest_cfg.get("show_signal_agreement")
        digest_payload = format_digest_payload(
            digest_signals,
            title="📊 Market Signal Digest",
            mode=digest_mode,
            prefer_embed=prefer_embed if isinstance(prefer_embed, bool) else None,
            use_colored_embed=use_colored_embed if isinstance(use_colored_embed, bool) else None,
            show_signal_agreement=show_signal_agreement if isinstance(show_signal_agreement, bool) else None,
        )
        discord_payload = {"content": digest_payload.get("content")}
        embeds = digest_payload.get("embeds")
        if isinstance(embeds, list) and embeds:
            discord_payload["embeds"] = embeds
        digest_ok = send_discord_payload(
            settings.discord_webhook_url,
            discord_payload,
        )
        if not digest_ok:
            fallback_content = digest_payload.get("fallback_content")
            if isinstance(fallback_content, str) and fallback_content:
                digest_ok = send_discord_message(settings.discord_webhook_url, fallback_content)
        if digest_ok:
            webhook_sent_count += len(digest_signals)
        for sig in digest_signals:
            decision_time = datetime.now(timezone.utc)
            alert_id = save_signal(conn, sig, analytics_context=_signal_analytics_context(sig, quotes))
            if not alert_id:
                persist_failed_count += 1
                suppressed_counts["persist_failed"] = suppressed_counts.get("persist_failed", 0) + 1
                logging.error("persist_failed ticker=%s brain=%s", sig.ticker, sig.brain)
                continue
            dispatch_time = datetime.now(timezone.utc)
            record_execution_metric(
                exec_conn,
                alert_id=alert_id,
                ticker=sig.ticker,
                decision_time=decision_time,
                dispatch_time=dispatch_time,
                decision_price=sig.price,
                dispatch_price=(quotes.get(sig.ticker) or {}).get("currentPrice"),
            )
            verification_engine.mark_sent(sig, state)
            throttler.record_alert(state, sig.ticker)
            sent_signals.append(sig)

    if sent_signals:
        top = rank_signals(sent_signals, top_n=3)
        lines = [f"Daily Top Signals ({len(top)}):"]
        for s in top:
            lines.append(f"- {s.ticker} | {s.signal_type} | {s.confidence} | {s.brain} | {s.action_bias}")
        send_discord_message(settings.discord_webhook_url, "\n".join(lines))

    if pm_briefing_enabled:
        pm_lines = ["**PM Briefing**"]

        # Cycle quality score (how many raw signals survived to dispatch)
        total_raw = len(raw_signals)
        total_approved = len(approved_signals)
        total_sent = len(sent_signals)
        if total_raw > 0:
            quality_pct = int(round(total_sent / total_raw * 100))
            pm_lines.append(f"Cycle Quality: {total_sent}/{total_raw} signals sent ({quality_pct}%)")

        # Regime and macro context
        regime_label = regime.replace("_", " ").title()
        drivers_str = ", ".join(regime_info.get("drivers", [])) or "none"
        pm_lines.append(f"Regime: {regime_label} (drivers: {drivers_str})")

        # Event risk
        if event_risk.active:
            event_names = ", ".join(e.get("name", "unknown") for e in (event_risk.events or [])[:3])
            pm_lines.append(f"Event Risk: ACTIVE — {event_names or 'see calendar'}")

        # Top optimizer allocation targets
        top_targets = list((optimizer_plan.get("targets") or {}).items())[:3]
        if top_targets:
            pm_lines.append("Top Targets:")
            for ticker, weight in top_targets:
                pm_lines.append(f"  {ticker}: {weight:.1%}")

        # Top suppression reasons this cycle
        if suppressed_counts:
            top_suppressions = sorted(suppressed_counts.items(), key=lambda kv: kv[1], reverse=True)[:3]
            sup_str = ", ".join(f"{r}×{n}" for r, n in top_suppressions)
            pm_lines.append(f"Top Suppressions: {sup_str}")

        send_discord_message(settings.discord_webhook_url, "\n".join(pm_lines))

    exec_summary = execution_summary(exec_conn)
    attribution = attribution_summary(conn)
    walkforward = walkforward_summary(conn)

    health = build_health(state, settings)
    summary = build_daily_summary(sent_signals, suppressed_counts, health)
    state["cycle_metrics"] = {
        "sent_count": len(sent_signals),
        "raw_signal_count": len(raw_signals),
        "approved_count": len(approved_signals),
        "webhook_sent_count": webhook_sent_count,
        "persist_failed_count": persist_failed_count,
        "suppressed_counts": suppressed_counts,
        "signal_counts_by_brain": summary.get("signal_counts_by_brain", {}),
        "market_regime": regime,
        "regime_drivers": regime_info.get("drivers", []),
        "event_risk_active": event_risk.active,
        "event_risk_events": event_risk.events[:5],
        "optimizer_plan": optimizer_plan,
        "execution_summary": exec_summary,
        "attribution": attribution,
        "walkforward": walkforward,
    }
    state["last_run"] = datetime.now(timezone.utc).isoformat()

    _save_json("anchors.json", anchors)
    _save_json("state.json", sanitize_state_for_json(state))

    if features.get("feature_flags", {}).get("enable_outcome_tracking", True):
        conn_out = init_outcomes_db()
        evaluate_pending_outcomes(conn_out)

    logging.info(
        "cycle_complete raw=%s approved=%s sent=%s webhook_sent=%s persist_failed=%s suppressions=%s",
        len(raw_signals),
        len(approved_signals),
        len(sent_signals),
        webhook_sent_count,
        persist_failed_count,
        suppressed_counts,
    )
    record_cycle_metrics(raw_count=len(raw_signals), approved_count=len(approved_signals), sent_count=len(sent_signals))
    record_suppressions(suppressed_counts)

    return {
        "status": "ok",
        "raw_signal_count": len(raw_signals),
        "approved_count": len(approved_signals),
        "sent_count": len(sent_signals),
        "webhook_sent_count": webhook_sent_count,
        "persist_failed_count": persist_failed_count,
        "suppressed_counts": suppressed_counts,
        "last_run": state.get("last_run"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Stock Alert Bot runner")
    parser.add_argument("--scheduler", action="store_true", help="Run internal scheduler loop")
    parser.add_argument(
        "--self-check-webhook",
        action="store_true",
        help="Validate and live-check DISCORD_WEBHOOK_URL, then exit",
    )
    args = parser.parse_args()

    if args.self_check_webhook:
        config = _load_json("config.json")
        settings = build_runtime_settings(config)
        ok, message = self_check_discord_webhook(settings.discord_webhook_url)
        print(message)
        raise SystemExit(0 if ok else 1)

    if args.scheduler:
        from scheduler import run_internal_scheduler

        run_internal_scheduler(lambda: run_once(exit_on_market_closed=False))
        return

    run_once(exit_on_market_closed=True)


if __name__ == "__main__":
    main()
