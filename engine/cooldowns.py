"""Cooldowns manager.

Simple in-memory cooldown manager that uses the `state` dict to persist
last-sent timestamps for cooldown keys. `state` is the same dict loaded from
`state.json` by `bot.py` so changes will be saved back at the end of the run.
"""
from time import time
from typing import Dict, Any


def is_on_cooldown(state: Dict[str, Any], cooldown_key: str, cooldown_seconds: int) -> bool:
    last = state.setdefault("cooldowns", {}).get(cooldown_key)
    if last is None:
        return False
    return (time() - last) < cooldown_seconds


def mark_sent(state: Dict[str, Any], cooldown_key: str) -> None:
    state.setdefault("cooldowns", {})[cooldown_key] = time()


__all__ = ["is_on_cooldown", "mark_sent"]
