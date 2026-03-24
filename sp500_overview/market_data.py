"""Fresh market data collection for the S&P 500 overview."""

from __future__ import annotations

import csv
import io
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

import requests
import yfinance as yf
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from sp500_overview.models import SP500Snapshot

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QuoteSpec:
    label: str
    symbol: str
    format_hint: str = "number"


SP500_SPEC = QuoteSpec("S&P 500", "^GSPC")
YIELD_10Y_SPEC = QuoteSpec("U.S. 10-year Treasury yield", "^TNX", format_hint="yield_pct")
VIX_SPEC = QuoteSpec("VIX", "^VIX")
WTI_SPEC = QuoteSpec("WTI crude oil", "CL=F")
SECTOR_SPECS = [
    QuoteSpec("Technology", "XLK"),
    QuoteSpec("Financials", "XLF"),
    QuoteSpec("Energy", "XLE"),
    QuoteSpec("Health Care", "XLV"),
    QuoteSpec("Industrials", "XLI"),
    QuoteSpec("Consumer Discretionary", "XLY"),
    QuoteSpec("Consumer Staples", "XLP"),
    QuoteSpec("Utilities", "XLU"),
    QuoteSpec("Materials", "XLB"),
    QuoteSpec("Real Estate", "XLRE"),
    QuoteSpec("Communication Services", "XLC"),
]


def _requests_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": "stock-alert-bot/sp500-overview"})
    return session


def _safe_float(value: object) -> Optional[float]:
    try:
        if value is None:
            return None
        numeric = float(value)
        return numeric if numeric == numeric else None
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


def _normalize_quote_value(spec: QuoteSpec, value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    if spec.format_hint == "yield_pct" and value > 20:
        return value / 10.0
    return value


def _retry_call(name: str, func, attempts: int = 3):
    last_error: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except Exception as exc:
            last_error = exc
            logger.warning("sp500_overview_retry name=%s attempt=%s error=%s", name, attempt, exc)
            if attempt < attempts:
                time.sleep(0.4 * attempt)
    raise RuntimeError(f"{name} failed after {attempts} attempts: {last_error}")


class MarketDataFetcher:
    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or _requests_session()

    def _fetch_history(self, spec: QuoteSpec, period: str = "1y"):
        ticker = yf.Ticker(spec.symbol)
        history = ticker.history(period=period, interval="1d", auto_adjust=False, prepost=True)
        closes = history.get("Close") if hasattr(history, "get") else None
        if closes is None:
            raise ValueError(f"history missing close column for {spec.symbol}")
        closes = closes.dropna()
        if len(closes) == 0:
            raise ValueError(f"no price history for {spec.symbol}")
        return ticker, closes

    def _fetch_latest_price_and_change(self, spec: QuoteSpec) -> tuple[Optional[float], Optional[float], Optional[datetime], Iterable]:
        ticker, closes = self._fetch_history(spec)
        latest_close = _safe_float(closes.iloc[-1])
        previous_close = _safe_float(closes.iloc[-2]) if len(closes) > 1 else None
        latest_time = _as_datetime(closes.index[-1])

        latest_price = latest_close
        previous_price = previous_close
        try:
            fast_info = ticker.fast_info
            live = _safe_float(getattr(fast_info, "last_price", None)) or _safe_float(getattr(fast_info, "regular_market_price", None))
            prev = _safe_float(getattr(fast_info, "previous_close", None))
            if live is not None:
                latest_price = live
            if prev is not None:
                previous_price = prev
        except Exception:
            pass

        latest_value = _normalize_quote_value(spec, latest_price)
        previous_value = _normalize_quote_value(spec, previous_price)
        change_pct = None
        if latest_value is not None and previous_value not in (None, 0):
            change_pct = ((latest_value - previous_value) / previous_value) * 100.0
        return latest_value, change_pct, latest_time, closes

    def _fetch_sector_moves(self) -> tuple[list[tuple[str, float]], list[tuple[str, float]], list[str]]:
        results: list[tuple[str, float]] = []
        warnings: list[str] = []
        for spec in SECTOR_SPECS:
            try:
                _, change_pct, _, _ = _retry_call(spec.symbol, lambda spec=spec: self._fetch_latest_price_and_change(spec))
            except Exception as exc:
                logger.warning("sp500_overview_sector_unavailable symbol=%s error=%s", spec.symbol, exc)
                warnings.append(f"{spec.label} sector data could not be retrieved.")
                continue
            if change_pct is not None:
                results.append((spec.label, change_pct))
        results.sort(key=lambda item: item[1], reverse=True)
        return results[:2], list(reversed(results[-2:])), warnings

    def _fetch_sp500_ytd_change(self, closes, latest_value: Optional[float], reference_year: int) -> Optional[float]:
        if latest_value is None:
            return None
        reference_close = None
        for index_value, close_value in zip(closes.index, closes.values):
            date_value = _as_datetime(index_value)
            if date_value is None:
                continue
            if date_value.year < reference_year:
                reference_close = _safe_float(close_value)
        if reference_close is None:
            for index_value, close_value in zip(closes.index, closes.values):
                date_value = _as_datetime(index_value)
                if date_value is None:
                    continue
                if date_value.year == reference_year:
                    reference_close = _safe_float(close_value)
                    break
        if reference_close in (None, 0):
            return None
        return ((latest_value - reference_close) / reference_close) * 100.0

    def fetch_effective_fed_funds_rate(self) -> tuple[Optional[float], str]:
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=FEDFUNDS"
        response = self.session.get(url, timeout=15)
        response.raise_for_status()
        rows = list(csv.DictReader(io.StringIO(response.text)))
        for row in reversed(rows):
            value = (row.get("FEDFUNDS") or "").strip()
            if not value or value == ".":
                continue
            return float(value), (row.get("observation_date") or row.get("DATE") or "").strip()
        return None, ""

    def fetch_snapshot(self, now: Optional[datetime] = None) -> SP500Snapshot:
        warnings: list[str] = []

        try:
            sp500_level, sp500_daily_change_pct, as_of, sp500_closes = _retry_call(
                "sp500",
                lambda: self._fetch_latest_price_and_change(SP500_SPEC),
            )
            reference_year = (now or as_of or datetime.utcnow()).year
            sp500_ytd_change_pct = self._fetch_sp500_ytd_change(sp500_closes, sp500_level, reference_year)
        except Exception as exc:
            logger.warning("sp500_overview_sp500_unavailable error=%s", exc)
            sp500_level = None
            sp500_daily_change_pct = None
            sp500_ytd_change_pct = None
            as_of = None
            warnings.append("S&P 500 data could not be retrieved.")

        try:
            treasury_10y_yield_pct, treasury_10y_change_pct, _, _ = _retry_call(
                "us10y",
                lambda: self._fetch_latest_price_and_change(YIELD_10Y_SPEC),
            )
        except Exception as exc:
            logger.warning("sp500_overview_us10y_unavailable error=%s", exc)
            treasury_10y_yield_pct = None
            treasury_10y_change_pct = None
            warnings.append("10-year Treasury yield data could not be retrieved.")

        try:
            vix_level, vix_change_pct, _, _ = _retry_call("vix", lambda: self._fetch_latest_price_and_change(VIX_SPEC))
        except Exception as exc:
            logger.warning("sp500_overview_vix_unavailable error=%s", exc)
            vix_level = None
            vix_change_pct = None
            warnings.append("VIX data could not be retrieved.")

        try:
            _, wti_change_pct, _, _ = _retry_call("wti", lambda: self._fetch_latest_price_and_change(WTI_SPEC))
        except Exception as exc:
            logger.warning("sp500_overview_wti_unavailable error=%s", exc)
            wti_change_pct = None
            warnings.append("WTI crude data could not be retrieved.")

        strongest_sectors, weakest_sectors, sector_warnings = self._fetch_sector_moves()
        warnings.extend(sector_warnings)

        fed_funds_rate = None
        fed_funds_as_of = ""
        try:
            fed_funds_rate, fed_funds_as_of = self.fetch_effective_fed_funds_rate()
        except Exception as exc:
            logger.warning("sp500_overview_fed_funds_unavailable error=%s", exc)
            warnings.append("Fed funds context could not be retrieved.")

        return SP500Snapshot(
            as_of=as_of,
            sp500_level=sp500_level,
            sp500_daily_change_pct=sp500_daily_change_pct,
            sp500_ytd_change_pct=sp500_ytd_change_pct,
            treasury_10y_yield_pct=treasury_10y_yield_pct,
            treasury_10y_change_pct=treasury_10y_change_pct,
            vix_level=vix_level,
            vix_change_pct=vix_change_pct,
            wti_change_pct=wti_change_pct,
            fed_funds_rate=fed_funds_rate,
            fed_funds_as_of=fed_funds_as_of,
            strongest_sectors=strongest_sectors,
            weakest_sectors=weakest_sectors,
            warnings=warnings,
        )