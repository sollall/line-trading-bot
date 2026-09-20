export interface Env {
  DB: D1Database;
  DEDUPE_KV: KVNamespace;
  PAPER_TRADE: string;

  // wrangler secret put で設定するシークレット
  CLAUDE_API_KEY: string;
  HYPERLIQUID_API_KEY: string;
  HYPERLIQUID_API_SECRET: string;
  BACKPACK_API_KEY: string;
  BACKPACK_API_SECRET: string;
  LINE_NOTIFY_TOKEN?: string;
  DISCORD_WEBHOOK_URL?: string;
}

export type LineKind = "entry" | "exit";
export type Exchange = "hyperliquid" | "backpack";

export interface NormalizedAlert {
  source: "tradingview" | "trendspider";
  lineKind: LineKind;
  symbol: string;
  exchange: Exchange;
  price: number;
  interval?: string;
  note?: string;
  firedAt: string;
}

export interface LlmDecision {
  action: "buy" | "sell" | "hold" | "close";
  confidence: number;
  reason: string;
}

export interface OrderResult {
  status: "skipped" | "ok" | "error";
  detail?: string;
}
