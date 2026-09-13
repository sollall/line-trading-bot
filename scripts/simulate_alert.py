#!/usr/bin/env python3
"""Manually drive the pipeline with a sample alert, without running the
HTTP server or touching a real exchange -- useful for local testing.

Usage:
    python scripts/simulate_alert.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from line_trading_bot.config import get_settings
from line_trading_bot.container import build_pipeline

SAMPLE_EMAIL_PAYLOAD = {
    "subject": "TradingView Alert: BPUSDT line touch",
    "text": (
        "SYMBOL=BPUSDT\n"
        "LINE_PRICE=65000\n"
        "CURRENT_PRICE=65120\n"
        "LINE_TYPE=resistance\n"
    ),
}

if __name__ == "__main__":
    settings = get_settings()
    pipeline = build_pipeline(settings)
    pipeline.handle(SAMPLE_EMAIL_PAYLOAD)
    print("done - check logs / the sqlite DB at", settings.database_path)
