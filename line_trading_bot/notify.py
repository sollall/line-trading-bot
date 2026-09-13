"""LINE notification layer (spec 3.4): judgment results, order results, and
failure alerts after exhausted retries all go out through here.
"""
from __future__ import annotations

import logging

import httpx

from .models import AlertEvent, OrderResult, TradeDecision

logger = logging.getLogger(__name__)

_LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"


class LineNotifier:
    def __init__(
        self,
        channel_access_token: str,
        to_user_id: str,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._token = channel_access_token
        self._to = to_user_id
        self._http = http_client or httpx.Client(timeout=10.0)

    def notify_decision(self, event: AlertEvent, decision: TradeDecision) -> None:
        self._send(
            f"[判定] {event.symbol} {decision.signal.value.upper()} "
            f"(confidence={decision.confidence:.2f})\n"
            f"line: {event.line_type.value} {event.line_price} / current: {event.current_price}\n"
            f"reason: {decision.reason}\n"
            f"line_basis: {decision.line_basis}"
        )

    def notify_order_result(self, event: AlertEvent, result: OrderResult) -> None:
        self._send(
            f"[発注結果] {result.exchange} {event.symbol} {result.status.value}\n"
            f"side={result.side} size={result.size} price={result.price} order_id={result.order_id}"
            + (f"\nerror: {result.error_message}" if result.error_message else "")
        )

    def notify_failure(self, event: AlertEvent, message: str) -> None:
        self._send(f"[アラート] {event.symbol} 発注に失敗しました: {message}")

    def _send(self, text: str) -> None:
        if not self._token or not self._to:
            logger.info("LINE notification skipped (not configured): %s", text)
            return
        try:
            resp = self._http.post(
                _LINE_PUSH_URL,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                },
                json={"to": self._to, "messages": [{"type": "text", "text": text[:5000]}]},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            # Notification failures must never break the trading pipeline.
            logger.error("failed to send LINE notification: %s", exc)
