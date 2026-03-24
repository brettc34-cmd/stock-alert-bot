"""Formatting helpers for the daily market update."""

from __future__ import annotations

from typing import Iterable, List, Optional

from market_update.models import Headline, InstrumentQuote, MarketUpdateResult


def _fmt_change(change_pct: Optional[float]) -> str:
    if change_pct is None:
        return "change unavailable"
    sign = "+" if change_pct >= 0 else ""
    return f"{sign}{change_pct:.2f}%"


def _fmt_price(quote: InstrumentQuote) -> str:
    if quote.price is None:
        return f"Unavailable ({quote.note or quote.source})"
    if quote.format_hint == "currency":
        return f"${quote.price:,.2f} ({_fmt_change(quote.change_pct)})"
    if quote.format_hint == "yield_pct":
        return f"{quote.price:.2f}% ({_fmt_change(quote.change_pct)})"
    return f"{quote.price:,.2f} ({_fmt_change(quote.change_pct)})"


def _format_quote_lines(quotes: Iterable[InstrumentQuote]) -> List[str]:
    return [f"- {quote.label}: {_fmt_price(quote)}" for quote in quotes]


def _format_sectors(sectors: List[InstrumentQuote]) -> List[str]:
    available = [q for q in sectors if q.change_pct is not None]
    if not available:
        return ["- Sector breadth unavailable from runtime sources."]
    strongest = ", ".join(f"{q.label} ({q.change_pct:+.2f}%)" for q in available[:2])
    weakest = ", ".join(f"{q.label} ({q.change_pct:+.2f}%)" for q in available[-2:])
    return [
        f"- Strongest: {strongest}",
        f"- Weakest: {weakest}",
    ]


def _format_headlines(headlines: List[Headline]) -> List[str]:
    if not headlines:
        return ["- No headlines were available from the configured feeds at runtime."]
    return [f"- {h.source}: {h.title}" for h in headlines[:5]]


def format_body(
    big_picture: str,
    indexes: List[InstrumentQuote],
    rates_and_macro: List[InstrumentQuote],
    fed_context: str,
    commodities: List[InstrumentQuote],
    crypto: List[InstrumentQuote],
    drivers: List[str],
    sectors: List[InstrumentQuote],
    vix: InstrumentQuote,
    headlines: List[Headline],
    watch_next: List[str],
    warnings: List[str],
) -> str:
    lines = [
        "Big picture",
        big_picture,
        "",
        "Major U.S. indexes",
        *_format_quote_lines(indexes),
        "",
        "Rates and macro",
        *_format_quote_lines(rates_and_macro),
        f"- Fed context: {fed_context}",
        "",
        "Commodities",
        *_format_quote_lines(commodities),
        "",
        "Crypto",
        *_format_quote_lines(crypto),
        "",
        "Market drivers",
        *[f"- {driver}" for driver in drivers],
        "",
        "Sector color",
        *_format_sectors(sectors),
        "",
        "Volatility",
        f"- {vix.label}: {_fmt_price(vix)}",
        "",
        "Recent headlines",
        *_format_headlines(headlines),
        "",
        "What to watch next",
        *[f"- {item}" for item in watch_next],
    ]
    if warnings:
        lines.extend(["", "Data quality notes", *[f"- {w}" for w in warnings]])
    return "\n".join(lines).strip()


def format_discord_update(result: MarketUpdateResult, max_chars: int = 1800) -> str:
    """Extract a Discord-friendly preview from a MarketUpdateResult.

    Includes Big picture, Major U.S. indexes, Rates and macro, Commodities,
    Crypto, Market drivers (capped at 3 bullets), and What to watch next
    (capped at 2 bullets). Hard-truncates at max_chars.
    """
    allowed_headers = {
        "Big picture",
        "Major U.S. indexes",
        "Rates and macro",
        "Commodities",
        "Crypto",
        "Market drivers",
        "What to watch next",
    }
    skip_headers = {"Sector color", "Volatility", "Recent headlines", "Data quality notes"}

    current_header = ""
    current_lines: List[str] = []
    sections: List[str] = []
    driver_count = 0
    watch_count = 0

    def flush() -> None:
        nonlocal current_header, current_lines
        if current_header and current_lines:
            sections.append("\n".join([current_header, *current_lines]).strip())
        current_header = ""
        current_lines = []

    for line in result.body.splitlines():
        if not line:
            continue
        if line in allowed_headers:
            flush()
            current_header = line
            if line == "Market drivers":
                driver_count = 0
            elif line == "What to watch next":
                watch_count = 0
            continue
        if line in skip_headers:
            flush()
            current_header = ""
            continue
        if not current_header:
            continue
        if current_header == "Market drivers" and line.startswith("-"):
            if driver_count >= 3:
                continue
            driver_count += 1
        if current_header == "What to watch next" and line.startswith("-"):
            if watch_count >= 2:
                continue
            watch_count += 1
        current_lines.append(line)

    flush()
    preview = "\n\n".join(s for s in sections if s).strip()
    if len(preview) <= max_chars:
        return preview
    return preview[: max_chars - 24].rstrip() + "\n\n...(preview truncated)"