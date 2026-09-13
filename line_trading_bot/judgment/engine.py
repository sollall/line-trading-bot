"""LLM-backed judge: AlertEvent -> TradeDecision (spec 3.2)."""
from __future__ import annotations

import base64
import logging

import httpx
from anthropic import Anthropic

from ..models import AlertEvent, Signal, TradeDecision

logger = logging.getLogger(__name__)

_DECISION_TOOL = {
    "name": "record_trade_decision",
    "description": (
        "Record the trading decision for this trendline-touch alert. "
        "Always call this tool exactly once with your final judgment."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "signal": {
                "type": "string",
                "enum": ["long", "short", "wait"],
                "description": "Trade direction, or 'wait' to skip this alert.",
            },
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Calibrated confidence in this signal, 0.0-1.0.",
            },
            "reason": {
                "type": "string",
                "description": "Concise rationale for the decision.",
            },
            "line_basis": {
                "type": "string",
                "description": (
                    "Which trendline this decision is based on (support/"
                    "resistance, approximate price/slope). If multiple "
                    "trendlines intersect near the current price, state "
                    "explicitly which one was used and why."
                ),
            },
        },
        "required": ["signal", "confidence", "reason", "line_basis"],
    },
}

_SYSTEM_PROMPT = (
    "You are a disciplined technical analyst judging a single trendline-touch "
    "alert for a leveraged crypto futures position. You will be given the "
    "line price, the current price, the line type (support/resistance/"
    "unknown), and optionally a chart image. Decide whether to go long, "
    "short, or wait.\n\n"
    "Rules:\n"
    "- Be conservative: prefer 'wait' when the setup is ambiguous or the "
    "price action does not clearly respect the line.\n"
    "- confidence must be honest and calibrated, not inflated.\n"
    "- If the chart shows multiple trendlines crossing near the current "
    "price, you MUST state in line_basis exactly which line you used and "
    "why you picked it over the others.\n"
    "- Always call the record_trade_decision tool exactly once with your "
    "final answer."
)


class JudgmentEngine:
    """The one place LLM prompting/parsing logic lives.

    The confidence threshold guard also lives here (not just in the prompt)
    so a miscalibrated or manipulated model response can't bypass it: any
    decision under the configured threshold is forced to "wait" before it's
    returned to the caller (spec 3.2's "safety valve").
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        confidence_threshold: float,
        max_tokens: int = 1024,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._client = Anthropic(api_key=api_key)
        self._model = model
        self._confidence_threshold = confidence_threshold
        self._max_tokens = max_tokens
        self._http = http_client or httpx.Client(timeout=10.0)

    def judge(self, event: AlertEvent) -> TradeDecision:
        content: list[dict] = []

        if event.chart_image_url:
            image_block = self._fetch_image_block(event.chart_image_url)
            if image_block is not None:
                content.append(image_block)

        content.append({"type": "text", "text": self._build_text_prompt(event)})

        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=_SYSTEM_PROMPT,
            tools=[_DECISION_TOOL],
            tool_choice={"type": "tool", "name": "record_trade_decision"},
            messages=[{"role": "user", "content": content}],
        )

        decision = self._extract_decision(response)
        return self._apply_confidence_guard(decision)

    def _build_text_prompt(self, event: AlertEvent) -> str:
        return (
            f"symbol: {event.symbol}\n"
            f"line_price: {event.line_price}\n"
            f"current_price: {event.current_price}\n"
            f"line_type: {event.line_type.value}\n"
            f"chart_image_attached: {event.chart_image_url is not None}\n"
        )

    def _fetch_image_block(self, url: str) -> dict | None:
        try:
            resp = self._http.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("failed to fetch chart image %s: %s", url, exc)
            return None

        media_type = resp.headers.get("content-type", "image/png").split(";")[0]
        if media_type not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
            media_type = "image/png"
        data = base64.standard_b64encode(resp.content).decode("ascii")
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": data},
        }

    def _extract_decision(self, response) -> TradeDecision:
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == "record_trade_decision":
                return TradeDecision.model_validate(block.input)
        raise ValueError("Judgment Engine: model did not return a record_trade_decision tool call")

    def _apply_confidence_guard(self, decision: TradeDecision) -> TradeDecision:
        if decision.signal != Signal.WAIT and decision.confidence < self._confidence_threshold:
            logger.info(
                "confidence %.2f below threshold %.2f, forcing wait (was %s)",
                decision.confidence,
                self._confidence_threshold,
                decision.signal.value,
            )
            return decision.model_copy(
                update={
                    "signal": Signal.WAIT,
                    "reason": f"{decision.reason} [forced wait: confidence below threshold]",
                }
            )
        return decision
