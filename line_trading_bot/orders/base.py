from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Callable, TypeVar

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..models import AlertEvent, OrderResult, RiskDecision, TradeDecision

logger = logging.getLogger(__name__)

T = TypeVar("T")


class OrderAdapterError(Exception):
    """Raised by an adapter's exchange call; triggers a retry."""


class OrderAdapter(ABC):
    """One implementation per exchange (spec 3.3). Adding/removing an
    exchange never touches the Judgment Engine or anything upstream of it.
    """

    name: str

    def __init__(self, max_retries: int = 3, base_delay_seconds: float = 2.0) -> None:
        self._max_retries = max_retries
        self._base_delay_seconds = base_delay_seconds

    @abstractmethod
    def place_order(
        self, decision: TradeDecision, event: AlertEvent, risk: RiskDecision
    ) -> OrderResult:
        raise NotImplementedError

    def _call_with_retry(self, func: Callable[[], T]) -> T:
        """Exponential backoff around a single exchange API call (spec 5).

        `func` should raise on failure (OrderAdapterError or the underlying
        exception); after the configured number of retries the final
        exception is re-raised for the caller (place_order) to turn into an
        OrderResult(status=error) and trigger the LINE failure alert.
        """
        retryer = retry(
            reraise=True,
            stop=stop_after_attempt(self._max_retries + 1),
            wait=wait_exponential(multiplier=self._base_delay_seconds, min=self._base_delay_seconds),
            retry=retry_if_exception_type(Exception),
            before_sleep=self._log_retry,
        )
        return retryer(func)()

    def _log_retry(self, retry_state) -> None:
        logger.warning(
            "%s order call failed (attempt %d), retrying: %s",
            self.name,
            retry_state.attempt_number,
            retry_state.outcome.exception(),
        )
