from .base import TriggerAdapter, TriggerParseError
from .email_adapter import EmailTriggerAdapter
from .webhook_adapter import WebhookTriggerAdapter

__all__ = [
    "TriggerAdapter",
    "TriggerParseError",
    "EmailTriggerAdapter",
    "WebhookTriggerAdapter",
    "get_trigger_adapter",
]


def get_trigger_adapter(mode: str) -> TriggerAdapter:
    """Factory: pick the active TriggerAdapter implementation from config.

    This is the single switch point mentioned in spec 3.1 — swapping from
    email to webhook triggers (or adding a new source later) never touches
    the Judgment Engine or anything downstream of it.
    """
    if mode == "email":
        return EmailTriggerAdapter()
    if mode == "webhook":
        return WebhookTriggerAdapter()
    raise ValueError(f"Unknown trigger_mode: {mode!r} (expected 'email' or 'webhook')")
