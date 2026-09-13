"""FastAPI entrypoint.

A single /webhook endpoint receives raw input for whichever TriggerAdapter
is active (spec 3.1); switching from email to a future TradingView Webhook
trigger is a TRIGGER_MODE config change, not a code/endpoint change.
"""
from __future__ import annotations

import logging

from fastapi import BackgroundTasks, FastAPI, Request

from .config import get_settings
from .container import build_pipeline
from .logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="line-trading-bot")

_settings = get_settings()
_pipeline = build_pipeline(_settings)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "trigger_mode": _settings.trigger_mode}


@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks) -> dict:
    payload = await request.json()
    # Ack immediately; TradingView/Cloudflare Email Workers expect a fast
    # response and the pipeline itself does blocking LLM/exchange calls.
    background_tasks.add_task(_pipeline.handle, payload)
    return {"status": "accepted"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
