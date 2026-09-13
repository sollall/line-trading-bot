from datetime import datetime, timezone

from line_trading_bot.models import (
    AlertEvent,
    LineType,
    OrderResult,
    OrderStatus,
    RawSource,
    Signal,
    TradeDecision,
)
from line_trading_bot.storage import Storage


def make_event(event_id="evt-1") -> AlertEvent:
    return AlertEvent(
        event_id=event_id,
        symbol="BPUSDT",
        line_price=100.0,
        current_price=101.0,
        line_type=LineType.RESISTANCE,
        raw_source=RawSource.EMAIL,
        received_at=datetime.now(timezone.utc),
    )


def test_event_dedup(tmp_path):
    storage = Storage(str(tmp_path / "test.db"))
    event = make_event()

    assert storage.event_exists(event.event_id) is False
    storage.save_alert_event(event)
    assert storage.event_exists(event.event_id) is True

    # Saving again must not raise or duplicate (idempotency, spec 5).
    storage.save_alert_event(event)


def test_save_and_persist_decision_and_order(tmp_path):
    storage = Storage(str(tmp_path / "test.db"))
    event = make_event()
    storage.save_alert_event(event)

    decision = TradeDecision(signal=Signal.LONG, confidence=0.8, reason="r", line_basis="lb")
    storage.save_trade_decision(event.event_id, decision)

    result = OrderResult(
        status=OrderStatus.FILLED,
        exchange="backpack",
        symbol=event.symbol,
        side="Bid",
        size=1.0,
        price=101.0,
        order_id="123",
        raw_response={"ok": True},
    )
    storage.save_order_result(event.event_id, result)  # should not raise


def test_storage_creates_parent_dir(tmp_path):
    db_path = tmp_path / "nested" / "dir" / "test.db"
    Storage(str(db_path))
    assert db_path.exists()
