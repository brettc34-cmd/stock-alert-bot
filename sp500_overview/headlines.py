"""RSS headline collection and driver classification for the S&P 500 overview."""

from __future__ import annotations

import email.utils
import html
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests

from sp500_overview.models import Headline

logger = logging.getLogger(__name__)

RSS_FEEDS = [
    ("CNBC Markets", "https://www.cnbc.com/id/20409666/device/rss/rss.html"),
    ("CNBC Economy", "https://www.cnbc.com/id/20910258/device/rss/rss.html"),
    ("Federal Reserve", "https://www.federalreserve.gov/feeds/press_monetary.xml"),
]

THEME_RULES = [
    ("Fed expectations", ("fed", "powell", "rate", "rates", "yield", "treasury", "inflation", "cpi", "pce")),
    ("Jobs and growth", ("jobs", "labor", "employment", "payroll", "unemployment", "gdp", "recession")),
    ("Earnings", ("earnings", "guidance", "forecast", "revenue", "profit")),
    ("Oil", ("oil", "crude", "opec", "gasoline")),
    ("Geopolitics", ("trade", "tariff", "sanction", "shipping", "supply chain", "middle east", "ukraine", "china")),
]

MARKET_RELEVANCE_KEYWORDS = (
    "s&p",
    "sp500",
    "market",
    "stocks",
    "shares",
    "wall street",
    "fed",
    "powell",
    "treasury",
    "yield",
    "bond",
    "inflation",
    "cpi",
    "pce",
    "jobs",
    "labor",
    "payroll",
    "unemployment",
    "earnings",
    "guidance",
    "revenue",
    "profit",
    "oil",
    "crude",
    "opec",
    "recession",
    "gdp",
    "tariff",
    "trade",
    "volatility",
    "vix",
)


def _contains_keyword(text: str, keyword: str) -> bool:
    pattern = r"(?<![A-Za-z0-9])" + re.escape(keyword) + r"(?![A-Za-z0-9])"
    return re.search(pattern, text) is not None


def _parse_pub_date(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def _is_market_relevant(title: str, summary: str) -> bool:
    haystack = f"{title} {summary}".lower()
    return any(_contains_keyword(haystack, keyword) for keyword in MARKET_RELEVANCE_KEYWORDS)


class HeadlineFetcher:
    def __init__(self, session: requests.Session) -> None:
        self.session = session

    def fetch_headlines(self, per_feed_limit: int = 4, total_limit: int = 6) -> List[Headline]:
        items: List[Headline] = []
        seen_titles: set[str] = set()
        for source, url in RSS_FEEDS:
            try:
                response = self.session.get(url, timeout=15)
                response.raise_for_status()
                root = ET.fromstring(response.content)
            except Exception as exc:
                logger.warning("sp500_overview_feed_failed source=%s error=%s", source, exc)
                continue

            count = 0
            for item in root.findall(".//item"):
                title = html.unescape((item.findtext("title") or "").strip())
                if not title:
                    continue
                normalized = title.lower()
                if normalized in seen_titles:
                    continue
                summary = html.unescape((item.findtext("description") or "").strip())
                if not _is_market_relevant(title, summary):
                    continue
                items.append(
                    Headline(
                        source=source,
                        title=title,
                        link=(item.findtext("link") or "").strip(),
                        summary=summary,
                        published_at=_parse_pub_date(item.findtext("pubDate") or item.findtext("published") or ""),
                    )
                )
                seen_titles.add(normalized)
                count += 1
                if count >= per_feed_limit:
                    break

        items.sort(key=lambda item: item.published_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return items[:total_limit]


def classify_driver_labels(headlines: List[Headline], limit: int = 3) -> List[str]:
    grouped: Dict[str, List[Headline]] = {label: [] for label, _ in THEME_RULES}
    for headline in headlines:
        title_haystack = headline.title.lower()
        summary_haystack = headline.summary.lower()
        for label, keywords in THEME_RULES:
            title_match = any(_contains_keyword(title_haystack, keyword) for keyword in keywords)
            summary_match_count = sum(1 for keyword in keywords if _contains_keyword(summary_haystack, keyword))
            if title_match or summary_match_count >= 2:
                grouped[label].append(headline)
                break
    ranked = sorted(grouped.items(), key=lambda item: len(item[1]), reverse=True)
    return [label for label, items in ranked if items][:limit]