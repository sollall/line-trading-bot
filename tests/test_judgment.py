from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import httpx

from line_trading_bot.judgment.engine import JudgmentEngine
from line_trading_bot.models import AlertEvent, LineType, RawSource, Signal


def make_event(**overrides) -> AlertEvent:
    defaults = dict(
        event_id="evt-1",
        symbol="BPUSDT",
        line_price=100.0,
        current_price=101.0,
        line_type=LineType.RESISTANCE,
        chart_image_url=None,
        raw_source=RawSource.EMAIL,
        received_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return AlertEvent(**defaults)


class _FakeBlock:
    def __init__(self, type_, name=None, input=None):
        self.type = type_
        self.name = name
        self.input = input


class _FakeResponse:
    def __init__(self, content):
        self.content = content


def _fake_anthropic_client(tool_input: dict) -> MagicMock:
    client = MagicMock()
    client.messages.create.return_value = _FakeResponse(
        [_FakeBlock("tool_use", name="record_trade_decision", input=tool_input)]
    )
    return client


@patch("line_trading_bot.judgment.engine.Anthropic")
def test_judge_returns_decision_above_threshold(mock_anthropic_cls):
    mock_anthropic_cls.return_value = _fake_anthropic_client(
        {"signal": "long", "confidence": 0.9, "reason": "clean bounce", "line_basis": "resistance @ 100"}
    )
    engine = JudgmentEngine(api_key="x", model="claude-sonnet-5", confidence_threshold=0.6)

    decision = engine.judge(make_event())

    assert decision.signal == Signal.LONG
    assert decision.confidence == 0.9


@patch("line_trading_bot.judgment.engine.Anthropic")
def test_judge_forces_wait_below_confidence_threshold(mock_anthropic_cls):
    mock_anthropic_cls.return_value = _fake_anthropic_client(
        {"signal": "short", "confidence": 0.3, "reason": "unclear", "line_basis": "resistance @ 100"}
    )
    engine = JudgmentEngine(api_key="x", model="claude-sonnet-5", confidence_threshold=0.6)

    decision = engine.judge(make_event())

    assert decision.signal == Signal.WAIT
    assert "forced wait" in decision.reason


@patch("line_trading_bot.judgment.engine.Anthropic")
def test_judge_raises_when_tool_not_called(mock_anthropic_cls):
    client = MagicMock()
    client.messages.create.return_value = _FakeResponse([_FakeBlock("text")])
    mock_anthropic_cls.return_value = client
    engine = JudgmentEngine(api_key="x", model="claude-sonnet-5", confidence_threshold=0.6)

    try:
        engine.judge(make_event())
        assert False, "expected ValueError"
    except ValueError:
        pass


@patch("line_trading_bot.judgment.engine.Anthropic")
def test_judge_includes_image_block_when_fetch_succeeds(mock_anthropic_cls):
    mock_anthropic_cls.return_value = _fake_anthropic_client(
        {"signal": "wait", "confidence": 0.5, "reason": "n/a", "line_basis": "n/a"}
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"fake-png-bytes", headers={"content-type": "image/png"})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    engine = JudgmentEngine(
        api_key="x", model="claude-sonnet-5", confidence_threshold=0.6, http_client=http_client
    )

    engine.judge(make_event(chart_image_url="https://example.com/chart.png"))

    call_kwargs = mock_anthropic_cls.return_value.messages.create.call_args.kwargs
    content_blocks = call_kwargs["messages"][0]["content"]
    assert any(block["type"] == "image" for block in content_blocks)
