from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class InstrumentQuote:
    key: str
    label: str
    symbol: str
    source: str
    price: Optional[float] = None
    change_pct: Optional[float] = None
    as_of: Optional[datetime] = None
    format_hint: str = "number"
    note: str = ""

    @property
    def is_available(self) -> bool:
        return self.price is not None


@dataclass
class Headline:
    source: str
    title: str
    link: str = ""
    published_at: Optional[datetime] = None
    summary: str = ""


@dataclass
class MarketUpdateResult:
    subject: str
    body: str
    timestamp_label: str
    warnings: List[str] = field(default_factory=list)