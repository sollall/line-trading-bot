import type { LineKind, NormalizedAlert } from "./types";

// TradingView: {{ticker}}, {{interval}}, {{close}}, {{time}}, {{exchange}} を
// アラートメッセージ側でJSON化して送る想定。line_kind はアラート名 or 固定文言で判別する。
interface TradingViewPayload {
  ticker: string;
  interval?: string;
  close: number;
  time: string;
  exchange: Exchange | string;
  line_kind: LineKind;
}

// TrendSpider: %alert_symbol%, %last_price%, %price_action_event%, %alert_note% を使用。
interface TrendSpiderPayload {
  alert_symbol: string;
  last_price: number;
  price_action_event: string; // "touch" | "break_through" | "bounce"
  alert_note: string; // line_kind と exchange を埋め込んでおく想定 (例: "entry:hyperliquid")
}

type Exchange = "hyperliquid" | "backpack";

function isTradingViewPayload(body: unknown): body is TradingViewPayload {
  return !!body && typeof body === "object" && "ticker" in body && "close" in body;
}

function isTrendSpiderPayload(body: unknown): body is TrendSpiderPayload {
  return !!body && typeof body === "object" && "alert_symbol" in body && "last_price" in body;
}

function parseAlertNote(note: string): { lineKind: LineKind; exchange: Exchange } {
  const [kindRaw, exchangeRaw] = note.split(":").map((s) => s.trim().toLowerCase());
  const lineKind: LineKind = kindRaw === "exit" ? "exit" : "entry";
  const exchange: Exchange = exchangeRaw === "backpack" ? "backpack" : "hyperliquid";
  return { lineKind, exchange };
}

export function normalizeAlert(body: unknown): NormalizedAlert {
  if (isTradingViewPayload(body)) {
    return {
      source: "tradingview",
      lineKind: body.line_kind,
      symbol: body.ticker,
      exchange: body.exchange === "backpack" ? "backpack" : "hyperliquid",
      price: Number(body.close),
      interval: body.interval,
      firedAt: body.time,
    };
  }

  if (isTrendSpiderPayload(body)) {
    const { lineKind, exchange } = parseAlertNote(body.alert_note ?? "");
    return {
      source: "trendspider",
      lineKind,
      symbol: body.alert_symbol,
      exchange,
      price: Number(body.last_price),
      note: body.price_action_event,
      firedAt: new Date().toISOString(),
    };
  }

  throw new Error("unrecognized webhook payload shape");
}

export function dedupeKey(alert: NormalizedAlert, bucketSeconds = 15): string {
  const bucket = Math.floor(Date.now() / 1000 / bucketSeconds);
  return `${alert.symbol}:${alert.lineKind}:${bucket}`;
}
