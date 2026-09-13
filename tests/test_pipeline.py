from datetime import datetime, timezone

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
from line_trading_bot.orders.router import OrderRouter
from line_trading_bot.pipeline import TradingPipeline
from line_trading_bot.risk import RiskManager
from line_trading_bot.storage import Storage
from line_trading_bot.triggers.base import TriggerAdapter, TriggerParseError


def make_event(event_id="evt-1", symbol="BPUSDT") -> AlertEvent:
    return AlertEvent(
        event_id=event_id,
        symbol=symbol,
        line_price=100.0,
        current_price=100.0,
        line_type=LineType.RESISTANCE,
        raw_source=RawSource.EMAIL,
        received_at=datetime.now(timezone.utc),
    )


class FakeTriggerAdapter(TriggerAdapter):
    def __init__(self, event=None, error=None):
        self.event = event
        self.error = error
        self.parse_calls = 0

    def parse(self, raw_input):
        self.parse_calls += 1
        if self.error:
            raise self.error
        return self.event


class FakeJudgmentEngine:
    def __init__(self, decision=None, error=None):
        self.decision = decision
        self.error = error
        self.judge_calls = 0

    def judge(self, event):
        self.judge_calls += 1
        if self.error:
            raise self.error
        return self.decision


class FakeOrderAdapter:
    name = "fake"

    def __init__(self, result=None):
        self.result = result
        self.place_order_calls = 0

    def place_order(self, decision, event, risk):
        self.place_order_calls += 1
        return self.result


class FakeNotifier:
    def __init__(self):
        self.decisions = []
        self.order_results = []
        self.failures = []

    def notify_decision(self, event, decision):
        self.decisions.append((event, decision))

    def notify_order_result(self, event, result):
        self.order_results.append((event, result))

    def notify_failure(self, event, message):
        self.failures.append((event, message))


def build_pipeline(tmp_path, trigger, judgment, order_adapter=None, symbol="BPUSDT"):
    risk_manager = RiskManager(max_position_size_usd=100, max_leverage=3)
    adapters = {"fake": order_adapter} if order_adapter else {}
    router = OrderRouter(adapters_by_exchange=adapters, symbol_to_exchange={symbol: "fake"} if order_adapter else {})
    storage = Storage(str(tmp_path / "test.db"))
    notifier = FakeNotifier()
    pipeline = TradingPipeline(trigger, judgment, risk_manager, router, storage, notifier)
    return pipeline, storage, notifier


def test_full_flow_filled_order(tmp_path):
    event = make_event()
    decision = TradeDecision(signal=Signal.LONG, confidence=0.9, reason="r", line_basis="lb")
    order_result = OrderResult(status=OrderStatus.FILLED, exchange="fake", symbol=event.symbol, order_id="1")

    trigger = FakeTriggerAdapter(event=event)
    judgment = FakeJudgmentEngine(decision=decision)
    adapter = FakeOrderAdapter(result=order_result)
    pipeline, storage, notifier = build_pipeline(tmp_path, trigger, judgment, adapter)

    pipeline.handle({"raw": "input"})

    assert storage.event_exists(event.event_id)
    assert adapter.place_order_calls == 1
    assert len(notifier.decisions) == 1
    assert len(notifier.order_results) == 1
    assert len(notifier.failures) == 0


def test_duplicate_event_is_skipped(tmp_path):
    event = make_event()
    decision = TradeDecision(signal=Signal.LONG, confidence=0.9, reason="r", line_basis="lb")
    order_result = OrderResult(status=OrderStatus.FILLED, exchange="fake", symbol=event.symbol)

    trigger = FakeTriggerAdapter(event=event)
    judgment = FakeJudgmentEngine(decision=decision)
    adapter = FakeOrderAdapter(result=order_result)
    pipeline, storage, notifier = build_pipeline(tmp_path, trigger, judgment, adapter)

    pipeline.handle({"raw": "input"})
    pipeline.handle({"raw": "input"})  # duplicate

    assert trigger.parse_calls == 2
    assert judgment.judge_calls == 1  # second call short-circuited before judgment
    assert adapter.place_order_calls == 1


def test_trigger_parse_failure_is_dropped_silently(tmp_path):
    trigger = FakeTriggerAdapter(error=TriggerParseError("bad input"))
    judgment = FakeJudgmentEngine()
    pipeline, storage, notifier = build_pipeline(tmp_path, trigger, judgment)

    pipeline.handle({"raw": "bad"})

    assert judgment.judge_calls == 0
    assert len(notifier.failures) == 0


def test_judgment_error_notifies_failure(tmp_path):
    event = make_event()
    trigger = FakeTriggerAdapter(event=event)
    judgment = FakeJudgmentEngine(error=RuntimeError("anthropic api down"))
    pipeline, storage, notifier = build_pipeline(tmp_path, trigger, judgment)

    pipeline.handle({"raw": "input"})

    assert len(notifier.failures) == 1
    assert storage.event_exists(event.event_id)


def test_wait_signal_never_places_order(tmp_path):
    event = make_event()
    decision = TradeDecision(signal=Signal.WAIT, confidence=0.9, reason="r", line_basis="lb")
    trigger = FakeTriggerAdapter(event=event)
    judgment = FakeJudgmentEngine(decision=decision)
    adapter = FakeOrderAdapter(result=None)
    pipeline, storage, notifier = build_pipeline(tmp_path, trigger, judgment, adapter)

    pipeline.handle({"raw": "input"})

    assert adapter.place_order_calls == 0
    assert len(notifier.order_results) == 0


def test_no_adapter_for_symbol_notifies_failure(tmp_path):
    event = make_event(symbol="UNMAPPED")
    decision = TradeDecision(signal=Signal.LONG, confidence=0.9, reason="r", line_basis="lb")
    trigger = FakeTriggerAdapter(event=event)
    judgment = FakeJudgmentEngine(decision=decision)
    pipeline, storage, notifier = build_pipeline(tmp_path, trigger, judgment, order_adapter=None)

    pipeline.handle({"raw": "input"})

    assert len(notifier.failures) == 1


def test_order_error_triggers_failure_notification(tmp_path):
    event = make_event()
    decision = TradeDecision(signal=Signal.SHORT, confidence=0.9, reason="r", line_basis="lb")
    order_result = OrderResult(
        status=OrderStatus.ERROR, exchange="fake", symbol=event.symbol, error_message="boom"
    )
    trigger = FakeTriggerAdapter(event=event)
    judgment = FakeJudgmentEngine(decision=decision)
    adapter = FakeOrderAdapter(result=order_result)
    pipeline, storage, notifier = build_pipeline(tmp_path, trigger, judgment, adapter)

    pipeline.handle({"raw": "input"})

    assert len(notifier.failures) == 1
    assert notifier.failures[0][1] == "boom"
