from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple


@dataclass
class Headline:
    source: str
    title: str
    link: str = ""
    summary: str = ""
    published_at: Optional[datetime] = None


@dataclass
class SP500Snapshot:
    as_of: Optional[datetime]
    sp500_level: Optional[float]
    sp500_daily_change_pct: Optional[float]
    sp500_ytd_change_pct: Optional[float]
    treasury_10y_yield_pct: Optional[float]
    treasury_10y_change_pct: Optional[float]
    vix_level: Optional[float]
    vix_change_pct: Optional[float]
    wti_change_pct: Optional[float]
    fed_funds_rate: Optional[float]
    fed_funds_as_of: str = ""
    strongest_sectors: List[Tuple[str, float]] = field(default_factory=list)
    weakest_sectors: List[Tuple[str, float]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class SP500OverviewMessage:
    subject: str
    body: str
    timestamp_label: str
    word_count: int
    warnings: List[str] = field(default_factory=list)


@dataclass
class DeliveryResult:
    subject: str
    body: str
    timestamp_label: str
    delivery_method: str
    destination: str
    sent: bool
    warnings: List[str] = field(default_factory=list)