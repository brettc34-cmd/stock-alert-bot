"""Discord digest formatter with grouped opportunities, agreement clarity, and dual rendering modes."""

from __future__ import annotations

import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from engine.signal_models import Signal


MAX_DISCORD_CONTENT_CHARS = 1900


SIGNAL_LABELS: Dict[str, str] = {
    "buy_the_dip": "Buy Pullback",
    "dip": "Pullback / Ladder Entry",
    "breakout": "Momentum Breakout",
    "breakdown": "Breakdown Risk",
    "mean_reversion": "Mean Reversion",
    "trend": "Trend Continuation",
    "trend_continuation": "Trend Continuation",
    "macro_divergence": "Macro Divergence",
    "risk": "Risk Alert",
    "concentration_risk": "Concentration Risk",
    "quality_dip": "Quality Pullback",
}


SIGNAL_THEME_LABELS: Dict[str, str] = {
    "buy_the_dip": "Value-supported pullback",
    "dip": "Price reached a staged-entry pullback level.",
    "breakout": "Volume-confirmed breakout",
    "breakdown": "Support level break",
    "trend": "Moving-average trend alignment",
    "trend_continuation": "Moving-average trend alignment",
    "mean_reversion": "Reversion setup",
    "macro_divergence": "Broader market relationships are not fully confirming.",
    "risk": "Risk pressure building",
    "concentration_risk": "Concentration risk pressure",
}


STRATEGY_FRIENDLY_LABELS: Dict[str, str] = {
    "buffett": "Value Accumulation",
    "druckenmiller": "Momentum Trend",
    "quant-ladder": "Systematic Scaling",
    "quant": "Systematic Momentum",
    "soros": "Market Conditions",
    "lynch": "Growth at Value",
    "analyst": "Street Revision",
    "dalio": "Macro Allocation",
}


SIGNAL_IMPORTANCE_BONUS: Dict[str, int] = {
    "breakout": 80,
    "breakdown": 80,
    "trend_continuation": 60,
    "trend": 60,
    "buy_the_dip": 45,
    "dip": 45,
    "quality_dip": 45,
    "mean_reversion": 35,
    "macro_divergence": 50,
    "risk": 50,
    "concentration_risk": 55,
}


BIAS_STYLE: Dict[str, Tuple[str, int, str]] = {
    "bullish": ("🟢", 0x1F9D55, "Bullish"),
    "mixed": ("🟡", 0xD4A017, "Mixed / Needs Confirmation"),
    "bearish": ("🔴", 0xC0392B, "Bearish Risk"),
}


@dataclass
class ConfidenceView:
    stars: int
    label: str


@dataclass
class BiasView:
    key: str
    icon: str
    embed_color: int
    label: str


@dataclass
class AgreementView:
    label: str
    aligned_signals: int
    active_signals: int


@dataclass
class TickerOpportunity:
    ticker: str
    signals: List[Signal]
    signal_labels: List[str]
    strategy_labels: List[str]
    confidence_score: int
    confidence_view: ConfidenceView
    bias: str
    bias_view: BiasView
    agreement: AgreementView
    key_signals: List[str]
    why_it_matters: str
    key_levels: Optional[str]
    sector: Optional[str]
    rank_score: int


def normalize_signal_label(signal_type: str) -> str:
    key = (signal_type or "").strip().lower()
    if key in SIGNAL_LABELS:
        return SIGNAL_LABELS[key]
    return key.replace("_", " ").title() if key else "Unknown"


def normalize_strategy_label(brain: str, mode: str = "pro") -> str:
    mode = (mode or "pro").lower()
    raw = (brain or "Unknown").replace("_", " ").strip()
    key = raw.lower()
    friendly = STRATEGY_FRIENDLY_LABELS.get(key)
    if not friendly:
        return raw.title()
    if mode == "novice":
        return friendly
    return f"{raw.title()} ({friendly})"


def _confidence_view(score: int) -> ConfidenceView:
    if score >= 85:
        return ConfidenceView(stars=5, label="Elite")
    if score >= 70:
        return ConfidenceView(stars=4, label="Strong")
    if score >= 55:
        return ConfidenceView(stars=3, label="Moderate")
    if score >= 40:
        return ConfidenceView(stars=2, label="Weak")
    return ConfidenceView(stars=1, label="Very Weak")


def _is_bearish(signal_type: str, direction: str) -> bool:
    st = (signal_type or "").lower()
    dr = (direction or "").lower()
    if st in {"breakdown", "risk", "concentration_risk", "overlap_exposure_warning"}:
        return True
    return dr == "down"


def _is_bullish(signal_type: str, direction: str) -> bool:
    st = (signal_type or "").lower()
    if st in {"breakdown", "risk", "concentration_risk", "overlap_exposure_warning"}:
        return False
    return (direction or "neutral").lower() != "down"


def _derive_bias_and_agreement(signals: List[Signal]) -> Tuple[str, BiasView, AgreementView]:
    signal_types = [(s.signal_type or "").lower() for s in signals]
    active_signals = len(set(signal_types))

    bullish_count = sum(1 for s in signals if _is_bullish(s.signal_type, s.direction))
    bearish_count = sum(1 for s in signals if _is_bearish(s.signal_type, s.direction))

    if bullish_count > 0 and bearish_count > 0:
        bias = "Mixed / Needs Confirmation"
        bias_key = "mixed"
        aligned = max(bullish_count, bearish_count)
        agreement = "Low"
    elif bearish_count > 0:
        bias = "Breakdown Risk"
        bias_key = "bearish"
        aligned = bearish_count
        agreement = "High" if active_signals <= 1 else "Moderate"
    else:
        has_pullback = any(t in {"dip", "buy_the_dip", "quality_dip"} for t in signal_types)
        has_breakout = any(t in {"breakout", "trend", "trend_continuation"} for t in signal_types)
        if has_pullback and has_breakout:
            bias = "Breakout + Pullback Buy"
        elif has_breakout:
            bias = "Momentum Breakout"
        elif has_pullback:
            bias = "Buy Pullback"
        else:
            bias = "Watch / Developing"
        bias_key = "bullish" if "Watch" not in bias else "mixed"
        aligned = bullish_count
        if active_signals <= 1:
            agreement = "High"
        else:
            agreement = "Moderate"

    icon, color, label = BIAS_STYLE[bias_key]
    agreement_view = AgreementView(label=agreement, aligned_signals=aligned, active_signals=active_signals)
    return bias, BiasView(key=bias_key, icon=icon, embed_color=color, label=label), agreement_view


def derive_bias(signals: Iterable[Signal]) -> str:
    bias, _, _ = _derive_bias_and_agreement(list(signals))
    return bias


def _extract_key_levels(signals: Iterable[Signal]) -> Optional[str]:
    levels: List[str] = []
    for s in signals:
        md = s.metadata if isinstance(s.metadata, dict) else {}
        if not md:
            continue
        if md.get("crossed_level") is not None:
            levels.append(f"Trigger {md.get('crossed_level')} crossed")
        if md.get("support") is not None:
            levels.append(f"Support {md.get('support')}")
        if md.get("resistance") is not None:
            levels.append(f"Resistance {md.get('resistance')}")
        if md.get("trigger_price") is not None:
            levels.append(f"Trigger {md.get('trigger_price')}")
        if md.get("moving_averages"):
            levels.append("Moving averages in play")
    if not levels:
        return None
    ordered: List[str] = []
    seen = set()
    for level in levels:
        if level not in seen:
            ordered.append(level)
            seen.add(level)
    return "; ".join(ordered[:3])


def _signal_themes(signals: Iterable[Signal]) -> List[str]:
    themes: List[str] = []
    seen = set()
    for s in signals:
        key = (s.signal_type or "").lower()
        theme = SIGNAL_THEME_LABELS.get(key) or normalize_signal_label(key)
        if theme not in seen:
            themes.append(theme)
            seen.add(theme)
    return themes[:3]


def _resolve_sector(signals: Iterable[Signal]) -> Optional[str]:
    sectors = []
    for s in signals:
        md = s.metadata if isinstance(s.metadata, dict) else {}
        sector = md.get("sector") if isinstance(md, dict) else None
        if isinstance(sector, str) and sector.strip():
            sectors.append(sector.strip())
    if not sectors:
        return None
    return Counter(sectors).most_common(1)[0][0]


def _why_it_matters(signals: List[Signal], agreement: AgreementView, sector: Optional[str]) -> str:
    types = {(s.signal_type or "").lower() for s in signals}
    brains = {(s.brain or "").lower() for s in signals}
    has_volume = any("volume" in c.lower() for s in signals for c in (s.confirmations or []))
    has_ma = any("ma" in c.lower() or "moving" in c.lower() for s in signals for c in (s.confirmations or []))

    if agreement.label == "Low":
        text = "Pullback setup is forming, but broader confirmation is incomplete."
    elif "macro_divergence" in types:
        text = "Broader market relationships are not fully confirming the move."
    elif "breakout" in types and (has_volume or has_ma):
        text = "Volume confirmed breakout with moving-average alignment suggests continuation."
    elif types & {"buy_the_dip", "dip", "quality_dip"} and "buffett" in brains:
        text = "Short-term weakness inside a stronger long-term accumulation profile."
    elif types & {"risk", "concentration_risk", "breakdown"}:
        text = "Risk signals are elevated and argue for tighter risk control."
    else:
        text = (signals[0].why_it_matters or signals[0].reason or "Conditions support a monitored setup.").strip()

    if sector:
        text += f" Sector context: {sector} is seeing multiple active names."
    return text


def _opportunity_rank_score(signals: List[Signal], agreement: AgreementView, confidence: int) -> int:
    importance = max(SIGNAL_IMPORTANCE_BONUS.get((s.signal_type or "").lower(), 25) for s in signals)
    agreement_bonus = 40 if agreement.label == "High" else 20 if agreement.label == "Moderate" else 0
    return int(confidence + agreement_bonus + importance)


def _group_by_ticker(signals: List[Signal], mode: str = "pro") -> List[TickerOpportunity]:
    grouped: Dict[str, List[Signal]] = defaultdict(list)
    for signal in signals:
        grouped[signal.ticker].append(signal)

    opportunities: List[TickerOpportunity] = []
    for ticker, items in grouped.items():
        confidence = max(int(s.confidence or 0) for s in items)
        confidence_view = _confidence_view(confidence)
        bias, bias_view, agreement = _derive_bias_and_agreement(items)
        sector = _resolve_sector(items)
        rank = _opportunity_rank_score(items, agreement, confidence)

        opportunity = TickerOpportunity(
            ticker=ticker,
            signals=items,
            signal_labels=list(dict.fromkeys(normalize_signal_label(s.signal_type) for s in items)),
            strategy_labels=list(dict.fromkeys(normalize_strategy_label(s.brain, mode=mode) for s in items)),
            confidence_score=confidence,
            confidence_view=confidence_view,
            bias=bias,
            bias_view=bias_view,
            agreement=agreement,
            key_signals=_signal_themes(items),
            why_it_matters=_why_it_matters(items, agreement=agreement, sector=None),
            key_levels=_extract_key_levels(items),
            sector=sector,
            rank_score=rank,
        )
        opportunities.append(opportunity)

    opportunities.sort(key=lambda o: (-o.rank_score, -o.agreement.active_signals, o.ticker))
    return opportunities


def _split_top_watchlist(opps: List[TickerOpportunity], top_n: int = 3) -> Tuple[List[TickerOpportunity], List[TickerOpportunity]]:
    top = opps[:top_n]
    watch = opps[top_n:]
    return top, watch


def _top_header_label(top_count: int) -> str:
    return f"Top Opportunity: {top_count}" if top_count == 1 else f"Top Opportunities: {top_count}"


def _mode_default(mode: Optional[str]) -> str:
    value = (mode or os.environ.get("DISCORD_DIGEST_MODE") or "pro").strip().lower()
    return value if value in {"pro", "novice"} else "pro"


def _show_agreement_default(show_signal_agreement: Optional[bool]) -> bool:
    if isinstance(show_signal_agreement, bool):
        return show_signal_agreement
    return os.environ.get("DISCORD_SHOW_SIGNAL_AGREEMENT", "1") != "0"


def _use_colored_embed_default(use_colored_embed: Optional[bool]) -> bool:
    if isinstance(use_colored_embed, bool):
        return use_colored_embed
    return os.environ.get("DISCORD_DIGEST_COLOR_EMBEDS", "1") != "0"


def _stars(view: ConfidenceView) -> str:
    return "⭐" * view.stars


def _legend() -> str:
    return (
        "Legend: 🟢 bullish, 🟡 mixed/watch, 🔴 bearish risk | "
        "⭐ confidence strength | Active signals = total signal types firing | "
        "Aligned signals = signals pointing in same direction"
    )


def format_digest_text(
    signals: List[Signal],
    title: Optional[str] = None,
    mode: Optional[str] = None,
    show_signal_agreement: Optional[bool] = None,
) -> str:
    mode_value = _mode_default(mode)
    show_agreement = _show_agreement_default(show_signal_agreement)
    digest_title = title or "📊 Market Signal Digest"

    opportunities = _group_by_ticker(signals, mode=mode_value)
    if not opportunities:
        return f"{digest_title}\n\nNo active opportunities right now."

    top, watch = _split_top_watchlist(opportunities, top_n=3)
    lines: List[str] = [digest_title, "", f"🔥 {_top_header_label(len(top))}", f"⚠️ Watchlist: {len(watch)}", ""]

    for opp in top:
        lines.append(f"{opp.bias_view.icon} {opp.ticker} — Bias: {opp.bias}")
        lines.append(f"Confidence: {_stars(opp.confidence_view)} ({opp.confidence_view.label})")
        lines.append(f"Active signals: {opp.agreement.active_signals} | Aligned signals: {opp.agreement.aligned_signals}")
        if show_agreement:
            lines.append(f"Signal Agreement: {opp.agreement.label}")
        lines.append(f"Strategies: {', '.join(opp.strategy_labels[:3])}")
        lines.append(f"Key Signals: {'; '.join(opp.key_signals)}")
        if opp.key_levels:
            lines.append(f"Key Levels: {opp.key_levels}")
        lines.append(f"Why it matters: {opp.why_it_matters}")
        if mode_value == "novice":
            lines.append("What this means: stronger setups usually combine higher confidence and better signal agreement.")
        lines.append("")

    if watch:
        lines.append("⚠️ Watchlist")
        for opp in watch[:12]:
            lines.append(f"- {opp.ticker} — {opp.bias} | {_stars(opp.confidence_view)} | agreement {opp.agreement.label}")

    lines.append("")
    lines.append(_legend())

    content = "\n".join(lines).strip()
    if len(content) <= MAX_DISCORD_CONTENT_CHARS:
        return content

    truncated = content[: MAX_DISCORD_CONTENT_CHARS - 40].rstrip()
    return truncated + "\n\n…(digest truncated for Discord limit)"


def format_digest_embed(
    signals: List[Signal],
    title: Optional[str] = None,
    mode: Optional[str] = None,
    use_colored_embed: Optional[bool] = None,
    show_signal_agreement: Optional[bool] = None,
) -> Dict[str, object]:
    mode_value = _mode_default(mode)
    show_agreement = _show_agreement_default(show_signal_agreement)
    use_colored_embed_value = _use_colored_embed_default(use_colored_embed)

    opportunities = _group_by_ticker(signals, mode=mode_value)
    top, watch = _split_top_watchlist(opportunities, top_n=3)

    top_label = _top_header_label(len(top))
    description = [top_label, f"Watchlist: {len(watch)}"]

    embed_color = 0x2563EB
    if use_colored_embed_value and top:
        embed_color = top[0].bias_view.embed_color

    fields: List[Dict[str, object]] = []
    for opp in top:
        body = [
            f"{opp.bias_view.icon} Bias: {opp.bias}",
            f"Confidence: {_stars(opp.confidence_view)} ({opp.confidence_view.label})",
            f"Active signals: {opp.agreement.active_signals} | Aligned signals: {opp.agreement.aligned_signals}",
        ]
        if show_agreement:
            body.append(f"Signal Agreement: {opp.agreement.label}")
        body.append(f"Strategies: {', '.join(opp.strategy_labels[:3])}")
        body.append(f"Key Signals: {'; '.join(opp.key_signals)}")
        if opp.key_levels:
            body.append(f"Key Levels: {opp.key_levels}")
        body.append(f"Why it matters: {opp.why_it_matters}")
        if mode_value == "novice":
            body.append("What this means: stronger setups combine confidence with agreement.")
        fields.append({"name": opp.ticker, "value": "\n".join(body)[:1000], "inline": False})

    if watch:
        watchline = ", ".join(f"{o.ticker} ({_stars(o.confidence_view)})" for o in watch[:12])
        fields.append({"name": "Watchlist", "value": watchline[:1000], "inline": False})

    return {
        "title": title or "Market Signal Digest",
        "description": "\n".join(description),
        "color": embed_color,
        "fields": fields[:24],
        "footer": {"text": _legend()},
    }


def format_digest_payload(
    signals: List[Signal],
    title: Optional[str] = None,
    mode: Optional[str] = None,
    prefer_embed: Optional[bool] = None,
    use_colored_embed: Optional[bool] = None,
    show_signal_agreement: Optional[bool] = None,
) -> Dict[str, object]:
    if prefer_embed is None:
        prefer_embed = os.environ.get("DISCORD_DIGEST_USE_EMBED", "0") == "1"

    text = format_digest_text(
        signals,
        title=title,
        mode=mode,
        show_signal_agreement=show_signal_agreement,
    )
    if not prefer_embed:
        return {"content": text}

    embed = format_digest_embed(
        signals,
        title=title,
        mode=mode,
        use_colored_embed=use_colored_embed,
        show_signal_agreement=show_signal_agreement,
    )
    return {
        "content": "📊 Signal digest generated",
        "embeds": [embed],
        "fallback_content": text,
    }


def format_digest(signals: List[Signal], title: Optional[str] = None) -> str:
    """Backwards-compatible plain text digest entrypoint."""
    return format_digest_text(signals, title=title)
