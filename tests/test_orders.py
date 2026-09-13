import base64
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import httpx
import nacl.signing
import pytest

from line_trading_bot.models import (
    AlertEvent,
    LineType,
    OrderResult,
    OrderStatus,
    RawSource,
    RiskDecision,
    Signal,
    TradeDecision,
)
from line_trading_bot.orders.backpack_adapter import BackpackOrderAdapter
from line_trading_bot.orders.base import OrderAdapter, OrderAdapterError
from line_trading_bot.orders.router import OrderRouter


def make_event(**overrides) -> AlertEvent:
    defaults = dict(
        event_id="evt-1",
        symbol="BPUSDT",
        line_price=100.0,
        current_price=100.0,
        line_type=LineType.RESISTANCE,
        raw_source=RawSource.EMAIL,
        received_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return AlertEvent(**defaults)


class _FlakyAdapter(OrderAdapter):
    name = "flaky"

    def __init__(self, fail_times: int, **kwargs):
        super().__init__(**kwargs)
        self.fail_times = fail_times
        self.attempts = 0

    def _do_call(self):
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise OrderAdapterError("transient failure")
        return "success"

    def place_order(self, decision, event, risk):
        return self._call_with_retry(self._do_call)


class TestRetry:
    def test_succeeds_after_transient_failures(self):
        adapter = _FlakyAdapter(fail_times=2, max_retries=3, base_delay_seconds=0.001)
        result = adapter.place_order(None, None, None)
        assert result == "success"
        assert adapter.attempts == 3

    def test_raises_after_exhausting_retries(self):
        adapter = _FlakyAdapter(fail_times=10, max_retries=2, base_delay_seconds=0.001)
        with pytest.raises(OrderAdapterError):
            adapter.place_order(None, None, None)
        assert adapter.attempts == 3  # 1 initial + 2 retries


class TestOrderRouter:
    def test_routes_symbol_to_correct_adapter(self):
        hl = MagicMock()
        bp = MagicMock()
        router = OrderRouter(
            adapters_by_exchange={"hyperliquid": hl, "backpack": bp},
            symbol_to_exchange={"HYPEUSD": "hyperliquid", "BPUSDT": "backpack"},
        )
        assert router.get_adapter("HYPEUSD") is hl
        assert router.get_adapter("BPUSDT") is bp

    def test_unmapped_symbol_returns_none(self):
        router = OrderRouter(adapters_by_exchange={}, symbol_to_exchange={})
        assert router.get_adapter("UNKNOWN") is None


class TestBackpackOrderAdapter:
    def _make_adapter(self, http_client=None, secret_key: nacl.signing.SigningKey | None = None):
        secret_key = secret_key or nacl.signing.SigningKey.generate()
        api_secret_b64 = base64.b64encode(bytes(secret_key)).decode()
        return BackpackOrderAdapter(
            api_key="test-api-key",
            api_secret=api_secret_b64,
            api_url="https://backpack.test",
            max_retries=1,
            base_delay_seconds=0.001,
            http_client=http_client,
        ), secret_key

    def test_wait_signal_is_skipped_without_http_call(self):
        adapter, _ = self._make_adapter()
        decision = TradeDecision(signal=Signal.WAIT, confidence=0.9, reason="r", line_basis="lb")
        risk = RiskDecision(approved=False, reason="wait")

        result = adapter.place_order(decision, make_event(), risk)

        assert result.status == OrderStatus.SKIPPED

    def test_signature_is_valid_and_order_filled(self):
        verify_key_holder = nacl.signing.SigningKey.generate()

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["X-API-Key"] == "test-api-key"
            timestamp = request.headers["X-Timestamp"]
            window = request.headers["X-Window"]
            signature = base64.b64decode(request.headers["X-Signature"])

            body = request.read()
            import json

            params = json.loads(body)
            query_string = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
            expected_payload = f"instruction=orderExecute&{query_string}&timestamp={timestamp}&window={window}"

            verify_key_holder.verify_key.verify(expected_payload.encode(), signature)
            return httpx.Response(200, json={"id": "abc123", "status": "Filled"})

        http_client = httpx.Client(transport=httpx.MockTransport(handler))
        adapter, _ = self._make_adapter(http_client=http_client, secret_key=verify_key_holder)

        decision = TradeDecision(signal=Signal.LONG, confidence=0.9, reason="r", line_basis="lb")
        risk = RiskDecision(approved=True, size_usd=100.0, leverage=1.0, reason="ok")

        result = adapter.place_order(decision, make_event(current_price=100.0), risk)

        assert result.status == OrderStatus.FILLED
        assert result.order_id == "abc123"
        assert result.side == "Bid"

    def test_http_failure_retried_then_returns_error(self):
        calls = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            return httpx.Response(500, text="server error")

        http_client = httpx.Client(transport=httpx.MockTransport(handler))
        adapter, _ = self._make_adapter(http_client=http_client)
        adapter._max_retries = 1

        decision = TradeDecision(signal=Signal.SHORT, confidence=0.9, reason="r", line_basis="lb")
        risk = RiskDecision(approved=True, size_usd=100.0, leverage=1.0, reason="ok")

        result = adapter.place_order(decision, make_event(), risk)

        assert result.status == OrderStatus.ERROR
        assert calls["count"] == 2  # 1 initial + 1 retry
