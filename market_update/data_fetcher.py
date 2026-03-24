"""Fresh market data collection using public online sources at runtime.

Sources used here:
- Yahoo Finance via yfinance for indexes, yields, dollar, commodities, crypto, VIX, and sector ETFs
- FRED CSV endpoint for effective fed funds rate context
"""

from __future__ import annotations

import csv
import io
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable, List, Optional

import requests
import yfinance as yf
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from market_update.models import InstrumentQuote

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QuoteSpec:
    key: str
    label: str
    symbol: str
    source: str
    format_hint: str = "number"
    transform: Optional[Callable[[float], float]] = None


INDEX_SPECS: List[QuoteSpec] = [
    QuoteSpec("sp500", "S&P 500", "^GSPC", "Yahoo Finance"),
    QuoteSpec("dow", "Dow Jones Industrial Average", "^DJI", "Yahoo Finance"),
    QuoteSpec("nasdaq", "Nasdaq Composite", "^IXIC", "Yahoo Finance"),
]

RATE_SPECS: List[QuoteSpec] = [
    QuoteSpec("us10y", "U.S. 10-year Treasury yield", "^TNX", "Yahoo Finance", format_hint="yield_pct"),
    QuoteSpec("dxy", "U.S. dollar index", "DX-Y.NYB", "Yahoo Finance"),
]

COMMODITY_SPECS: List[QuoteSpec] = [
    QuoteSpec("wti", "WTI crude oil", "CL=F", "Yahoo Finance", format_hint="currency"),
    QuoteSpec("gold", "Gold", "GC=F", "Yahoo Finance", format_hint="currency"),
]

CRYPTO_SPECS: List[QuoteSpec] = [
    QuoteSpec("bitcoin", "Bitcoin", "BTC-USD", "Yahoo Finance", format_hint="currency"),
    QuoteSpec("ethereum", "Ethereum", "ETH-USD", "Yahoo Finance", format_hint="currency"),
]

VIX_SPEC = QuoteSpec("vix", "VIX", "^VIX", "Yahoo Finance")

SECTOR_SPECS: List[QuoteSpec] = [
    QuoteSpec("technology", "Technology", "XLK", "Yahoo Finance"),
    QuoteSpec("financials", "Financials", "XLF", "Yahoo Finance"),
    QuoteSpec("energy", "Energy", "XLE", "Yahoo Finance"),
    QuoteSpec("healthcare", "Health Care", "XLV", "Yahoo Finance"),
    QuoteSpec("industrials", "Industrials", "XLI", "Yahoo Finance"),
    QuoteSpec("consumer_discretionary", "Consumer Discretionary", "XLY", "Yahoo Finance"),
    QuoteSpec("consumer_staples", "Consumer Staples", "XLP", "Yahoo Finance"),
    QuoteSpec("utilities", "Utilities", "XLU", "Yahoo Finance"),
    QuoteSpec("materials", "Materials", "XLB", "Yahoo Finance"),
    QuoteSpec("real_estate", "Real Estate", "XLRE", "Yahoo Finance"),
    QuoteSpec("communication_services", "Communication Services", "XLC", "Yahoo Finance"),
]


def _requests_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": "stock-alert-bot/market-update"})
    return session


def _safe_float(value: object) -> Optional[float]:
    try:
        if value is None:
            return None
        f = float(value)  # type: ignore[arg-type]
        return f if f == f else None  # filter NaN (NaN != NaN)
    except Exception:
        return None


def _as_datetime(value: object) -> Optional[datetime]:
    converter = getattr(value, "to_pydatetime", None)
    if callable(converter):
        try:
            return converter()
        except Exception:
            return None
    if isinstance(value, datetime):
        return value
    return None


def _retry_call(name: str, func: Callable[[], InstrumentQuote], attempts: int = 3) -> InstrumentQuote:
    last_error: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except Exception as exc:
            last_error = exc
            logger.warning("market_update_fetch_retry name=%s attempt=%s error=%s", name, attempt, exc)
            if attempt < attempts:
                time.sleep(0.4 * attempt)
    raise RuntimeError(f"{name} failed after {attempts} attempts: {last_error}")


def _normalize_value(spec: QuoteSpec, value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    normalized = value
    if spec.format_hint == "yield_pct" and normalized > 20:
        normalized = normalized / 10.0
    if spec.transform is not None:
        normalized = spec.transform(normalized)
    return normalized


class MarketDataFetcher:
    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or _requests_session()

    def _fetch_yahoo_quote(self, spec: QuoteSpec) -> InstrumentQuote:
        ticker = yf.Ticker(spec.symbol)
        history = ticker.history(period="5d", interval="1d", auto_adjust=False, prepost=True)
        closes = history.get("Close") if hasattr(history, "get") else None
        if closes is None:
            raise ValueError(f"history missing close column for {spec.symbol}")
        closes = closes.dropna()
        if len(closes) == 0:
            raise ValueError(f"no price history for {spec.symbol}")

        latest_close = _safe_float(closes.iloc[-1])
        previous_close = _safe_float(closes.iloc[-2]) if len(closes) > 1 else None
        latest_time = _as_datetime(closes.index[-1])

        latest_price = latest_close
        previous_price = previous_close

        try:
            fi = ticker.fast_info
            # fast_info in yfinance >=0.2.x is a FastInfo object, not a dict.
            # Use getattr to avoid AttributeError on dict-style .get() calls.
            live = _safe_float(getattr(fi, "last_price", None)) or \
                   _safe_float(getattr(fi, "regular_market_price", None))
            prev = _safe_float(getattr(fi, "previous_close", None))
            if live is not None:
                latest_price = live
            if prev is not None:
                previous_price = prev
        except Exception:
            pass

        if latest_price is None:
            raise ValueError(f"latest price unavailable for {spec.symbol}")

        latest_value = _normalize_value(spec, latest_price)
        previous_value = _normalize_value(spec, previous_price)
        change_pct: Optional[float] = None
        if previous_value not in (None, 0):
            change_pct = ((latest_value - previous_value) / previous_value) * 100.0

        return InstrumentQuote(
            key=spec.key,
            label=spec.label,
            symbol=spec.symbol,
            source=spec.source,
            price=latest_value,
            change_pct=change_pct,
            as_of=latest_time,
            format_hint=spec.format_hint,
        )

    def _fetch_many(self, specs: Iterable[QuoteSpec]) -> List[InstrumentQuote]:
        results: List[InstrumentQuote] = []
        for spec in specs:
            try:
                quote = _retry_call(spec.key, lambda spec=spec: self._fetch_yahoo_quote(spec))
            except Exception as exc:
                logger.warning("market_update_quote_unavailable symbol=%s source=%s error=%s", spec.symbol, spec.source, exc)
                quote = InstrumentQuote(
                    key=spec.key,
                    label=spec.label,
                    symbol=spec.symbol,
                    source=spec.source,
                    format_hint=spec.format_hint,
                    note=f"Unavailable from {spec.source}",
                )
            results.append(quote)
        return results

    def fetch_major_indexes(self) -> List[InstrumentQuote]:
        return self._fetch_many(INDEX_SPECS)

    def fetch_rates_and_macro(self) -> List[InstrumentQuote]:
        return self._fetch_many(RATE_SPECS)

    def fetch_commodities(self) -> List[InstrumentQuote]:
        return self._fetch_many(COMMODITY_SPECS)

    def fetch_crypto(self) -> List[InstrumentQuote]:
        return self._fetch_many(CRYPTO_SPECS)

    def fetch_vix(self) -> InstrumentQuote:
        try:
            return _retry_call(VIX_SPEC.key, lambda: self._fetch_yahoo_quote(VIX_SPEC))
        except Exception as exc:
            logger.warning("market_update_vix_unavailable error=%s", exc)
            return InstrumentQuote(
                key=VIX_SPEC.key,
                label=VIX_SPEC.label,
                symbol=VIX_SPEC.symbol,
                source=VIX_SPEC.source,
                format_hint=VIX_SPEC.format_hint,
                note=f"Unavailable from {VIX_SPEC.source}",
            )

    def fetch_sector_strength(self) -> List[InstrumentQuote]:
        sectors = [quote for quote in self._fetch_many(SECTOR_SPECS) if quote.change_pct is not None]
        sectors.sort(key=lambda quote: quote.change_pct or 0.0, reverse=True)
        return sectors

    def fetch_effective_fed_funds_rate(self) -> Optional[tuple[float, str]]:
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=FEDFUNDS"
        response = self.session.get(url, timeout=15)
        response.raise_for_status()
        rows = list(csv.DictReader(io.StringIO(response.text)))
        for row in reversed(rows):
            value = (row.get("FEDFUNDS") or "").strip()
            if not value or value == ".":
                continue
            # FRED CSV header is "observation_date" in current exports; "DATE" in older ones.
            date_str = (row.get("observation_date") or row.get("DATE") or "").strip()
            return float(value), date_str
        return None