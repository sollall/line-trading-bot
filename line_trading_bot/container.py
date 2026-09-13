"""Builds a fully-wired TradingPipeline from Settings.

This is the one place that decides *which concrete adapters* get plugged
into the pipeline. Everything here is driven by config (spec 4's
"differences are config, not code" table): trigger mode, and which
exchanges are actually referenced by SYMBOL_EXCHANGE_MAP.
"""
from __future__ import annotations

import logging

from .config import Settings
from .judgment.engine import JudgmentEngine
from .notify import LineNotifier
from .orders.backpack_adapter import BackpackOrderAdapter
from .orders.base import OrderAdapter
from .orders.hyperliquid_adapter import HyperliquidOrderAdapter
from .orders.router import OrderRouter
from .pipeline import TradingPipeline
from .risk import RiskManager
from .storage import Storage
from .triggers import get_trigger_adapter

logger = logging.getLogger(__name__)


def build_pipeline(settings: Settings) -> TradingPipeline:
    trigger_adapter = get_trigger_adapter(settings.trigger_mode)

    judgment_engine = JudgmentEngine(
        api_key=settings.anthropic_api_key,
        model=settings.anthropic_model,
        confidence_threshold=settings.judgment_confidence_threshold,
        max_tokens=settings.judgment_max_tokens,
    )

    risk_manager = RiskManager(
        max_position_size_usd=settings.risk_max_position_size_usd,
        max_leverage=settings.risk_max_leverage,
    )

    symbol_to_exchange = settings.symbol_exchange_mapping()
    order_router = OrderRouter(
        _build_order_adapters(settings, needed_exchanges=set(symbol_to_exchange.values())),
        symbol_to_exchange,
    )

    storage = Storage(settings.database_path)
    notifier = LineNotifier(settings.line_channel_access_token, settings.line_to_user_id)

    return TradingPipeline(
        trigger_adapter=trigger_adapter,
        judgment_engine=judgment_engine,
        risk_manager=risk_manager,
        order_router=order_router,
        storage=storage,
        notifier=notifier,
    )


def _build_order_adapters(settings: Settings, needed_exchanges: set[str]) -> dict[str, OrderAdapter]:
    adapters: dict[str, OrderAdapter] = {}

    if "hyperliquid" in needed_exchanges:
        if settings.hyperliquid_wallet_address and settings.hyperliquid_private_key:
            adapters["hyperliquid"] = HyperliquidOrderAdapter(
                wallet_address=settings.hyperliquid_wallet_address,
                private_key=settings.hyperliquid_private_key,
                api_url=settings.hyperliquid_api_url,
                max_retries=settings.order_max_retries,
                base_delay_seconds=settings.order_retry_base_delay_seconds,
            )
        else:
            logger.warning("SYMBOL_EXCHANGE_MAP references hyperliquid but credentials are missing")

    if "backpack" in needed_exchanges:
        if settings.backpack_api_key and settings.backpack_api_secret:
            adapters["backpack"] = BackpackOrderAdapter(
                api_key=settings.backpack_api_key,
                api_secret=settings.backpack_api_secret,
                api_url=settings.backpack_api_url,
                max_retries=settings.order_max_retries,
                base_delay_seconds=settings.order_retry_base_delay_seconds,
            )
        else:
            logger.warning("SYMBOL_EXCHANGE_MAP references backpack but credentials are missing")

    return adapters
