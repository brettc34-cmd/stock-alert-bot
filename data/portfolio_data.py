"""Portfolio data and helpers."""

import json
from pathlib import Path
from typing import Dict, Any, List


def load_portfolio(path: str = "config/portfolio.json") -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {"positions": [], "cash": 0}
    with open(p, "r") as f:
        return json.load(f)


def get_position(portfolio: Dict[str, Any], ticker: str) -> Dict[str, Any]:
    for pos in portfolio.get("positions", []):
        if pos.get("ticker") == ticker:
            return pos
    return {}


def total_value(portfolio: Dict[str, Any], prices: Dict[str, float]) -> float:
    total = portfolio.get("cash", 0.0)
    for pos in portfolio.get("positions", []):
        t = pos.get("ticker")
        shares = pos.get("shares", 0)
        price = prices.get(t)
        if price is not None:
            total += shares * price
    return total
