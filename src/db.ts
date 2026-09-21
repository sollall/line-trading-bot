import type { Env, LlmDecision, NormalizedAlert, OrderResult } from "./types";

export async function logDecision(
  env: Env,
  alert: NormalizedAlert,
  prompt: string,
  rawOutput: string,
  decision: LlmDecision,
  order: OrderResult,
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO decisions
      (fired_at, symbol, line_kind, exchange, prompt, raw_output, action, confidence, reason, order_status, order_detail)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
  )
    .bind(
      alert.firedAt,
      alert.symbol,
      alert.lineKind,
      alert.exchange,
      prompt,
      rawOutput,
      decision.action,
      decision.confidence,
      decision.reason,
      order.status,
      order.detail ?? null,
    )
    .run();
}
