import re
from datetime import datetime, timezone

from ..models import AlertEvent, LineType, RawSource
from .base import TriggerAdapter, TriggerParseError, compute_event_id

_LINE_RE = re.compile(r"^\s*([A-Za-z_]+)\s*[:=]\s*(.+?)\s*$")


class EmailTriggerAdapter(TriggerAdapter):
    """Parses the JSON payload a Cloudflare Email Worker forwards to us.

    The worker receives the raw TradingView alert email, extracts the
    plain-text body, and POSTs something like:

        {"subject": "...", "text": "SYMBOL=BPUSDT\\nLINE_PRICE=65000\\n...",
         "from": "noreply@tradingview.com"}

    The email *body* itself is a template the user configures on the
    TradingView alert message (see README), formatted as KEY=VALUE lines:

        SYMBOL=BPUSDT
        LINE_PRICE=65000
        CURRENT_PRICE=65120
        LINE_TYPE=resistance
        CHART_URL=https://www.tradingview.com/x/abc123/

    Only symbol/line_price/current_price are required; line_type defaults to
    "unknown" and chart_url is optional (the Judgment Engine still works off
    the numeric line data when no chart image is available).
    """

    REQUIRED_FIELDS = ("symbol", "line_price", "current_price")

    def parse(self, raw_input: dict) -> AlertEvent:
        if not isinstance(raw_input, dict):
            raise TriggerParseError(f"expected dict payload, got {type(raw_input)!r}")

        body = raw_input.get("text") or raw_input.get("body") or ""
        if not body.strip():
            raise TriggerParseError("email payload has no text/body content")

        fields: dict[str, str] = {}
        for line in body.splitlines():
            match = _LINE_RE.match(line)
            if match:
                key, value = match.group(1).lower(), match.group(2)
                fields[key] = value

        missing = [f for f in self.REQUIRED_FIELDS if f not in fields]
        if missing:
            raise TriggerParseError(f"email body missing required fields: {missing}")

        try:
            line_price = float(fields["line_price"])
            current_price = float(fields["current_price"])
        except ValueError as exc:
            raise TriggerParseError(f"could not parse price fields as float: {exc}") from exc

        line_type_raw = fields.get("line_type", "unknown").lower()
        try:
            line_type = LineType(line_type_raw)
        except ValueError:
            line_type = LineType.UNKNOWN

        event_id = compute_event_id(RawSource.EMAIL.value, body.encode("utf-8"))

        return AlertEvent(
            event_id=event_id,
            symbol=fields["symbol"].upper(),
            line_price=line_price,
            current_price=current_price,
            line_type=line_type,
            chart_image_url=fields.get("chart_url") or None,
            raw_source=RawSource.EMAIL,
            received_at=datetime.now(timezone.utc),
        )
