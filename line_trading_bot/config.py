"""Central configuration, sourced from environment variables / .env.

Every layer that needs to know about a *specific* adapter implementation
(which trigger mode is active, which exchange a symbol routes to) reads it
from here rather than hardcoding it, so swapping adapters is a config change.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Trigger layer ---
    # "email" (current: TradingView -> Cloudflare Email Workers -> our webhook)
    # or "webhook" (future: TradingView Webhook JSON directly)
    trigger_mode: str = "email"

    # --- Judgment Engine ---
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    judgment_confidence_threshold: float = 0.6
    judgment_max_tokens: int = 1024

    # --- Risk Manager ---
    risk_max_position_size_usd: float = 100.0
    risk_max_leverage: float = 3.0

    # --- Order layer ---
    # "BPUSDT:backpack,HYPEUSD:hyperliquid"
    symbol_exchange_map: str = ""
    order_max_retries: int = 3
    order_retry_base_delay_seconds: float = 2.0

    hyperliquid_api_url: str = "https://api.hyperliquid.xyz"
    hyperliquid_wallet_address: str = ""
    hyperliquid_private_key: str = ""

    backpack_api_url: str = "https://api.backpack.exchange"
    backpack_api_key: str = ""  # base64 ED25519 verifying key
    backpack_api_secret: str = ""  # base64 ED25519 signing (seed) key

    # --- Storage ---
    database_path: str = "data/trading_bot.db"

    # --- Notification ---
    line_channel_access_token: str = ""
    line_to_user_id: str = ""

    def symbol_exchange_mapping(self) -> dict[str, str]:
        """Parse 'SYMBOL:exchange,SYMBOL2:exchange2' into a dict."""
        mapping: dict[str, str] = {}
        for pair in self.symbol_exchange_map.split(","):
            pair = pair.strip()
            if not pair:
                continue
            symbol, _, exchange = pair.partition(":")
            if symbol and exchange:
                mapping[symbol.strip()] = exchange.strip().lower()
        return mapping


@lru_cache
def get_settings() -> Settings:
    return Settings()
