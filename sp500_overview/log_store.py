"""Append-only local logging for S&P 500 overview sends."""

from __future__ import annotations

import json
from pathlib import Path

from sp500_overview.models import DeliveryResult


class MessageLogStore:
    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def append(self, result: DeliveryResult) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp_label": result.timestamp_label,
            "delivery_method": result.delivery_method,
            "destination": result.destination,
            "sent": result.sent,
            "subject": result.subject,
            "body": result.body,
            "warnings": result.warnings,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")