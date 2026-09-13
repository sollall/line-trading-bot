import hashlib
from abc import ABC, abstractmethod
from typing import Any

from ..models import AlertEvent


def compute_event_id(raw_source: str, raw_bytes: bytes) -> str:
    """Deterministic event id from the exact raw payload.

    Using a content hash (rather than a random uuid) is what makes the
    idempotency guarantee in spec 5 work: TradingView re-sending the same
    alert email/webhook (retries, duplicate delivery) yields the same
    event_id, so the pipeline's dedup check can recognize it.
    """
    digest = hashlib.sha256(raw_bytes).hexdigest()
    return f"{raw_source}:{digest}"


class TriggerParseError(Exception):
    """Raised when raw input cannot be turned into an AlertEvent.

    Per spec 5 (non-functional requirements), a parse failure must NOT reach
    the Judgment Engine — the caller is expected to catch this, log it, and
    drop the event to avoid an accidental order.
    """


class TriggerAdapter(ABC):
    @abstractmethod
    def parse(self, raw_input: Any) -> AlertEvent:
        """Convert adapter-specific raw input into a normalized AlertEvent."""
        raise NotImplementedError
