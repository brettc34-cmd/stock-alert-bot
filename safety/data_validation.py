"""Sanity checks for incoming market data."""

import os
from typing import Dict, Any


def validate_quote(quote: Dict[str, Any]) -> bool:
    """Return True if quote contains expected keys and non-null data."""
    required = ["ticker", "currentPrice", "volume", "timestamp"]
    for key in required:
        if quote.get(key) is None:
            return False
    if quote.get("currentPrice", 0) <= 0:
        return False
    if quote.get("volume", 0) < 0:
        return False
    return True


def validate_config(config: Dict[str, Any]) -> bool:
    if not isinstance(config.get("stocks"), list):
        return False
    if not os.environ.get("DISCORD_WEBHOOK_URL"):
        return False
    if not isinstance(config.get("ladder_step", 5), (int, float)):
        return False
    return True
