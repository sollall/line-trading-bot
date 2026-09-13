from __future__ import annotations

from .base import OrderAdapter


class OrderRouter:
    """Symbol -> exchange -> OrderAdapter mapping table (spec 3.3 / 4).

    Adding a new exchange or reassigning a symbol is purely a config /
    construction-time change here; the pipeline just calls get_adapter().
    """

    def __init__(
        self,
        adapters_by_exchange: dict[str, OrderAdapter],
        symbol_to_exchange: dict[str, str],
    ) -> None:
        self._adapters_by_exchange = adapters_by_exchange
        self._symbol_to_exchange = symbol_to_exchange

    def get_adapter(self, symbol: str) -> OrderAdapter | None:
        exchange = self._symbol_to_exchange.get(symbol)
        if exchange is None:
            return None
        return self._adapters_by_exchange.get(exchange)
