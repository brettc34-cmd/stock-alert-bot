"""Market data engine.

Provides a canonical market snapshot for a given ticker.
"""

from datetime import datetime, timezone
from typing import Dict, Any, Optional
import logging
import time as time_mod

import yfinance as yf
from requests import exceptions as requests_exceptions
from services.metrics import record_quote_fetch


logger = logging.getLogger(__name__)
TRANSIENT_EXCEPTIONS = (
    requests_exceptions.RequestException,
    TimeoutError,
    ConnectionError,
)


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _days_until_earnings(info: Dict[str, Any], now: datetime) -> Optional[int]:
    raw = info.get("earningsDate")
    if not raw:
        return None
    # yfinance may return list/tuple/range-like for earningsDate
    date_value = raw[0] if isinstance(raw, (list, tuple)) else raw
    if hasattr(date_value, "to_pydatetime"):
        date_value = date_value.to_pydatetime()
    if not isinstance(date_value, datetime):
        return None
    if date_value.tzinfo is None:
        date_value = date_value.replace(tzinfo=timezone.utc)
    return int((date_value - now).total_seconds() // 86400)


def _estimate_iv_rank(ticker: yf.Ticker) -> Optional[float]:
    """Best-effort IV rank proxy in [0, 1] from near-term options chain.

    Falls back to None when options are unavailable.
    """
    try:
        expiries = ticker.options
        if not expiries:
            return None
        chain = ticker.option_chain(expiries[0])
        ivs = []
        for side in (chain.calls, chain.puts):
            if side is None or side.empty or "impliedVolatility" not in side.columns:
                continue
            series = side["impliedVolatility"].dropna()
            ivs.extend(float(v) for v in series.tolist() if isinstance(v, (int, float)))
        if not ivs:
            return None
        iv_now = sorted(ivs)[len(ivs) // 2]
        iv_min, iv_max = min(ivs), max(ivs)
        if iv_max <= iv_min:
            return 0.5
        return max(0.0, min(1.0, (iv_now - iv_min) / (iv_max - iv_min)))
    except Exception:
        return None


def fetch_quote(ticker_symbol: str) -> Optional[Dict[str, Any]]:
    """Fetch a quote and normalize the returned fields.

    Returns None if the ticker could not be fetched.
    """
    max_attempts = 3
    error_text = "unknown"
    start_ts = time_mod.perf_counter()
    for attempt in range(1, max_attempts + 1):
        try:
            ticker = yf.Ticker(ticker_symbol)
            info = ticker.info
            if not info:
                raise ValueError(f"Empty quote payload for {ticker_symbol}")

            # Normalize timestamp (yfinance does not expose quote timestamp reliably)
            now = datetime.now(timezone.utc)
            hist = ticker.history(period="6mo", interval="1d", auto_adjust=False)
            closes = hist["Close"].dropna() if not hist.empty else None
            vols = hist["Volume"].dropna() if not hist.empty else None

            ma20 = _safe_float(closes.tail(20).mean()) if closes is not None and len(closes) >= 20 else _safe_float(info.get("fiftyDayAverage"))
            ma50 = _safe_float(closes.tail(50).mean()) if closes is not None and len(closes) >= 50 else _safe_float(info.get("fiftyDayAverage"))
            high20 = _safe_float(closes.tail(20).max()) if closes is not None and len(closes) >= 20 else None
            high50 = _safe_float(closes.tail(50).max()) if closes is not None and len(closes) >= 50 else None
            ma20_prev = _safe_float(closes.tail(21).head(20).mean()) if closes is not None and len(closes) >= 21 else ma20
            ma20_slope = (ma20 - ma20_prev) if ma20 is not None and ma20_prev is not None else None

            recent_high = _safe_float(closes.max()) if closes is not None and len(closes) > 0 else None
            move_1d = None
            if closes is not None and len(closes) >= 2:
                prev = _safe_float(closes.iloc[-2])
                last = _safe_float(closes.iloc[-1])
                if prev and prev != 0:
                    move_1d = (last - prev) / prev

            avg_20_vol = _safe_float(vols.tail(20).mean()) if vols is not None and len(vols) >= 20 else _safe_float(info.get("averageVolume"))
            volume = _safe_float(info.get("volume"))
            volume_ratio = (volume / avg_20_vol) if volume is not None and avg_20_vol not in (None, 0) else None

            rs_ratio = None
            try:
                benchmark = yf.Ticker("SPY").history(period="6mo", interval="1d", auto_adjust=False)
                if not benchmark.empty and closes is not None and len(closes) >= 20 and len(benchmark["Close"].dropna()) >= 20:
                    stock_ret = (closes.iloc[-1] / closes.iloc[-20]) - 1
                    bench_series = benchmark["Close"].dropna()
                    bench_ret = (bench_series.iloc[-1] / bench_series.iloc[-20]) - 1
                    rs_ratio = float(stock_ret - bench_ret)
            except (KeyError, IndexError, ValueError, TypeError, requests_exceptions.RequestException) as exc:
                logger.warning("benchmark_fetch_failed ticker=%s error=%s", ticker_symbol, exc)
                rs_ratio = None

            days_to_earnings = _days_until_earnings(info, now)

            # Basic fields that the brains currently consume
            quote = {
                "ticker": ticker_symbol,
                "currentPrice": _safe_float(info.get("currentPrice")),
                "volume": volume,
                "averageVolume": _safe_float(info.get("averageVolume")),
                "trailingPE": info.get("trailingPE"),
                "dividendYield": info.get("dividendYield"),
                "fiftyDayAverage": info.get("fiftyDayAverage"),
                "twoHundredDayAverage": info.get("twoHundredDayAverage"),
                "revenueGrowth": _safe_float(info.get("revenueGrowth")),
                "pegRatio": _safe_float(info.get("pegRatio")),
                "recommendationKey": info.get("recommendationKey"),
                "recommendationMean": _safe_float(info.get("recommendationMean")),
                "targetMeanPrice": _safe_float(info.get("targetMeanPrice")),
                "targetMedianPrice": _safe_float(info.get("targetMedianPrice")),
                "numberOfAnalystOpinions": _safe_float(info.get("numberOfAnalystOpinions")),
                "sector": info.get("sector"),
                "ma20": ma20,
                "ma50": ma50,
                "ma20_slope": ma20_slope,
                "high20": high20,
                "high50": high50,
                "recent_high": recent_high,
                "move_1d": move_1d,
                "avg20_volume": avg_20_vol,
                "volume_ratio": volume_ratio,
                "relative_strength_vs_benchmark": rs_ratio,
                "earnings_days": days_to_earnings,
                "iv_rank": _estimate_iv_rank(ticker),
                "timestamp": now,
            }
            record_quote_fetch("success", time_mod.perf_counter() - start_ts)
            return quote
        except TRANSIENT_EXCEPTIONS as exc:
            error_text = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "quote_fetch_transient_error ticker=%s attempt=%s/%s error=%s",
                ticker_symbol,
                attempt,
                max_attempts,
                error_text,
            )
            if attempt < max_attempts:
                time_mod.sleep(0.4 * (2 ** (attempt - 1)))
            continue
        except (KeyError, ValueError, TypeError) as exc:
            error_text = f"{type(exc).__name__}: {exc}"
            logger.error("quote_fetch_failed ticker=%s error=%s", ticker_symbol, error_text)
            break
        except Exception as exc:
            error_text = f"{type(exc).__name__}: {exc}"
            logger.exception("quote_fetch_unexpected ticker=%s error=%s", ticker_symbol, error_text)
            break

    record_quote_fetch("failure", time_mod.perf_counter() - start_ts)
    return {
        "ticker": ticker_symbol,
        "error": f"Failed to fetch quote after {max_attempts} attempts: {error_text}",
        "currentPrice": None,
        "volume": None,
        "timestamp": datetime.now(timezone.utc),
    }
