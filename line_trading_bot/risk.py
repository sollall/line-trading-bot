"""RiskManager: sits between the Judgment Engine and the Order Adapter layer
(spec 3.3) so position sizing / leverage rules stay in one place regardless
of which exchange ends up receiving the order.

Position sizing beyond a flat per-trade cap is explicitly listed as an open
question in spec section 6, so this starts with the simplest safe rule (a
fixed max notional + max leverage per trade) and is the single place to
extend later (per-symbol allocation, daily loss limits, etc.) without
touching any Order Adapter.
"""
from __future__ import annotations

import logging

from .models import AlertEvent, RiskDecision, Signal, TradeDecision

logger = logging.getLogger(__name__)


class RiskManager:
    def __init__(self, max_position_size_usd: float, max_leverage: float) -> None:
        if max_position_size_usd <= 0:
            raise ValueError("max_position_size_usd must be positive")
        if max_leverage <= 0:
            raise ValueError("max_leverage must be positive")
        self._max_position_size_usd = max_position_size_usd
        self._max_leverage = max_leverage

    def evaluate(self, decision: TradeDecision, event: AlertEvent) -> RiskDecision:
        if decision.signal == Signal.WAIT:
            return RiskDecision(approved=False, reason="signal is wait")

        if event.current_price <= 0:
            return RiskDecision(approved=False, reason="invalid current_price")

        risk_decision = RiskDecision(
            approved=True,
            size_usd=self._max_position_size_usd,
            leverage=self._max_leverage,
            reason="within configured per-trade risk limits",
        )
        logger.info(
            "risk approved: %s %s size_usd=%.2f leverage=%.1f",
            decision.signal.value,
            event.symbol,
            risk_decision.size_usd,
            risk_decision.leverage,
        )
        return risk_decision
