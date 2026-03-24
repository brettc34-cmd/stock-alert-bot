from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional


@dataclass
class Signal:
    ticker: str
    signal_type: str
    brain: str
    direction: str
    confidence: int
    priority: str
    action_bias: str
    reason: str
    why_it_matters: str
    confirmations: List[str] = field(default_factory=list)
    suppressions: List[str] = field(default_factory=list)
    price: Optional[float] = None
    change_pct: Optional[float] = None
    volume_ratio: Optional[float] = None
    portfolio_weight: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    score_raw: int = 0
    cooldown_key: str = ""
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    portfolio_note: str = ""
    summary: str = ""
    urgency: str = "moderate"

    @property
    def category(self) -> str:
        # Backward compatibility with older code/tests.
        return self.signal_type

    @property
    def price_at_signal(self) -> Optional[float]:
        return self.price

    @price_at_signal.setter
    def price_at_signal(self, value: Optional[float]) -> None:
        self.price = value

    def __post_init__(self) -> None:
        # Normalize legacy fields from old constructors/callers.
        self.priority = (self.priority or self.urgency or "moderate").lower()
        self.signal_type = self.signal_type or self.metadata.get("category", "unknown")
        self.reason = self.reason or self.summary or ""
        self.why_it_matters = self.why_it_matters or self.reason or ""
        self.direction = (self.direction or "neutral").lower()
        if self.confidence is None:
            self.confidence = 0
        self.confidence = max(0, min(100, int(self.confidence)))
        if not self.cooldown_key:
            self.cooldown_key = f"{self.ticker}_{self.signal_type}_{self.brain}".lower()
        if self.evidence and not self.confirmations:
            self.confirmations = [e.get("type", "unknown") for e in self.evidence if isinstance(e, dict)]
        if not self.summary:
            self.summary = self.reason
        # Keep a title-cased urgency string for existing formatters.
        self.urgency = self.priority.title()


__all__ = ["Signal"]
