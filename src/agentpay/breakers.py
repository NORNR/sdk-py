from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class CircuitBreakerConfig:
    max_requests: int = 10
    window_seconds: float = 1.0
    max_spend_usd: float | None = None
    max_velocity_usd: float | None = None


class LocalCircuitBreaker:
    def __init__(self, config: CircuitBreakerConfig | None = None) -> None:
        self.config = config or CircuitBreakerConfig()
        self._events: deque[tuple[float, float]] = deque()

    def check(self, amount_usd: float, *, now: float | None = None) -> None:
        current_time = now if now is not None else time.time()
        cutoff = current_time - self.config.window_seconds
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()
        projected_requests = len(self._events) + 1
        if projected_requests > self.config.max_requests:
            raise RuntimeError(
                f"Local NORNR circuit breaker opened after {projected_requests} requests in {self.config.window_seconds:.1f}s",
            )
        projected_spend = sum(amount for _, amount in self._events) + float(amount_usd)
        if self.config.max_spend_usd is not None and projected_spend > self.config.max_spend_usd:
            raise RuntimeError(
                f"Local NORNR circuit breaker blocked projected spend {projected_spend:.2f} USD "
                f"over {self.config.window_seconds:.1f}s",
            )
        if self.config.max_velocity_usd is not None:
            velocity = projected_spend / max(self.config.window_seconds, 0.001)
            if velocity > self.config.max_velocity_usd:
                raise RuntimeError(
                    f"Local NORNR circuit breaker blocked velocity {velocity:.2f} USD/s "
                    f"over {self.config.window_seconds:.1f}s",
                )
        self._events.append((current_time, float(amount_usd)))
