from __future__ import annotations

import logging

from eth_account import Account
from hyperliquid.exchange import Exchange

from ..models import AlertEvent, OrderResult, OrderStatus, RiskDecision, Signal, TradeDecision
from .base import OrderAdapter, OrderAdapterError

logger = logging.getLogger(__name__)


class HyperliquidOrderAdapter(OrderAdapter):
    """Order Adapter for Hyperliquid, built on the official
    hyperliquid-python-sdk (handles the exchange's EIP-712 request signing).
    """

    name = "hyperliquid"

    def __init__(
        self,
        wallet_address: str,
        private_key: str,
        api_url: str,
        max_retries: int = 3,
        base_delay_seconds: float = 2.0,
    ) -> None:
        super().__init__(max_retries=max_retries, base_delay_seconds=base_delay_seconds)
        account = Account.from_key(private_key)
        self._exchange = Exchange(account, api_url, account_address=wallet_address)

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

        is_buy = decision.signal == Signal.LONG
        side = "buy" if is_buy else "sell"
        size = risk.size_usd / event.current_price

        def _call():
            try:
                self._exchange.update_leverage(max(1, int(risk.leverage)), event.symbol)
                return self._exchange.market_open(event.symbol, is_buy, size)
            except Exception as exc:  # noqa: BLE001 - re-raised for retry classification
                raise OrderAdapterError(str(exc)) from exc

        try:
            response = self._call_with_retry(_call)
        except Exception as exc:
            logger.error("hyperliquid order failed after retries: %s", exc)
            return OrderResult(
                status=OrderStatus.ERROR,
                exchange=self.name,
                symbol=event.symbol,
                side=side,
                size=size,
                error_message=str(exc),
            )

        if not isinstance(response, dict) or response.get("status") != "ok":
            return OrderResult(
                status=OrderStatus.REJECTED,
                exchange=self.name,
                symbol=event.symbol,
                side=side,
                size=size,
                raw_response=response if isinstance(response, dict) else None,
                error_message=str(response),
            )

        return OrderResult(
            status=OrderStatus.FILLED,
            exchange=self.name,
            symbol=event.symbol,
            side=side,
            size=size,
            price=event.current_price,
            order_id=self._extract_order_id(response),
            raw_response=response,
        )

    @staticmethod
    def _extract_order_id(response: dict) -> str | None:
        try:
            statuses = response["response"]["data"]["statuses"]
            for status in statuses:
                if "resting" in status:
                    return str(status["resting"]["oid"])
                if "filled" in status:
                    return str(status["filled"]["oid"])
        except (KeyError, TypeError, IndexError):
            pass
        return None
