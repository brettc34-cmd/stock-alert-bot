"""Message generation for the S&P 500 daily overview."""

from __future__ import annotations

from datetime import datetime
from typing import List

from sp500_overview.config import SP500OverviewSettings
from sp500_overview.headlines import classify_driver_labels
from sp500_overview.models import Headline, SP500OverviewMessage, SP500Snapshot

DISCLAIMER = "“This is general information only and not financial advice. For personal guidance, please talk to a licensed professional.”"


def _word_count(text: str) -> int:
    return len([word for word in text.split() if word.strip()])


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "data could not be retrieved"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


def _fmt_number(value: float | None) -> str:
    if value is None:
        return "data could not be retrieved"
    return f"{value:,.2f}"


def _truncate_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[: max(1, max_words - 1)]) + "..."


def _sector_fragment(snapshot: SP500Snapshot) -> str:
    fragments: List[str] = []
    if snapshot.strongest_sectors:
        strongest = ", ".join(label for label, _ in snapshot.strongest_sectors[:2])
        fragments.append(f"leaders: {strongest}")
    if snapshot.weakest_sectors:
        weakest = ", ".join(label for label, _ in snapshot.weakest_sectors[:2])
        fragments.append(f"laggards: {weakest}")
    return "; ".join(fragments) if fragments else "sector leadership data could not be retrieved"


def _top_drivers(snapshot: SP500Snapshot, headlines: List[Headline]) -> str:
    labels = classify_driver_labels(headlines, limit=3)
    items = labels[:]
    if snapshot.wti_change_pct is not None and not any("Oil" in item for item in items):
        if abs(snapshot.wti_change_pct) >= 1.0:
            items.append("Oil")
    sector_text = _sector_fragment(snapshot)
    if sector_text:
        items.append(sector_text)
    if not items:
        return "Headline and sector driver data could not be retrieved"
    return "; ".join(items[:4])


def _key_headlines(headlines: List[Headline]) -> str:
    if not headlines:
        return "headlines could not be retrieved"
    top = [f"{headline.source}: {headline.title.rstrip(' .')}" for headline in headlines[:2]]
    return "; ".join(top)


def _bull_case(snapshot: SP500Snapshot) -> str:
    reasons: List[str] = []
    if snapshot.sp500_ytd_change_pct is not None and snapshot.sp500_ytd_change_pct > 0:
        reasons.append("the index is still positive YTD")
    if snapshot.sp500_daily_change_pct is not None and snapshot.sp500_daily_change_pct >= 0:
        reasons.append("today's tape is holding up")
    if snapshot.treasury_10y_change_pct is not None and snapshot.treasury_10y_change_pct <= 0:
        reasons.append("yields are not adding pressure")
    if snapshot.strongest_sectors:
        reasons.append(f"leadership includes {snapshot.strongest_sectors[0][0]}")
    if not reasons:
        return "supportive live inputs could not be confirmed"
    return "; ".join(reasons[:3])


def _bear_case(snapshot: SP500Snapshot) -> str:
    reasons: List[str] = []
    if snapshot.sp500_daily_change_pct is not None and snapshot.sp500_daily_change_pct < 0:
        reasons.append("the index is trading lower on the day")
    if snapshot.treasury_10y_change_pct is not None and snapshot.treasury_10y_change_pct > 0:
        reasons.append("higher yields are a headwind")
    if snapshot.wti_change_pct is not None and snapshot.wti_change_pct > 1.0:
        reasons.append("oil is firm enough to pressure inflation expectations")
    if snapshot.vix_level is not None and snapshot.vix_level >= 20:
        reasons.append("volatility is still elevated")
    if snapshot.weakest_sectors:
        reasons.append(f"weakness is visible in {snapshot.weakest_sectors[0][0]}")
    if not reasons:
        return "clear downside pressure was not confirmed in live inputs"
    return "; ".join(reasons[:3])


def _bottom_line(snapshot: SP500Snapshot) -> str:
    parts: List[str] = []
    if snapshot.sp500_daily_change_pct is not None:
        direction = "higher" if snapshot.sp500_daily_change_pct >= 0 else "lower"
        parts.append(f"The S&P 500 is trading {direction} by {_fmt_pct(snapshot.sp500_daily_change_pct)}")
    else:
        parts.append("The latest S&P 500 reading could not be retrieved")
    if snapshot.treasury_10y_yield_pct is not None:
        parts.append(f"the 10-year yield is near {snapshot.treasury_10y_yield_pct:.2f}%")
    if snapshot.fed_funds_rate is not None and snapshot.fed_funds_as_of:
        parts.append(f"the latest fed funds rate was {snapshot.fed_funds_rate:.2f}% as of {snapshot.fed_funds_as_of}")
    if snapshot.vix_level is not None:
        parts.append(f"VIX is {snapshot.vix_level:.2f}")
    return "; ".join(parts[:4]) + "."


def generate_summary(
    snapshot: SP500Snapshot,
    headlines: List[Headline],
    generated_at: datetime,
    settings: SP500OverviewSettings,
) -> SP500OverviewMessage:
    timestamp_label = generated_at.strftime("%Y-%m-%d %I:%M %p %Z")
    subject_prefix = f"{settings.subject_prefix.strip()} " if settings.subject_prefix.strip() else ""
    subject = f"{subject_prefix}S&P 500 Daily Overview | {generated_at.strftime('%a %b %d, %Y')}"

    lines = [
        "S&P 500 Daily Overview",
        f"- Index level: {_fmt_number(snapshot.sp500_level)}",
        f"- Daily move: {_fmt_pct(snapshot.sp500_daily_change_pct)}",
        f"- YTD: {_fmt_pct(snapshot.sp500_ytd_change_pct)}",
        f"- Top drivers: {_top_drivers(snapshot, headlines)}",
        f"- Key headlines: {_key_headlines(headlines)}",
        f"- Bull case: {_bull_case(snapshot)}",
        f"- Bear case: {_bear_case(snapshot)}",
        f"- Bottom line: {_bottom_line(snapshot)}",
        "",
        DISCLAIMER,
    ]
    body = "\n".join(lines).strip()
    if _word_count(body) > settings.max_words:
        lines[4] = f"- Top drivers: {_truncate_words(_top_drivers(snapshot, headlines), 12)}"
        lines[5] = f"- Key headlines: {_truncate_words(_key_headlines(headlines), 14)}"
        lines[6] = f"- Bull case: {_truncate_words(_bull_case(snapshot), 12)}"
        lines[7] = f"- Bear case: {_truncate_words(_bear_case(snapshot), 12)}"
        lines[8] = f"- Bottom line: {_truncate_words(_bottom_line(snapshot), 18)}"
        body = "\n".join(lines).strip()

    warnings = list(snapshot.warnings)
    return SP500OverviewMessage(
        subject=subject,
        body=body,
        timestamp_label=timestamp_label,
        word_count=_word_count(body),
        warnings=warnings,
    )