CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fired_at TEXT NOT NULL,
  symbol TEXT NOT NULL,
  line_kind TEXT NOT NULL,
  exchange TEXT NOT NULL,
  prompt TEXT NOT NULL,
  raw_output TEXT NOT NULL,
  action TEXT NOT NULL,
  confidence REAL NOT NULL,
  reason TEXT NOT NULL,
  order_status TEXT NOT NULL,
  order_detail TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_decisions_symbol_fired_at ON decisions (symbol, fired_at);
