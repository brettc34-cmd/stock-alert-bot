"""Persistent cooldown storage for interactive command rate limiting."""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import redis
except Exception:  # pragma: no cover - optional dependency
    redis = None


class RunCooldownStore:
    def __init__(self, redis_url: str | None = None, sqlite_path: str = "./storage/discord_cooldowns.db") -> None:
        self.redis_url = redis_url or os.environ.get("REDIS_URL")
        self.sqlite_path = sqlite_path
        self._redis = None

        if self.redis_url and redis is not None:
            try:
                self._redis = redis.from_url(self.redis_url, decode_responses=True)
                self._redis.ping()
                logger.info("run_cooldown_store backend=redis")
            except Exception as exc:
                logger.warning("run_cooldown_store redis_unavailable error=%s", exc)
                self._redis = None

        if self._redis is None:
            logger.info("run_cooldown_store backend=sqlite path=%s", self.sqlite_path)
            self._init_sqlite()

    def _init_sqlite(self) -> None:
        Path(self.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.sqlite_path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS run_cooldowns (
                  scope_key TEXT PRIMARY KEY,
                  last_run_epoch REAL NOT NULL
                )
                """
            )
            conn.commit()

    def seconds_remaining(self, scope_key: str, cooldown_seconds: int) -> int:
        now = time.time()
        last = self._get_last(scope_key)
        if last <= 0:
            return 0
        remaining = cooldown_seconds - (now - last)
        return int(remaining) if remaining > 0 else 0

    def mark_run(self, scope_key: str, now_epoch: float | None = None) -> None:
        ts = now_epoch or time.time()
        if self._redis is not None:
            key = self._redis_key(scope_key)
            self._redis.set(key, str(ts))
            return

        with sqlite3.connect(self.sqlite_path) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO run_cooldowns(scope_key, last_run_epoch) VALUES (?, ?)",
                (scope_key, ts),
            )
            conn.commit()

    def _get_last(self, scope_key: str) -> float:
        if self._redis is not None:
            raw = self._redis.get(self._redis_key(scope_key))
            try:
                return float(raw) if raw is not None else 0.0
            except ValueError:
                return 0.0

        with sqlite3.connect(self.sqlite_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT last_run_epoch FROM run_cooldowns WHERE scope_key = ?", (scope_key,))
            row = cur.fetchone()
            return float(row[0]) if row else 0.0

    @staticmethod
    def _redis_key(scope_key: str) -> str:
        return f"stock_alert:run_cooldown:{scope_key}"
