from __future__ import annotations

import base64
import logging
import time

import httpx
from nacl.signing import SigningKey

from ..models import AlertEvent, OrderResult, OrderStatus, RiskDecision, Signal, TradeDecision
from .base import OrderAdapter, OrderAdapterError

logger = logging.getLogger(__name__)


class BackpackOrderAdapter(OrderAdapter):
    """Order Adapter for Backpack Exchange.

    Backpack authenticates signed requests with an ED25519 keypair: the
    request's params are alphabetically sorted, joined as a query string,
    prefixed with `instruction=<name>` and suffixed with
    `timestamp=...&window=...`, then signed. See
    https://docs.backpack.exchange/ for the authoritative spec -- verify
    field names/casing there before trading with real funds, since exchange
    APIs evolve.
    """

    name = "backpack"

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        api_url: str = "https://api.backpack.exchange",
        window_ms: int = 5000,
        max_retries: int = 3,
        base_delay_seconds: float = 2.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        super().__init__(max_retries=max_retries, base_delay_seconds=base_delay_seconds)
        self._api_key = api_key
        self._signing_key = SigningKey(base64.b64decode(api_secret))
        self._api_url = api_url.rstrip("/")
        self._window_ms = window_ms
        self._http = http_client or httpx.Client(timeout=10.0)

    def place_order(
        self, decision: TradeDecision, event: AlertEvent, risk: RiskDecision
    ) -> OrderResult:
        if decision.signal not in (Signal.LONG, Signal.SHORT):
            return OrderResult(
                status=OrderStatus.SKIPPED,
                exchange=self.name,
                symbol=event.symbol,
                error_message=f"non-actionable signal: {decision.signal.value}",
            )

        side = "Bid" if decision.signal == Signal.LONG else "Ask"
        quantity = risk.size_usd / event.current_price

        params = {
            "symbol": event.symbol,
            "side": side,
            "orderType": "Market",
            "quantity": f"{quantity:.6f}",
        }

        def _call():
            try:
                return self._signed_post("/api/v1/order", "orderExecute", params)
            except httpx.HTTPError as exc:
                raise OrderAdapterError(str(exc)) from exc

        try:
            response = self._call_with_retry(_call)
        except Exception as exc:
            logger.error("backpack order failed after retries: %s", exc)
            return OrderResult(
                status=OrderStatus.ERROR,
                exchange=self.name,
                symbol=event.symbol,
                side=side,
                size=quantity,
                error_message=str(exc),
            )

        order_id = response.get("id") if isinstance(response, dict) else None
        status = response.get("status") if isinstance(response, dict) else None
        if status in ("Filled", "New", "PartiallyFilled"):
            return OrderResult(
                status=OrderStatus.FILLED,
                exchange=self.name,
                symbol=event.symbol,
                side=side,
                size=quantity,
                price=event.current_price,
                order_id=str(order_id) if order_id else None,
                raw_response=response,
            )

        return OrderResult(
            status=OrderStatus.REJECTED,
            exchange=self.name,
            symbol=event.symbol,
            side=side,
            size=quantity,
            raw_response=response if isinstance(response, dict) else None,
            error_message=str(response),
        )

    def _signed_post(self, path: str, instruction: str, params: dict) -> dict:
        timestamp = int(time.time() * 1000)
        query_string = "&".join(f"{k}={v}" for k, v in sorted(params.items()))

        sign_payload = f"instruction={instruction}"
        if query_string:
            sign_payload += f"&{query_string}"
        sign_payload += f"&timestamp={timestamp}&window={self._window_ms}"

        signature = self._signing_key.sign(sign_payload.encode("utf-8")).signature
        signature_b64 = base64.b64encode(signature).decode("ascii")

        headers = {
            "X-API-Key": self._api_key,
            "X-Signature": signature_b64,
            "X-Timestamp": str(timestamp),
            "X-Window": str(self._window_ms),
            "Content-Type": "application/json; charset=utf-8",
        }

        resp = self._http.post(f"{self._api_url}{path}", json=params, headers=headers)
        resp.raise_for_status()
        return resp.json() if resp.content else {}
