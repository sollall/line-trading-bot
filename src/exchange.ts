import type { Env, LlmDecision, NormalizedAlert, OrderResult } from "./types";

async function withRetry<T>(fn: () => Promise<T>, retries = 3): Promise<T> {
  let lastErr: unknown;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      return await fn();
    } catch (err) {
      lastErr = err;
      if (attempt < retries) {
        const backoffMs = 200 * 2 ** attempt;
        await new Promise((r) => setTimeout(r, backoffMs));
      }
    }
  }
  throw lastErr;
}

async function placeOnHyperliquid(env: Env, alert: NormalizedAlert, decision: LlmDecision): Promise<void> {
  // 実際の署名・発注APIはHyperliquidの仕様に合わせて実装する。
  // ここでは骨組みのみ (レート制限対策としてリトライ/バックオフでラップする)。
  const res = await fetch("https://api.hyperliquid.xyz/exchange", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": env.HYPERLIQUID_API_KEY,
    },
    body: JSON.stringify({
      symbol: alert.symbol,
      side: decision.action,
      orderType: alert.lineKind === "entry" ? "limit" : "market",
      price: alert.price,
    }),
  });
  if (!res.ok) throw new Error(`hyperliquid order failed: ${res.status} ${await res.text()}`);
}

async function placeOnBackpack(env: Env, alert: NormalizedAlert, decision: LlmDecision): Promise<void> {
  const res = await fetch("https://api.backpack.exchange/api/v1/order", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": env.BACKPACK_API_KEY,
    },
    body: JSON.stringify({
      symbol: alert.symbol,
      side: decision.action,
      orderType: "market",
      price: alert.price,
    }),
  });
  if (!res.ok) throw new Error(`backpack order failed: ${res.status} ${await res.text()}`);
}

export async function placeOrder(env: Env, alert: NormalizedAlert, decision: LlmDecision): Promise<OrderResult> {
  const shouldOrder =
    (alert.lineKind === "entry" && (decision.action === "buy" || decision.action === "sell")) ||
    (alert.lineKind === "exit" && decision.action === "close");

  if (!shouldOrder) {
    return { status: "skipped", detail: `action=${decision.action}` };
  }

  if (env.PAPER_TRADE === "true") {
    return { status: "skipped", detail: "paper_trade" };
  }

  try {
    await withRetry(() =>
      alert.exchange === "backpack"
        ? placeOnBackpack(env, alert, decision)
        : placeOnHyperliquid(env, alert, decision),
    );
    return { status: "ok" };
  } catch (err) {
    return { status: "error", detail: String(err) };
  }
}
