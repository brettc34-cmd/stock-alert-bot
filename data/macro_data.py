"""Macro and market regime data fetch helpers.

All fields are best-effort. Missing values should not break the run cycle.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

import yfinance as yf


_SECTOR_ETFS = {
    "Technology": "XLK",
    "Financial Services": "XLF",
    "Healthcare": "XLV",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Utilities": "XLU",
    "Basic Materials": "XLB",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
}


def _safe_close_change(symbol: str, period: str = "6mo") -> Dict[str, Optional[float]]:
    out: Dict[str, Optional[float]] = {"change_1d": None, "return_20d": None, "price": None, "ma200": None}
    try:
        hist = yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=False)
        if hist.empty:
            return out
        closes = hist["Close"].dropna()
        if len(closes) < 2:
            return out
        last = float(closes.iloc[-1])
        prev = float(closes.iloc[-2])
        out["price"] = last
        if prev:
            out["change_1d"] = (last - prev) / prev
        if len(closes) >= 20 and float(closes.iloc[-20]) != 0.0:
            out["return_20d"] = (last / float(closes.iloc[-20])) - 1.0
        if len(closes) >= 200:
            out["ma200"] = float(closes.tail(200).mean())
        return out
    except Exception:
        return out


def fetch_macro_snapshot() -> Dict[str, Any]:
    """Return macro context used for regime and risk overlays."""
    spx = _safe_close_change("^GSPC", period="2y")
    vix = _safe_close_change("^VIX", period="6mo")
    tnx = _safe_close_change("^TNX", period="1y")
    irx = _safe_close_change("^IRX", period="1y")
    hyg = _safe_close_change("HYG", period="1y")
    lqd = _safe_close_change("LQD", period="1y")
    dxy = _safe_close_change("DX-Y.NYB", period="1y")

    sector_returns_20d: Dict[str, float] = {}
    for sector_name, etf in _SECTOR_ETFS.items():
        data = _safe_close_change(etf, period="1y")
        ret_20 = data.get("return_20d")
        if isinstance(ret_20, float):
            sector_returns_20d[sector_name] = ret_20

    vix_level = vix.get("price")
    spx_price = spx.get("price")
    spx_ma200 = spx.get("ma200")
    tnx_yield = (tnx.get("price") or 0.0) / 100.0 if isinstance(tnx.get("price"), float) else None
    irx_yield = (irx.get("price") or 0.0) / 100.0 if isinstance(irx.get("price"), float) else None

    curve_slope_10y_3m = None
    if isinstance(tnx_yield, float) and isinstance(irx_yield, float):
        curve_slope_10y_3m = tnx_yield - irx_yield

    credit_risk_proxy_20d = None
    if isinstance(hyg.get("return_20d"), float) and isinstance(lqd.get("return_20d"), float):
        credit_risk_proxy_20d = float(hyg["return_20d"] - lqd["return_20d"])

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "spx_change_1d": spx.get("change_1d"),
        "spx_return_20d": spx.get("return_20d"),
        "spx_price": spx_price,
        "spx_ma200": spx_ma200,
        "vix": vix_level,
        "yield_10y": tnx_yield,
        "yield_3m": irx_yield,
        "yield_curve_10y_3m": curve_slope_10y_3m,
        "credit_risk_proxy_20d": credit_risk_proxy_20d,
        "dxy_return_20d": dxy.get("return_20d"),
        "sector_returns_20d": sector_returns_20d,
    }
