import type { Env, LlmDecision, NormalizedAlert, OrderResult } from "./types";

export async function notify(
  env: Env,
  alert: NormalizedAlert,
  decision: LlmDecision,
  order: OrderResult,
): Promise<void> {
  const message = `[${alert.lineKind}] ${alert.symbol} @ ${alert.price}\naction=${decision.action} confidence=${decision.confidence}\norder=${order.status}${order.detail ? ` (${order.detail})` : ""}`;

  const tasks: Promise<unknown>[] = [];

  if (env.DISCORD_WEBHOOK_URL) {
    tasks.push(
      fetch(env.DISCORD_WEBHOOK_URL, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ content: message }),
      }),
    );
  }

  if (env.LINE_NOTIFY_TOKEN) {
    tasks.push(
      fetch("https://notify-api.line.me/api/notify", {
        method: "POST",
        headers: {
          authorization: `Bearer ${env.LINE_NOTIFY_TOKEN}`,
          "content-type": "application/x-www-form-urlencoded",
        },
        body: new URLSearchParams({ message: `\n${message}` }),
      }),
    );
  }

  await Promise.allSettled(tasks);
}
