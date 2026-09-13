# line-trading-bot

TradingViewのトレンドライン接近アラートをトリガーに、Claude (Anthropic API) がチャート画像とライン情報から売買判断を行い、Hyperliquid / Backpack へ自動発注するBot。

仕様書: `ライントレードBot 仕様書` に基づき実装。**Trigger層 / Judgment Engine / Order層** を正規化データ構造 (`AlertEvent` → `TradeDecision` → `OrderResult`) 経由の疎結合アダプタ構成にしてあるため、トリガー方式（メール→Webhook）や発注先取引所の変更は、対応するアダプタの追加・config変更だけで完結する。

## アーキテクチャ

```
[TradingView Alert] --(email or webhook)-->
  TriggerAdapter (EmailTriggerAdapter / WebhookTriggerAdapter)
    -> AlertEvent
  JudgmentEngine (Anthropic API, structured tool-use output)
    -> TradeDecision  (confidence閾値ガード付き)
  RiskManager
    -> RiskDecision   (サイズ/レバレッジの上限を適用、wait/低confidenceは非承認)
  OrderRouter -> OrderAdapter (HyperliquidOrderAdapter / BackpackOrderAdapter)
    -> OrderResult    (取引所API呼び出しは指数バックオフでリトライ)
  Storage (SQLite)     全AlertEvent/TradeDecision/OrderResultを永続化・監査用
  LineNotifier          判定結果・発注結果・失敗アラートをLINEへpush通知
```

各モジュールの対応:

| ディレクトリ / ファイル | 役割 |
|---|---|
| `line_trading_bot/models.py` | 層をまたぐ正規化データ構造 (`AlertEvent`, `TradeDecision`, `RiskDecision`, `OrderResult`) |
| `line_trading_bot/triggers/` | Trigger Adapter層 (`EmailTriggerAdapter`, `WebhookTriggerAdapter`) |
| `line_trading_bot/judgment/engine.py` | Judgment Engine (Claude呼び出し + confidence閾値ガード) |
| `line_trading_bot/risk.py` | RiskManager (ポジションサイズ・レバレッジ上限) |
| `line_trading_bot/orders/` | Order Adapter層 (`HyperliquidOrderAdapter`, `BackpackOrderAdapter`, `OrderRouter`) |
| `line_trading_bot/storage.py` | SQLite永続化 + イベントIDベースの冪等性 |
| `line_trading_bot/notify.py` | LINE Messaging API通知 |
| `line_trading_bot/pipeline.py` | 全層を接続するオーケストレータ |
| `line_trading_bot/container.py` | configから実アダプタを組み立てるファクトリ |
| `line_trading_bot/app.py` | FastAPIエントリポイント (`POST /webhook`, `GET /health`) |

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
# .env を編集して ANTHROPIC_API_KEY, LINE_*, 取引所の鍵, SYMBOL_EXCHANGE_MAP を設定

pytest -q               # テスト実行
python -m line_trading_bot.app   # ローカルでサーバ起動 (http://localhost:8000)
```

手動でパイプラインを1回だけ動かして確認する場合:

```bash
python scripts/simulate_alert.py
```

## 設定 (`.env`)

`.env.example` を参照。主なもの:

- `TRIGGER_MODE`: `email` (現状) / `webhook` (将来のTradingView Webhook移行後)。**この1行を変えるだけ**でトリガー方式を切り替えられる。
- `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` / `JUDGMENT_CONFIDENCE_THRESHOLD`: Judgment Engine設定。`confidence`がこの閾値未満の場合、Judgment Engine側で強制的に `wait` に上書きされる（LLMの誤断定に対する安全弁、仕様書3.2）。
- `RISK_MAX_POSITION_SIZE_USD` / `RISK_MAX_LEVERAGE`: 1トレードあたりの上限。ポジションサイジングの詳細ルール（銘柄ごとの資金配分等）は仕様書6の未確定事項のため、まずはフラットな上限のみ実装している。将来のルール変更は `risk.py` のみの変更で完結する。
- `SYMBOL_EXCHANGE_MAP`: `SYMBOL:exchange` のカンマ区切り。例 `BPUSDT:backpack,HYPEUSD:hyperliquid`。ここに取引所を追加/変更するだけで発注先を切り替えられる。対応する `*_API_KEY` 等の認証情報が未設定の場合、そのシンボルへの発注は「アダプタ未設定」としてログ＋LINE失敗通知のうえスキップされる（誤発注防止のため、起動失敗にはしない）。

## Trigger Adapter: メール本文フォーマット

TradingViewのアラートメッセージ（本文）は、現状は以下のKEY=VALUE形式をTradingView側のアラート設定で使う想定 (`EmailTriggerAdapter`):

```
SYMBOL=BPUSDT
LINE_PRICE=65000
CURRENT_PRICE=65120
LINE_TYPE=resistance
CHART_URL=https://www.tradingview.com/x/xxxxx/
```

`SYMBOL` / `LINE_PRICE` / `CURRENT_PRICE` は必須。`LINE_TYPE` 省略時は `unknown`、`CHART_URL` は省略可（画像なしでライン数値のみでの判定になる）。

このメール本文をCloudflare Email Workerが受信・パースし、JSON化して `POST /webhook` に転送する構成を想定している:

```js
// Cloudflare Email Worker (概要)
import PostalMime from "postal-mime";

export default {
  async email(message, env, ctx) {
    const parsed = await PostalMime.parse(message.raw);
    await fetch(env.BOT_WEBHOOK_URL, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        subject: parsed.subject,
        text: parsed.text,
        from: parsed.from?.address,
      }),
    });
  },
};
```

## Trigger Adapter: 将来のWebhook移行

TradingViewが有料プランのWebhookに切り替わった場合、アラートメッセージをJSONテンプレートにして直接 `POST /webhook` へ送るだけでよい (`WebhookTriggerAdapter`):

```json
{
  "symbol": "BPUSDT",
  "line_price": 65000,
  "current_price": 65120,
  "line_type": "resistance",
  "chart_image_url": null
}
```

`.env` の `TRIGGER_MODE=webhook` に変更すれば、後段（Judgment Engine以降）は無改修でそのまま動く。

## 冪等性・可用性・監査性 (仕様書5)

- **冪等性**: `event_id` はメール本文/Webhook JSONの内容ハッシュ (SHA-256) から決定的に生成される (`triggers/base.py: compute_event_id`)。同一アラートが再送されても同じ `event_id` になり、`storage.event_exists()` により重複発注を防ぐ。
- **可用性**: `TriggerAdapter.parse()` が `TriggerParseError` を送出した場合、Judgment Engineには渡さずログに記録して握りつぶす（誤発注防止優先、`pipeline.py`）。Judgment Engine自体が例外を投げた場合も同様にorderを出さずLINEへ失敗通知する。
- **リトライ**: Order Adapter層のAPI呼び出しは `OrderAdapter._call_with_retry` により指数バックオフでリトライし（`ORDER_MAX_RETRIES` / `ORDER_RETRY_BASE_DELAY_SECONDS`）、最終的に失敗した場合はLINEへアラート通知する。
- **監査性**: `AlertEvent` / `TradeDecision`（`line_basis`含む）/ `OrderResult` は全て `storage.py` のSQLiteに保存され、後から目視で判定根拠を検証できる。

## 取引所アダプタの実装について（重要な注意）

- **Hyperliquid**: 公式の [`hyperliquid-python-sdk`](https://github.com/hyperliquid-dex/hyperliquid-python-sdk) を利用し、署名処理はSDKに委譲している。
- **Backpack**: 公式SDKに依存せず、[Backpack Exchange API docs](https://docs.backpack.exchange/) に基づくED25519署名を手実装している (`orders/backpack_adapter.py`)。**本番投入前に、パラメータ名・大文字小文字・エンドポイントパスを最新の公式ドキュメントと突き合わせて検証すること。** 取引所APIは仕様変更が起こりうるため、ここは "差し替え可能" というアーキテクチャの恩恵を受けられる箇所でもある（`BackpackOrderAdapter` 単体を直すだけで済む）。

いずれのアダプタも実際の資金を動かすため、**先にテストネット/紙トレードで動作確認してから本番の鍵を設定すること**を強く推奨する。

## 今後の検討事項（仕様書6、未実装）

- バックテストによるJudgment Engineの精度検証
- 複数トレンドライン交差時のconfidence閾値の具体的なチューニング
- 銘柄ごとの資金配分など、より高度なポジションサイジングルール（現状は`RISK_MAX_POSITION_SIZE_USD`によるフラット上限のみ）
- Email/Webhookそれぞれの障害時のフェイルオーバー方針

## テスト

```bash
pytest -q
```

外部呼び出し（Anthropic API、取引所API、LINE API）は全てモック/フェイクでテストしており、実際のネットワークアクセスは発生しない。
