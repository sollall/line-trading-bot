"""Normalized data structures shared across all layers.

These are the contracts that keep Trigger Adapter / Judgment Engine / Order
Adapter decoupled from one another (see spec section 3). None of these types
should ever import from a concrete adapter module.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class LineType(str, Enum):
    SUPPORT = "support"
    RESISTANCE = "resistance"
    UNKNOWN = "unknown"


class RawSource(str, Enum):
    EMAIL = "email"
    WEBHOOK = "webhook"


class Signal(str, Enum):
    LONG = "long"
    SHORT = "short"
    WAIT = "wait"


class OrderStatus(str, Enum):
    FILLED = "filled"
    REJECTED = "rejected"
    ERROR = "error"
    SKIPPED = "skipped"


class AlertEvent(BaseModel):
    """Normalized trigger output. Every TriggerAdapter must produce this."""

    event_id: str
    symbol: str
    line_price: float
    current_price: float
    line_type: LineType = LineType.UNKNOWN
    chart_image_url: str | None = None
    raw_source: RawSource
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TradeDecision(BaseModel):
    """Normalized Judgment Engine output. Fixed JSON shape for downstream parsing."""

    signal: Signal
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    line_basis: str


class RiskDecision(BaseModel):
    """RiskManager verdict, sitting between TradeDecision and the Order Adapter."""

    approved: bool
    size_usd: float = 0.0
    leverage: float = 0.0
    reason: str


class OrderResult(BaseModel):
    status: OrderStatus
    exchange: str
    symbol: str
    side: str | None = None
    size: float | None = None
    price: float | None = None
    order_id: str | None = None
    raw_response: dict | None = None
    error_message: str | None = None
