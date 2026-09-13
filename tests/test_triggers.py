import pytest

from line_trading_bot.models import LineType, RawSource
from line_trading_bot.triggers import EmailTriggerAdapter, WebhookTriggerAdapter, get_trigger_adapter
from line_trading_bot.triggers.base import TriggerParseError


class TestEmailTriggerAdapter:
    def setup_method(self):
        self.adapter = EmailTriggerAdapter()

    def test_parses_well_formed_body(self):
        payload = {
            "subject": "TradingView Alert",
            "text": (
                "SYMBOL=BPUSDT\n"
                "LINE_PRICE=65000\n"
                "CURRENT_PRICE=65120.5\n"
                "LINE_TYPE=resistance\n"
                "CHART_URL=https://example.com/chart.png\n"
            ),
        }
        event = self.adapter.parse(payload)

        assert event.symbol == "BPUSDT"
        assert event.line_price == 65000
        assert event.current_price == 65120.5
        assert event.line_type == LineType.RESISTANCE
        assert event.chart_image_url == "https://example.com/chart.png"
        assert event.raw_source == RawSource.EMAIL
        assert event.event_id

    def test_same_body_yields_same_event_id(self):
        payload = {"text": "SYMBOL=BPUSDT\nLINE_PRICE=1\nCURRENT_PRICE=2\n"}
        event1 = self.adapter.parse(payload)
        event2 = self.adapter.parse(payload)
        assert event1.event_id == event2.event_id

    def test_missing_required_field_raises(self):
        payload = {"text": "SYMBOL=BPUSDT\nLINE_PRICE=1\n"}  # missing current_price
        with pytest.raises(TriggerParseError):
            self.adapter.parse(payload)

    def test_unparseable_price_raises(self):
        payload = {"text": "SYMBOL=BPUSDT\nLINE_PRICE=abc\nCURRENT_PRICE=2\n"}
        with pytest.raises(TriggerParseError):
            self.adapter.parse(payload)

    def test_empty_body_raises(self):
        with pytest.raises(TriggerParseError):
            self.adapter.parse({"text": ""})

    def test_unknown_line_type_defaults_to_unknown(self):
        payload = {"text": "SYMBOL=X\nLINE_PRICE=1\nCURRENT_PRICE=2\nLINE_TYPE=garbage\n"}
        event = self.adapter.parse(payload)
        assert event.line_type == LineType.UNKNOWN

    def test_non_dict_input_raises(self):
        with pytest.raises(TriggerParseError):
            self.adapter.parse("not a dict")


class TestWebhookTriggerAdapter:
    def setup_method(self):
        self.adapter = WebhookTriggerAdapter()

    def test_parses_well_formed_json(self):
        payload = {
            "symbol": "hypeusd",
            "line_price": 10.5,
            "current_price": 10.6,
            "line_type": "support",
            "chart_image_url": "https://example.com/c.png",
        }
        event = self.adapter.parse(payload)

        assert event.symbol == "HYPEUSD"
        assert event.line_type == LineType.SUPPORT
        assert event.raw_source == RawSource.WEBHOOK

    def test_missing_field_raises(self):
        with pytest.raises(TriggerParseError):
            self.adapter.parse({"symbol": "X", "line_price": 1})

    def test_defaults_line_type_unknown(self):
        payload = {"symbol": "X", "line_price": 1, "current_price": 2}
        event = self.adapter.parse(payload)
        assert event.line_type == LineType.UNKNOWN


def test_get_trigger_adapter_factory():
    assert isinstance(get_trigger_adapter("email"), EmailTriggerAdapter)
    assert isinstance(get_trigger_adapter("webhook"), WebhookTriggerAdapter)
    with pytest.raises(ValueError):
        get_trigger_adapter("carrier_pigeon")
