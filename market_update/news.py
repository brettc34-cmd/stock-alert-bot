"""Headline collection and lightweight factor summarization for the market update.

Sources used here:
- Reuters RSS where available
- CNBC / major-market RSS feeds
- Federal Reserve press release RSS for policy context
"""

from __future__ import annotations

import email.utils
import html
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests

from market_update.models import Headline

logger = logging.getLogger(__name__)


def _contains_keyword(text: str, keyword: str) -> bool:
    pattern = r"(?<![A-Za-z0-9])" + re.escape(keyword) + r"(?![A-Za-z0-9])"
    return re.search(pattern, text) is not None


# Reuters (feeds.reuters.com) is frequently DNS-blocked outside Reuters infrastructure;
# replaced with a second CNBC feed for broader headline coverage.
RSS_FEEDS = [
    ("CNBC Markets", "https://www.cnbc.com/id/20409666/device/rss/rss.html"),
    ("CNBC Economy", "https://www.cnbc.com/id/20910258/device/rss/rss.html"),
    ("Federal Reserve", "https://www.federalreserve.gov/feeds/press_monetary.xml"),
]


THEME_RULES = [
    ("Fed and rates", ("fed", "powell", "rate", "rates", "yield", "treasury", "inflation")),
    ("Labor and growth", ("jobs", "labor", "employment", "payroll", "growth", "recession")),
    ("Geopolitics and trade", ("geopolit", "tariff", "trade", "war", "sanction")),
    ("Earnings and guidance", ("earnings", "guidance", "forecast", "revenue", "profit")),
    ("Oil and commodities", ("oil", "crude", "gold", "commodity", "opec")),
    ("Currencies and dollar", ("dollar", "currency", "fx", "yen", "euro")),
    ("Crypto risk appetite", ("bitcoin", "ethereum", "crypto", "digital asset")),
]


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


class NewsFetcher:
    def __init__(self, session: requests.Session) -> None:
        self.session = session

    def fetch_headlines(self, per_feed_limit: int = 6, total_limit: int = 12) -> List[Headline]:
        items: List[Headline] = []
        seen_titles = set()
        for source, url in RSS_FEEDS:
            try:
                response = self.session.get(url, timeout=15)
                response.raise_for_status()
                root = ET.fromstring(response.content)
            except Exception as exc:
                logger.warning("market_update_news_feed_failed source=%s error=%s", source, exc)
                continue

            count = 0
            for item in root.findall(".//item"):
                title = (item.findtext("title") or "").strip()
                if not title:
                    continue
                title = html.unescape(title)
                normalized = title.lower()
                if normalized in seen_titles:
                    continue
                headline = Headline(
                    source=source,
                    title=title,
                    link=(item.findtext("link") or "").strip(),
                    published_at=_parse_pub_date(item.findtext("pubDate") or item.findtext("published") or ""),
                    summary=html.unescape((item.findtext("description") or "").strip()),
                )
                items.append(headline)
                seen_titles.add(normalized)
                count += 1
                if count >= per_feed_limit:
                    break

        items.sort(key=lambda headline: headline.published_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return items[:total_limit]


def summarize_market_drivers(headlines: List[Headline], limit: int = 5) -> List[str]:
    grouped: Dict[str, List[Headline]] = {label: [] for label, _ in THEME_RULES}
    unmatched: List[Headline] = []
    for headline in headlines:
        title_haystack = headline.title.lower()
        summary_haystack = headline.summary.lower()
        matched_label: Optional[str] = None
        for label, keywords in THEME_RULES:
            title_match = any(_contains_keyword(title_haystack, keyword) for keyword in keywords)
            summary_match_count = sum(1 for keyword in keywords if _contains_keyword(summary_haystack, keyword))
            if title_match or summary_match_count >= 2:
                matched_label = label
                break
        if matched_label:
            grouped[matched_label].append(headline)
        else:
            unmatched.append(headline)

    drivers: List[str] = []
    ranked_groups = sorted(grouped.items(), key=lambda item: len(item[1]), reverse=True)
    for label, items in ranked_groups:
        if not items or len(drivers) >= limit:
            continue
        lead = items[0].title.rstrip(" .")
        drivers.append(f"{label} are in focus after headlines on {lead}.")

    has_fed_theme = any(driver.startswith("Fed and rates") for driver in drivers)
    for headline in unmatched:
        if len(drivers) >= max(3, limit):
            break
        if has_fed_theme and headline.source == "Federal Reserve":
            continue
        drivers.append(f"Headline flow is also tracking {headline.title.rstrip(' .')}.")

    if not drivers:
        drivers.append("Headline flow was limited at run time, so the note leans more heavily on price action and macro gauges.")
    return drivers[:limit]