"""On-demand ticker research using the existing brain stack."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from brains.analyst_brain import analyze as analyst_analyze
from brains.buffett_brain import analyze as buffett_analyze
from brains.dalio_brain import analyze as dalio_analyze
from brains.druckenmiller_brain import analyze as druck_analyze
from brains.lynch_brain import analyze as lynch_analyze
from brains.quant_brain import process_ladder_and_volume
from brains.sector_rotation_brain import analyze as sector_rotation_analyze
from brains.soros_brain import analyze as soros_analyze
from data.event_calendar import load_event_calendar, resolve_event_risk
from data.macro_data import fetch_macro_snapshot
from data.market_data import fetch_quote
from data.portfolio_data import load_portfolio
from engine import decision_engine, verification_engine
from engine.context_overlay import apply_context_overlays
from engine.ranking_engine import rank_signals
from engine.regime_engine import classify_regime, regime_allows_signal
from engine.signal_models import Signal
from utils.config import load_thresholds, load_json_file


def _annotate_conflicting_brains(signals: List[Signal]) -> None:
    by_ticker: Dict[str, List[Signal]] = {}
    for s in signals:
        by_ticker.setdefault(s.ticker, []).append(s)
    for ticker_signals in by_ticker.values():
        has_up = any(s.direction == "up" for s in ticker_signals)
        has_down = any(s.direction == "down" for s in ticker_signals)
        if has_up and has_down:
            for s in ticker_signals:
                s.metadata["conflicting_brains"] = True


def _research_header(ticker: str, quote: Dict[str, Any], regime: str, regime_drivers: List[str]) -> List[str]:
    price = quote.get("currentPrice")
    move = quote.get("move_1d")
    vol = quote.get("volume_ratio")
    earnings_days = quote.get("earnings_days")
    iv_rank = quote.get("iv_rank")

    lines = [f"Research: {ticker}"]
    if isinstance(price, (int, float)):
        lines.append(f"- Price: ${float(price):,.2f}")
    if isinstance(move, (int, float)):
        lines.append(f"- Daily move: {float(move):+.2%}")
    if isinstance(vol, (int, float)):
        lines.append(f"- Volume ratio: {float(vol):.2f}x")
    if isinstance(earnings_days, (int, float)):
        lines.append(f"- Earnings in: {int(earnings_days)} day(s)")
    if isinstance(iv_rank, (int, float)):
        lines.append(f"- IV rank: {float(iv_rank):.0%}")
    lines.append(f"- Market regime: {regime}")
    if regime_drivers:
        lines.append(f"- Regime drivers: {', '.join(regime_drivers[:4])}")
    return lines


def _signal_line(signal: Signal, approved: bool, reason: str | None = None) -> str:
    status = "approved" if approved else f"suppressed ({reason or 'unknown'})"
    return (
        f"- {signal.brain}: {signal.signal_type} | conf {signal.confidence} | "
        f"{signal.action_bias} | {status}"
    )


def _brain_consensus(signals: List[Signal]) -> Tuple[int, int, int]:
    bullish = sum(1 for s in signals if s.direction == "up")
    bearish = sum(1 for s in signals if s.direction == "down")
    risk = sum(1 for s in signals if s.signal_type in {"risk", "concentration_risk", "macro_divergence"})
    return bullish, bearish, risk


def build_ticker_research(ticker: str) -> str:
    symbol = (ticker or "").strip().upper()
    if not symbol:
        return "Please provide a ticker symbol, e.g. `research NVDA`."

    quote = fetch_quote(symbol)
    if not quote or quote.get("error"):
        detail = quote.get("error") if isinstance(quote, dict) else "no data"
        return f"Could not fetch data for {symbol}: {detail}"

    config = load_json_file("config.json")
    thresholds = load_thresholds()
    premium_cfg = thresholds.get("premium", {}) if isinstance(thresholds.get("premium"), dict) else {}

    macro = fetch_macro_snapshot()
    regime_info = classify_regime(macro)
    regime = regime_info.get("regime", "balanced")
    sector_returns = macro.get("sector_returns_20d") or {}
    if isinstance(quote.get("sector"), str):
        quote["sector_return_20d"] = sector_returns.get(quote.get("sector"))

    ladder_step = int(config.get("ladder_step", 5)) if isinstance(config, dict) else 5
    px = float(quote.get("currentPrice") or 0.0)
    anchor = {"anchor": px, "next_up": px + ladder_step, "next_down": px - ladder_step}
    now_text = datetime.now(timezone.utc).isoformat()

    raw_signals: List[Signal] = []
    raw_signals.extend(
        process_ladder_and_volume(
            symbol,
            quote,
            anchor,
            {
                "ladder_step": ladder_step,
                "volume_threshold": float((thresholds.get("market", {}) or {}).get("breakout_volume_ratio", 1.5)),
                "strong_breakout_volume_ratio": float((thresholds.get("market", {}) or {}).get("strong_breakout_volume_ratio", 2.0)),
                "earnings_risk_window_days": int((thresholds.get("runtime", {}) or {}).get("earnings_risk_window_days", 7)),
            },
            {"volume_alerts_sent": {}},
            now_text,
            0.5,
        )
    )
    raw_signals.extend(buffett_analyze(symbol, quote, anchor, {"earnings_risk_window_days": int((thresholds.get("runtime", {}) or {}).get("earnings_risk_window_days", 7))}))
    raw_signals.extend(druck_analyze(symbol, quote, anchor, {"strong_breakout_volume_ratio": float((thresholds.get("market", {}) or {}).get("strong_breakout_volume_ratio", 2.0))}))
    raw_signals.extend(lynch_analyze(symbol, quote, anchor, {}))
    raw_signals.extend(analyst_analyze(symbol, quote, anchor, {"earnings_risk_window_days": int((thresholds.get("runtime", {}) or {}).get("earnings_risk_window_days", 7))}))
    raw_signals.extend(soros_analyze(symbol, quote, anchor, {}))
    raw_signals.extend(
        sector_rotation_analyze(
            symbol,
            quote,
            anchor,
            {
                "sector_leader_return_20d": float(premium_cfg.get("sector_leader_return_20d", 0.03)),
                "sector_laggard_return_20d": float(premium_cfg.get("sector_laggard_return_20d", -0.03)),
            },
        )
    )

    portfolio = load_portfolio()
    prices = {symbol: float(quote.get("currentPrice") or 0.0)}
    raw_signals.extend(dalio_analyze(portfolio, prices))

    for s in raw_signals:
        s.metadata.setdefault("quote_timestamp", str(quote.get("timestamp") or s.timestamp))
        s.metadata.setdefault("earnings_days", quote.get("earnings_days"))
        s.metadata.setdefault("earnings_risk_window_days", int((thresholds.get("runtime", {}) or {}).get("earnings_risk_window_days", 7)))
        s.metadata.setdefault("trim_warning_weight", float((thresholds.get("portfolio", {}) or {}).get("trim_warning_weight", 0.2)))
        s.metadata.setdefault("sector", quote.get("sector"))
        s.metadata.setdefault("iv_rank", quote.get("iv_rank"))

    _annotate_conflicting_brains(raw_signals)

    decided = decision_engine.decide(raw_signals, portfolio, prices)
    decided = apply_context_overlays(decided, macro=macro, regime=regime, brain_multipliers={})

    event_calendar = load_event_calendar("config/events.yaml")
    event_risk = resolve_event_risk(datetime.now(timezone.utc), horizon_hours=int(premium_cfg.get("event_risk_horizon_hours", 24)), calendar=event_calendar)

    for s in decided:
        if not regime_allows_signal(s.signal_type, regime):
            s.metadata["regime_blocked"] = True
        if event_risk.active and s.signal_type in {"breakout", "trend_continuation", "buy_the_dip", "dip", "quality_dip", "growth_value"}:
            s.metadata["event_risk_blocked"] = True

    approved: List[Signal] = []
    suppressed: List[Tuple[Signal, str]] = []
    for s in decided:
        ok, reason = verification_engine.verify_signal(
            s,
            state={},
            min_threshold=int((thresholds.get("confidence", {}) or {}).get("min_send_score", 50)),
            cooldown_seconds=0,
            high_conviction_score=int((thresholds.get("confidence", {}) or {}).get("high_conviction_score", 80)),
            min_confirmations_normal=int((thresholds.get("runtime", {}) or {}).get("min_confirmations_normal", 2)),
            min_confirmations_high=int((thresholds.get("runtime", {}) or {}).get("min_confirmations_high", 3)),
            stale_quote_max_age_seconds=int((thresholds.get("market", {}) or {}).get("stale_quote_max_age_seconds", 300)),
        )
        if ok:
            approved.append(s)
        else:
            suppressed.append((s, reason))

    ranked = rank_signals(decided, top_n=5)
    bulls, bears, risks = _brain_consensus(decided)

    lines = _research_header(symbol, quote, regime, regime_info.get("drivers", []))
    lines.append(f"- Brain consensus: bullish={bulls}, bearish={bears}, risk_flags={risks}")
    if event_risk.active:
        names = ", ".join(e.get("name", "event") for e in event_risk.events[:3])
        lines.append(f"- Event risk: active (next {event_risk.horizon_hours}h): {names}")

    if approved:
        lines.append("")
        lines.append("Top approved insights:")
        for s in rank_signals(approved, top_n=3):
            lines.append(_signal_line(s, approved=True))
            tgt = (s.metadata or {}).get("target_weight")
            inv = (s.metadata or {}).get("invalidation_price")
            if isinstance(tgt, (int, float)):
                lines.append(f"  target_weight: {float(tgt):.1%}")
            if isinstance(inv, (int, float)):
                lines.append(f"  invalidation_price: ${float(inv):,.2f}")
    else:
        lines.append("")
        lines.append("No currently approved signals for this ticker under active risk controls.")

    if ranked:
        lines.append("")
        lines.append("Brain-by-brain read:")
        approved_set = {(s.brain, s.signal_type, s.confidence) for s in approved}
        sup_map = {(s.brain, s.signal_type, s.confidence): reason for s, reason in suppressed}
        for s in ranked[:5]:
            key = (s.brain, s.signal_type, s.confidence)
            is_ok = key in approved_set
            lines.append(_signal_line(s, approved=is_ok, reason=sup_map.get(key)))

    return "\n".join(lines)
