"""Wires Trigger Adapter -> Judgment Engine -> Risk Manager -> Order Adapter
-> Storage -> Notify together (spec section 2/5).

This is the only module that knows about all the layers at once; every
other module only knows the normalized types it consumes/produces
(AlertEvent / TradeDecision / RiskDecision / OrderResult), which is what
keeps the layers swappable.
"""
from __future__ import annotations

import logging
from typing import Any

from .models import OrderStatus
from .notify import LineNotifier
from .orders.router import OrderRouter
from .risk import RiskManager
from .storage import Storage
from .triggers.base import TriggerAdapter, TriggerParseError

logger = logging.getLogger(__name__)


class JudgmentEngineProtocol:
    def judge(self, event):  # pragma: no cover - structural typing only
        ...


class TradingPipeline:
    def __init__(
        self,
        trigger_adapter: TriggerAdapter,
        judgment_engine: JudgmentEngineProtocol,
        risk_manager: RiskManager,
        order_router: OrderRouter,
        storage: Storage,
        notifier: LineNotifier,
    ) -> None:
        self._trigger_adapter = trigger_adapter
        self._judgment_engine = judgment_engine
        self._risk_manager = risk_manager
        self._order_router = order_router
        self._storage = storage
        self._notifier = notifier

    def handle(self, raw_input: Any) -> None:
        try:
            event = self._trigger_adapter.parse(raw_input)
        except TriggerParseError as exc:
            # Availability requirement (spec 5): a parse failure never
            # reaches the Judgment Engine, it's just logged and dropped.
            logger.error("trigger parse failed, dropping input: %s", exc)
            return

        if self._storage.event_exists(event.event_id):
            logger.info("duplicate event_id=%s, skipping (idempotency)", event.event_id)
            return
        self._storage.save_alert_event(event)

        try:
            decision = self._judgment_engine.judge(event)
        except Exception as exc:  # noqa: BLE001 - never let a judgment failure crash the pipeline
            logger.error("judgment engine failed for event_id=%s: %s", event.event_id, exc)
            self._notifier.notify_failure(event, f"judgment engine error: {exc}")
            return

        self._storage.save_trade_decision(event.event_id, decision)
        self._notifier.notify_decision(event, decision)
        logger.info(
            "event_id=%s symbol=%s signal=%s confidence=%.2f line_basis=%s",
            event.event_id,
            event.symbol,
            decision.signal.value,
            decision.confidence,
            decision.line_basis,
        )

        risk_decision = self._risk_manager.evaluate(decision, event)
        if not risk_decision.approved:
            logger.info("event_id=%s not approved by risk manager: %s", event.event_id, risk_decision.reason)
            return

        adapter = self._order_router.get_adapter(event.symbol)
        if adapter is None:
            message = f"no order adapter configured for symbol {event.symbol}"
            logger.error("event_id=%s %s", event.event_id, message)
            self._notifier.notify_failure(event, message)
            return

        result = adapter.place_order(decision, event, risk_decision)
        self._storage.save_order_result(event.event_id, result)
        self._notifier.notify_order_result(event, result)

        if result.status == OrderStatus.ERROR:
            self._notifier.notify_failure(event, result.error_message or "unknown order error")
