from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from decimal import Decimal

from .money import AmountLike, usd_decimal, usd_text


@dataclass(frozen=True)
class CircuitBreakerConfig:
    max_requests: int = 10
    window_seconds: float = 1.0
    max_spend_usd: AmountLike | None = None
    max_velocity_usd: AmountLike | None = None


class LocalCircuitBreaker:
    def __init__(self, config: CircuitBreakerConfig | None = None) -> None:
        self.config = config or CircuitBreakerConfig()
        self._events: deque[tuple[float, Decimal]] = deque()

    def check(self, amount_usd: AmountLike, *, now: float | None = None) -> None:
        current_time = now if now is not None else time.time()
        cutoff = current_time - self.config.window_seconds
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()
        projected_requests = len(self._events) + 1
        if projected_requests > self.config.max_requests:
            raise RuntimeError(
                f"Local NORNR circuit breaker opened after {projected_requests} requests in {self.config.window_seconds:.1f}s",
            )
        normalized_amount = usd_decimal(amount_usd)
        projected_spend = sum((usd_decimal(amount) for _, amount in self._events), usd_decimal(0)) + normalized_amount
        if self.config.max_spend_usd is not None and projected_spend > usd_decimal(self.config.max_spend_usd):
            raise RuntimeError(
                f"Local NORNR circuit breaker blocked projected spend {usd_text(projected_spend)} USD "
                f"over {self.config.window_seconds:.1f}s",
            )
        if self.config.max_velocity_usd is not None:
            velocity = projected_spend / usd_decimal(max(self.config.window_seconds, 0.001))
            if velocity > usd_decimal(self.config.max_velocity_usd):
                raise RuntimeError(
                    f"Local NORNR circuit breaker blocked velocity {usd_text(velocity)} USD/s "
                    f"over {self.config.window_seconds:.1f}s",
                )
        self._events.append((current_time, normalized_amount))
