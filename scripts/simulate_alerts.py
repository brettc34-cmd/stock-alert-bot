"""Simulate alerts over historical data for balance and quality validation."""

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Any, List
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yfinance as yf
import pandas as pd

from brains.quant_brain import process_ladder_and_volume
from brains.buffett_brain import analyze as buffett_analyze
from brains.druckenmiller_brain import analyze as druck_analyze
from brains.lynch_brain import analyze as lynch_analyze
from brains.analyst_brain import analyze as analyst_analyze
from brains.soros_brain import analyze as soros_analyze
from engine import verification_engine
from services.alert_router import AlertRouter


@dataclass
class SimSettings:
    alert_min_confidence: int = 50
    alert_cooldown_minutes: int = 0
    min_confirmations_normal: int = 2
    min_confirmations_high: int = 3
    stale_quote_max_age_seconds: int = 365 * 24 * 3600


def load_history(ticker: str, period: str = "3mo", interval: str = "1d") -> pd.DataFrame:
    df = yf.download(ticker, period=period, interval=interval, progress=False)
    if df.empty:
        raise ValueError(f"No data for {ticker}")
    return df


def prepare_info(df: pd.DataFrame, i: int, ticker: str) -> Dict[str, Any]:
    row = df.iloc[i]
    closes = df[("Close", ticker)].iloc[: i + 1]
    vols = df[("Volume", ticker)].iloc[: i + 1]
    current_price = float(row[("Close", ticker)])
    ma20 = float(closes.tail(20).mean()) if len(closes) >= 20 else current_price
    ma50 = float(closes.tail(50).mean()) if len(closes) >= 50 else ma20
    high20 = float(closes.tail(20).max()) if len(closes) >= 20 else current_price
    high50 = float(closes.tail(50).max()) if len(closes) >= 50 else high20
    ma20_prev = float(closes.iloc[-21:-1].mean()) if len(closes) >= 21 else ma20
    move_1d = ((current_price / float(closes.iloc[-2])) - 1.0) if len(closes) >= 2 and float(closes.iloc[-2]) else 0.0
    avg20_vol = float(vols.tail(20).mean()) if len(vols) >= 20 else float(row[("Volume", ticker)])
    volume = float(row[("Volume", ticker)])
    volume_ratio = (volume / avg20_vol) if avg20_vol else None
    recent_high = float(closes.max()) if len(closes) else current_price

    return {
        "ticker": ticker,
        "currentPrice": current_price,
        "volume": volume,
        "averageVolume": avg20_vol,
        "avg20_volume": avg20_vol,
        "fiftyDayAverage": ma50,
        "twoHundredDayAverage": ma50,
        "ma20": ma20,
        "ma50": ma50,
        "high20": high20,
        "high50": high50,
        "ma20_slope": ma20 - ma20_prev,
        # RS proxy: MA20 vs MA50 momentum delta. Not a true benchmark comparison
        # but exercises the full signal pipeline (Druckenmiller/Soros) in simulation.
        "relative_strength_vs_benchmark": round((ma20 - ma50) / ma50, 4) if ma50 > 0 else None,
        "move_1d": move_1d,
        "move_zscore": abs(move_1d) / 0.02 if move_1d is not None else 0.0,
        "recent_high": recent_high,
        "earnings_days": 30,
        "volume_ratio": volume_ratio,
        "timestamp": datetime.now(timezone.utc),
    }


def apply_diversity_rebalance(signals: List[Any], approved_counts: Counter, soft_cap: float = 0.60) -> None:
    """Soft-cap dominant brain share by nudging confidence intra-simulation.

    This only affects simulation diagnostics and does not modify production routing.
    """
    total_approved = sum(approved_counts.values())
    if total_approved < 4:
        return
    dominant_brain, dominant_count = approved_counts.most_common(1)[0]
    dominant_share = dominant_count / total_approved if total_approved else 0.0
    if dominant_share <= soft_cap:
        return

    for s in signals:
        s.metadata.setdefault("diversity_adjustment", 0)
        if s.brain == dominant_brain:
            s.confidence = max(0, s.confidence - 12)
            s.metadata["diversity_adjustment"] -= 12
        else:
            s.confidence = min(100, s.confidence + 10)
            s.metadata["diversity_adjustment"] += 10


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate premium alerts on historical data")
    parser.add_argument("--ticker", required=True, help="Stock ticker")
    parser.add_argument("--days", type=int, default=90, help="Days of history")
    parser.add_argument("--output", default="results.json", help="Output JSON file")
    args = parser.parse_args()

    print(f"Simulating premium alerts for {args.ticker} over {args.days} days...")
    df = load_history(args.ticker, period=f"{args.days}d")

    state: Dict[str, Any] = {"sent_signals": {}, "cooldowns": {}, "suppression_counts": {}, "volume_alerts_sent": {}}
    router = AlertRouter(state=state, settings=SimSettings())

    all_signals = []
    all_approved = []
    suppression_counts = Counter()
    approved_counts = Counter()
    suppression_by_brain = Counter()
    suppression_reason_by_brain: Dict[str, Counter] = defaultdict(Counter)

    for i in range(len(df)):
        info = prepare_info(df, i, args.ticker)
        anchor_price = info["currentPrice"]
        anchor_entry = {
            "anchor": anchor_price,
            "next_up": anchor_price + 5,
            "next_down": anchor_price - 5,
        }

        signals = []
        signals.extend(process_ladder_and_volume(args.ticker, info, anchor_entry, {
            "ladder_step": 5,
            "volume_threshold": 1.5,
            "strong_breakout_volume_ratio": 2.0,
            "earnings_risk_window_days": 7,
        }, state, datetime.now(timezone.utc).isoformat(), 0.5))
        signals.extend(buffett_analyze(args.ticker, info, anchor_entry, {"earnings_risk_window_days": 7}))
        signals.extend(druck_analyze(args.ticker, info, anchor_entry, {"strong_breakout_volume_ratio": 2.0}))
        signals.extend(lynch_analyze(args.ticker, info, anchor_entry, {}))
        signals.extend(analyst_analyze(args.ticker, info, anchor_entry, {}))
        signals.extend(soros_analyze(args.ticker, info, anchor_entry, {}))

        for s in signals:
            s.metadata.setdefault("quote_timestamp", str(info["timestamp"]))
            s.metadata.setdefault("earnings_days", info["earnings_days"])
            s.metadata.setdefault("trim_warning_weight", 0.2)
            s.metadata.setdefault("move_zscore", info.get("move_zscore"))

        apply_diversity_rebalance(signals, approved_counts, soft_cap=0.60)

        approved, suppressed = router.filter_signals(signals)
        approved_ids = {id(s) for s in approved}
        for s in signals:
            if id(s) in approved_ids:
                continue
            if s.suppressions:
                reason = s.suppressions[-1]
                suppression_by_brain[s.brain] += 1
                suppression_reason_by_brain[s.brain][reason] += 1
        for sig in approved:
            verification_engine.mark_sent(sig, state)

        all_signals.extend(signals)
        all_approved.extend(approved)
        approved_counts.update(s.brain for s in approved)
        suppression_counts.update(suppressed)

    by_brain = Counter(s.brain for s in all_approved)
    by_type = Counter(s.signal_type for s in all_approved)
    confidence_by_brain: Dict[str, List[float]] = defaultdict(list)
    for s in all_approved:
        confidence_by_brain[s.brain].append(float(s.confidence))
    avg_confidence_by_brain = {
        brain: round(sum(vals) / len(vals), 2)
        for brain, vals in confidence_by_brain.items()
        if vals
    }

    approved_total = len(all_approved)
    approved_by_brain_pct = {
        brain: round((count / approved_total) * 100, 2)
        for brain, count in by_brain.items()
    } if approved_total else {}
    approved_by_type_pct = {
        sig_type: round((count / approved_total) * 100, 2)
        for sig_type, count in by_type.items()
    } if approved_total else {}
    top_suppression_reason_by_brain = {
        brain: counts.most_common(1)[0][0]
        for brain, counts in suppression_reason_by_brain.items()
        if counts
    }

    # Per-brain confirmations frequency — helps diagnose why one brain dominates.
    brain_confirmations: Dict[str, Counter] = defaultdict(Counter)
    for s in all_approved:
        for c in s.confirmations:
            brain_confirmations[s.brain][c] += 1

    dominant_brain = by_brain.most_common(1)[0][0] if by_brain else None
    dominant_share = (by_brain.most_common(1)[0][1] / len(all_approved)) if by_brain and all_approved else 0.0
    dominant_flag = dominant_share > 0.60

    report = {
        "ticker": args.ticker,
        "days": args.days,
        "raw_signal_count": len(all_signals),
        "approved_signal_count": len(all_approved),
        "signal_counts_by_brain": dict(by_brain),
        "approved_by_brain_percent": approved_by_brain_pct,
        "signal_counts_by_type": dict(by_type),
        "approved_by_type_percent": approved_by_type_pct,
        "suppression_counts_by_reason": dict(suppression_counts),
        "suppression_by_brain": dict(suppression_by_brain),
        "avg_confidence_by_brain": avg_confidence_by_brain,
        "top_suppression_reason_by_brain": top_suppression_reason_by_brain,
        "dominant_signal_source": dominant_brain,
        "dominant_signal_share": round(dominant_share, 4),
        "dominance_warning": dominant_flag,
    }

    print("=== SIMULATION SUMMARY ===")
    print(f"Raw signals: {report['raw_signal_count']}")
    print(f"Approved signals: {report['approved_signal_count']}")
    print(f"By brain: {report['signal_counts_by_brain']}")
    print(f"By brain %: {report['approved_by_brain_percent']}")
    print(f"By type: {report['signal_counts_by_type']}")
    print(f"By type %: {report['approved_by_type_percent']}")
    print(f"Suppressions: {report['suppression_counts_by_reason']}")
    print(f"Suppression by brain: {report['suppression_by_brain']}")
    print(f"Avg confidence by brain: {report['avg_confidence_by_brain']}")
    print(f"Top suppression reason by brain: {report['top_suppression_reason_by_brain']}")
    if dominant_flag:
        print(f"Warning: dominant signal source {dominant_brain} at {dominant_share:.1%}")
        top_confs = brain_confirmations[dominant_brain].most_common(5)
        print(f"  Top confirmations driving {dominant_brain}:")
        for conf, cnt in top_confs:
            print(f"    {conf}: {cnt}")
    print("Brain confirmation breakdown:")
    for brain, counts in brain_confirmations.items():
        print(f"  {brain}: {dict(counts.most_common(3))}")

    with open(args.output, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Results saved to {args.output}")


if __name__ == "__main__":
    main()
