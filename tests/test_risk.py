from datetime import datetime, timezone

import pytest

from line_trading_bot.models import AlertEvent, LineType, RawSource, Signal, TradeDecision
from line_trading_bot.risk import RiskManager


def make_event(current_price=100.0) -> AlertEvent:
    return AlertEvent(
        event_id="evt-1",
        symbol="BPUSDT",
        line_price=100.0,
        current_price=current_price,
        line_type=LineType.RESISTANCE,
        raw_source=RawSource.EMAIL,
        received_at=datetime.now(timezone.utc),
    )


def test_wait_signal_not_approved():
    manager = RiskManager(max_position_size_usd=100, max_leverage=3)
    decision = TradeDecision(signal=Signal.WAIT, confidence=0.9, reason="r", line_basis="lb")

    result = manager.evaluate(decision, make_event())

    assert result.approved is False


def test_long_signal_approved_within_caps():
    manager = RiskManager(max_position_size_usd=100, max_leverage=3)
    decision = TradeDecision(signal=Signal.LONG, confidence=0.9, reason="r", line_basis="lb")

    result = manager.evaluate(decision, make_event())

    assert result.approved is True
    assert result.size_usd == 100
    assert result.leverage == 3


def test_invalid_price_not_approved():
    manager = RiskManager(max_position_size_usd=100, max_leverage=3)
    decision = TradeDecision(signal=Signal.SHORT, confidence=0.9, reason="r", line_basis="lb")

    result = manager.evaluate(decision, make_event(current_price=0))

    assert result.approved is False


def test_constructor_rejects_invalid_config():
    with pytest.raises(ValueError):
        RiskManager(max_position_size_usd=0, max_leverage=3)
    with pytest.raises(ValueError):
        RiskManager(max_position_size_usd=100, max_leverage=0)
