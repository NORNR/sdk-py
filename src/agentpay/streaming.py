from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any, TypeVar

from .client import AsyncWallet, ApprovalRequiredError, Wallet

T = TypeVar("T")


def guarded_stream(
    wallet: Wallet,
    stream_factory: Callable[[], Iterator[T]],
    *,
    amount: float,
    counterparty: str,
    purpose: str,
    destination: str | None = None,
    budget_tags: dict[str, str] | None = None,
) -> Iterator[T]:
    """Run a NORNR preflight before yielding a sync stream."""

    decision = wallet.pay(
        amount=amount,
        to=destination or counterparty,
        counterparty=counterparty,
        purpose=purpose,
        budget_tags=budget_tags,
    )
    if decision.status != "approved":
        raise ApprovalRequiredError.from_decision(decision)
    yield from stream_factory()


async def guarded_async_stream(
    wallet: AsyncWallet,
    stream_factory: Callable[[], AsyncIterator[T]],
    *,
    amount: float,
    counterparty: str,
    purpose: str,
    destination: str | None = None,
    budget_tags: dict[str, str] | None = None,
) -> AsyncIterator[T]:
    """Run a NORNR preflight before yielding an async stream."""

    decision = await wallet.pay(
        amount=amount,
        to=destination or counterparty,
        counterparty=counterparty,
        purpose=purpose,
        budget_tags=budget_tags,
    )
    if decision.status != "approved":
        raise ApprovalRequiredError.from_decision(decision)
    async for chunk in stream_factory():
        yield chunk
