import type { Env } from "./types";
import { normalizeAlert, dedupeKey } from "./webhook";
import { judge } from "./llm";
import { placeOrder } from "./exchange";
import { logDecision } from "./db";
import { notify } from "./notify";

const DEDUPE_TTL_SECONDS = 15;

async function isDuplicate(env: Env, key: string): Promise<boolean> {
  const existing = await env.DEDUPE_KV.get(key);
  if (existing) return true;
  await env.DEDUPE_KV.put(key, "1", { expirationTtl: DEDUPE_TTL_SECONDS });
  return false;
}

async function handleAlert(env: Env, ctx: ExecutionContext, body: unknown): Promise<void> {
  const alert = normalizeAlert(body);

  const key = dedupeKey(alert);
  if (await isDuplicate(env, key)) {
    return;
  }

  const decision = await judge(env, alert);
  const order = await placeOrder(env, alert, decision);

  await Promise.allSettled([
    logDecision(env, alert, JSON.stringify(alert), JSON.stringify(decision), decision, order),
    notify(env, alert, decision, order),
  ]);
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    if (request.method !== "POST" || url.pathname !== "/webhook") {
      return new Response("not found", { status: 404 });
    }

    let body: unknown;
    try {
      body = await request.json();
    } catch {
      return new Response("invalid json", { status: 400 });
    }

    // TradingViewは3秒でタイムアウトするため、即200を返して後処理を非同期化する
    ctx.waitUntil(
      handleAlert(env, ctx, body).catch((err) => {
        console.error("handleAlert failed", err);
      }),
    );

    return new Response("ok", { status: 200 });
  },
};
