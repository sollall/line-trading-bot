import type { Env, LlmDecision, NormalizedAlert } from "./types";

const ENTRY_SYSTEM_PROMPT = `あなたはトレーディングのエントリー判断アシスタントです。
与えられた情報だけを根拠に、エントリーすべきかを判断してください。
出力は必ず次のJSON形式のみ: {"action": "buy"|"sell"|"hold", "confidence": 0-1, "reason": "..."}`;

const EXIT_SYSTEM_PROMPT = `あなたはトレーディングの決済判断アシスタントです。応答速度を優先し、
簡潔に判断してください。出力は必ず次のJSON形式のみ: {"action": "close"|"hold", "confidence": 0-1, "reason": "..."}`;

function buildUserPrompt(alert: NormalizedAlert): string {
  const lines = [
    `銘柄: ${alert.symbol}`,
    `ライン種別: ${alert.lineKind}`,
    `現在価格: ${alert.price}`,
    alert.interval ? `時間足: ${alert.interval}` : undefined,
    alert.note ? `イベント: ${alert.note}` : undefined,
  ].filter(Boolean);
  return lines.join("\n");
}

export async function judge(env: Env, alert: NormalizedAlert): Promise<LlmDecision> {
  const system = alert.lineKind === "entry" ? ENTRY_SYSTEM_PROMPT : EXIT_SYSTEM_PROMPT;

  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": env.CLAUDE_API_KEY,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model: "claude-sonnet-4-5",
      max_tokens: 300,
      system,
      messages: [{ role: "user", content: buildUserPrompt(alert) }],
    }),
  });

  if (!res.ok) {
    throw new Error(`claude api error: ${res.status} ${await res.text()}`);
  }

  const data = (await res.json()) as { content: { type: string; text?: string }[] };
  const text = data.content.find((c) => c.type === "text")?.text ?? "";

  try {
    const parsed = JSON.parse(text);
    return {
      action: parsed.action,
      confidence: Number(parsed.confidence),
      reason: String(parsed.reason ?? ""),
    };
  } catch {
    // パース失敗時は安全側 (hold) に倒す
    return { action: "hold", confidence: 0, reason: `parse_error: ${text}` };
  }
}
