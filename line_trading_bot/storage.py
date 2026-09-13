"""Persistence + idempotency (spec 3.4 / 5).

Every AlertEvent / TradeDecision / OrderResult is persisted so the "why did
it trade" question is always answerable later (audit requirement), and
alert_events.event_id (a content hash, see triggers/base.py) doubles as the
dedup key so a re-delivered alert can never cause a duplicate order.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from .models import AlertEvent, OrderResult, TradeDecision

_SCHEMA = """
CREATE TABLE IF NOT EXISTS alert_events (
    event_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    line_price REAL NOT NULL,
    current_price REAL NOT NULL,
    line_type TEXT NOT NULL,
    chart_image_url TEXT,
    raw_source TEXT NOT NULL,
    received_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trade_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL REFERENCES alert_events(event_id),
    signal TEXT NOT NULL,
    confidence REAL NOT NULL,
    reason TEXT NOT NULL,
    line_basis TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS order_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL REFERENCES alert_events(event_id),
    status TEXT NOT NULL,
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT,
    size REAL,
    price REAL,
    order_id TEXT,
    raw_response TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class Storage:
    def __init__(self, db_path: str) -> None:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = str(path)
        with closing(self._connect()) as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def event_exists(self, event_id: str) -> bool:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT 1 FROM alert_events WHERE event_id = ?", (event_id,)
            ).fetchone()
            return row is not None

    def save_alert_event(self, event: AlertEvent) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """INSERT OR IGNORE INTO alert_events
                   (event_id, symbol, line_price, current_price, line_type,
                    chart_image_url, raw_source, received_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.event_id,
                    event.symbol,
                    event.line_price,
                    event.current_price,
                    event.line_type.value,
                    event.chart_image_url,
                    event.raw_source.value,
                    event.received_at.isoformat(),
                ),
            )
            conn.commit()

    def save_trade_decision(self, event_id: str, decision: TradeDecision) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """INSERT INTO trade_decisions
                   (event_id, signal, confidence, reason, line_basis)
                   VALUES (?, ?, ?, ?, ?)""",
                (event_id, decision.signal.value, decision.confidence, decision.reason, decision.line_basis),
            )
            conn.commit()

    def save_order_result(self, event_id: str, result: OrderResult) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """INSERT INTO order_results
                   (event_id, status, exchange, symbol, side, size, price,
                    order_id, raw_response, error_message)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event_id,
                    result.status.value,
                    result.exchange,
                    result.symbol,
                    result.side,
                    result.size,
                    result.price,
                    result.order_id,
                    json.dumps(result.raw_response) if result.raw_response is not None else None,
                    result.error_message,
                ),
            )
            conn.commit()
