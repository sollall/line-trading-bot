import json
from datetime import datetime, timezone

from ..models import AlertEvent, LineType, RawSource
from .base import TriggerAdapter, TriggerParseError, compute_event_id

REQUIRED_FIELDS = ("symbol", "line_price", "current_price")


class WebhookTriggerAdapter(TriggerAdapter):
    """Parses a TradingView Webhook JSON payload (spec 3.1, future trigger).

    Expected shape (the TradingView alert message set to a JSON template
    with TradingView placeholders filled in):

        {
          "symbol": "BPUSDT",
          "line_price": 65000,
          "current_price": 65120,
          "line_type": "resistance",
          "chart_image_url": null
        }

    Swapping the active trigger from email to this adapter is a one-line
    config change (TRIGGER_MODE=webhook); nothing downstream changes because
    both adapters produce the same AlertEvent shape.
    """

    def parse(self, raw_input: dict) -> AlertEvent:
        if not isinstance(raw_input, dict):
            raise TriggerParseError(f"expected dict payload, got {type(raw_input)!r}")

        missing = [f for f in REQUIRED_FIELDS if raw_input.get(f) is None]
        if missing:
            raise TriggerParseError(f"webhook payload missing required fields: {missing}")

        try:
            line_price = float(raw_input["line_price"])
            current_price = float(raw_input["current_price"])
        except (TypeError, ValueError) as exc:
            raise TriggerParseError(f"could not parse price fields as float: {exc}") from exc

        line_type_raw = str(raw_input.get("line_type", "unknown")).lower()
        try:
            line_type = LineType(line_type_raw)
        except ValueError:
            line_type = LineType.UNKNOWN

        raw_bytes = json.dumps(raw_input, sort_keys=True, default=str).encode("utf-8")
        event_id = compute_event_id(RawSource.WEBHOOK.value, raw_bytes)

        return AlertEvent(
            event_id=event_id,
            symbol=str(raw_input["symbol"]).upper(),
            line_price=line_price,
            current_price=current_price,
            line_type=line_type,
            chart_image_url=raw_input.get("chart_image_url"),
            raw_source=RawSource.WEBHOOK,
            received_at=datetime.now(timezone.utc),
        )
