from __future__ import annotations

import functools
import inspect
from typing import Any, Callable, TypeVar

try:
    from typing import ParamSpec
except ImportError:  # pragma: no cover - Python 3.9 fallback
    from typing_extensions import ParamSpec

from .client import ApprovalRequiredError, AsyncWallet, DecisionRecord, Wallet
from .replay import build_replay_context

P = ParamSpec("P")
R = TypeVar("R")


def _resolve(value: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    return value(*args, **kwargs) if callable(value) else value


class WalletGuard:
    def __init__(
        self,
        wallet: Wallet,
        *,
        amount: float,
        counterparty: str,
        purpose: str,
        destination: str | None = None,
        budget_tags: dict[str, str] | None = None,
    ) -> None:
        self.wallet = wallet
        self.amount = amount
        self.counterparty = counterparty
        self.purpose = purpose
        self.destination = destination
        self.budget_tags = budget_tags
        self.decision: DecisionRecord | None = None

    def __enter__(self) -> DecisionRecord:
        self.decision = self.wallet.pay(
            amount=self.amount,
            to=self.destination or self.counterparty,
            counterparty=self.counterparty,
            purpose=self.purpose,
            budget_tags=self.budget_tags,
        )
        if self.decision.status != "approved":
            raise ApprovalRequiredError.from_decision(self.decision)
        return self.decision

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class AsyncWalletGuard:
    def __init__(
        self,
        wallet: AsyncWallet,
        *,
        amount: float,
        counterparty: str,
        purpose: str,
        destination: str | None = None,
        budget_tags: dict[str, str] | None = None,
    ) -> None:
        self.wallet = wallet
        self.amount = amount
        self.counterparty = counterparty
        self.purpose = purpose
        self.destination = destination
        self.budget_tags = budget_tags
        self.decision: DecisionRecord | None = None

    async def __aenter__(self) -> DecisionRecord:
        self.decision = await self.wallet.pay(
            amount=self.amount,
            to=self.destination or self.counterparty,
            counterparty=self.counterparty,
            purpose=self.purpose,
            budget_tags=self.budget_tags,
        )
        if self.decision.status != "approved":
            raise ApprovalRequiredError.from_decision(self.decision)
        return self.decision

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


def nornr_guard(
    wallet: Wallet | AsyncWallet,
    *,
    amount: float | Callable[..., float],
    counterparty: str | Callable[..., str],
    purpose: str | Callable[..., str],
    destination: str | Callable[..., str] | None = None,
    budget_tags: dict[str, str] | Callable[..., dict[str, str] | None] | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                decision = await wallet.pay(
                    amount=_resolve(amount, args, kwargs),
                    to=_resolve(destination, args, kwargs) or _resolve(counterparty, args, kwargs),
                    counterparty=_resolve(counterparty, args, kwargs),
                    purpose=_resolve(purpose, args, kwargs),
                    budget_tags=_resolve(budget_tags, args, kwargs),
                    replay_context=build_replay_context(func, args, kwargs, source="nornr_guard"),
                )
                if decision.status != "approved":
                    raise ApprovalRequiredError.from_decision(decision)
                return await func(*args, **kwargs)

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            decision = wallet.pay(
                amount=_resolve(amount, args, kwargs),
                to=_resolve(destination, args, kwargs) or _resolve(counterparty, args, kwargs),
                counterparty=_resolve(counterparty, args, kwargs),
                purpose=_resolve(purpose, args, kwargs),
                budget_tags=_resolve(budget_tags, args, kwargs),
                replay_context=build_replay_context(func, args, kwargs, source="nornr_guard"),
            )
            if decision.status != "approved":
                raise ApprovalRequiredError.from_decision(decision)
            return func(*args, **kwargs)

        return sync_wrapper  # type: ignore[return-value]

    return decorator
