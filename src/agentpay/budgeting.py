from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from .money import AmountLike, usd_decimal


@dataclass(frozen=True)
class BudgetScope:
    limit_usd: Decimal
    counterparty: str | None = None
    purpose_prefix: str | None = None
    budget_tags: dict[str, str] | None = None
    dry_run: bool = False


_ACTIVE_BUDGET_SCOPE: ContextVar[BudgetScope | None] = ContextVar("nornr_active_budget_scope", default=None)


class BudgetContext:
    def __init__(
        self,
        limit: AmountLike,
        *,
        counterparty: str | None = None,
        purpose_prefix: str | None = None,
        budget_tags: dict[str, str] | None = None,
        dry_run: bool = False,
    ) -> None:
        self.scope = BudgetScope(
            limit_usd=usd_decimal(limit),
            counterparty=counterparty,
            purpose_prefix=purpose_prefix,
            budget_tags=dict(budget_tags or {}) or None,
            dry_run=dry_run,
        )
        self._token: Token[BudgetScope | None] | None = None

    def __enter__(self) -> BudgetScope:
        self._token = _ACTIVE_BUDGET_SCOPE.set(self.scope)
        return self.scope

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> Literal[False]:
        if self._token is not None:
            _ACTIVE_BUDGET_SCOPE.reset(self._token)
        return False

    async def __aenter__(self) -> BudgetScope:
        return self.__enter__()

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> Literal[False]:
        return self.__exit__(exc_type, exc, tb)


def budget(
    limit: AmountLike,
    *,
    counterparty: str | None = None,
    purpose_prefix: str | None = None,
    budget_tags: dict[str, str] | None = None,
    dry_run: bool = False,
) -> BudgetContext:
    """Create a temporary local NORNR budget scope for a code block."""

    return BudgetContext(
        limit,
        counterparty=counterparty,
        purpose_prefix=purpose_prefix,
        budget_tags=budget_tags,
        dry_run=dry_run,
    )


def current_budget_scope() -> BudgetScope | None:
    return _ACTIVE_BUDGET_SCOPE.get()
