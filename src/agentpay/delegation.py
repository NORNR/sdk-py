from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .budgeting import BudgetContext, budget
from .models import BudgetCapRecord
from .money import AmountLike, usd_float

if TYPE_CHECKING:
    from .client import AsyncWallet, Wallet


@dataclass(frozen=True)
class DelegatedMandate:
    parent_agent_id: str
    target_agent_id: str
    daily_limit_usd: float
    counterparty: str | None = None
    purpose_prefix: str | None = None
    budget_tags: dict[str, str] | None = None
    metadata: dict[str, Any] | None = None
    applied_budget_cap: BudgetCapRecord | None = None

    def to_budget_cap_payload(self) -> dict[str, Any]:
        payload = {
            "agentId": self.target_agent_id,
            "dailyLimitUsd": self.daily_limit_usd,
            "reason": f"Delegated NORNR mandate from {self.parent_agent_id}",
            "source": "nornr.delegation",
        }
        if self.metadata:
            payload["evidence"] = dict(self.metadata)
        return payload

    def to_budget_scope(self, *, dry_run: bool = False) -> BudgetContext:
        return budget(
            self.daily_limit_usd,
            counterparty=self.counterparty,
            purpose_prefix=self.purpose_prefix,
            budget_tags=self.budget_tags,
            dry_run=dry_run,
        )

    def to_business_context(self) -> dict[str, Any]:
        return {
            "delegatedMandate": {
                "parentAgentId": self.parent_agent_id,
                "targetAgentId": self.target_agent_id,
                "dailyLimitUsd": self.daily_limit_usd,
                "counterparty": self.counterparty,
                "purposePrefix": self.purpose_prefix,
                "budgetTags": dict(self.budget_tags or {}),
                "metadata": dict(self.metadata or {}),
            }
        }


def create_delegated_mandate(
    wallet: "Wallet",
    *,
    target_agent_id: str,
    daily_limit: AmountLike,
    counterparty: str | None = None,
    purpose_prefix: str | None = None,
    budget_tags: dict[str, str] | None = None,
    metadata: dict[str, Any] | None = None,
    apply_budget_cap: bool = True,
) -> DelegatedMandate:
    mandate = DelegatedMandate(
        parent_agent_id=wallet.agent_id,
        target_agent_id=target_agent_id,
        daily_limit_usd=usd_float(daily_limit),
        counterparty=counterparty,
        purpose_prefix=purpose_prefix,
        budget_tags=dict(budget_tags or {}),
        metadata=dict(metadata or {}),
    )
    applied_budget_cap = wallet.client.create_budget_cap(mandate.to_budget_cap_payload()) if apply_budget_cap else None
    return DelegatedMandate(
        parent_agent_id=mandate.parent_agent_id,
        target_agent_id=mandate.target_agent_id,
        daily_limit_usd=mandate.daily_limit_usd,
        counterparty=mandate.counterparty,
        purpose_prefix=mandate.purpose_prefix,
        budget_tags=mandate.budget_tags,
        metadata=mandate.metadata,
        applied_budget_cap=applied_budget_cap,
    )


async def create_delegated_mandate_async(
    wallet: "AsyncWallet",
    *,
    target_agent_id: str,
    daily_limit: AmountLike,
    counterparty: str | None = None,
    purpose_prefix: str | None = None,
    budget_tags: dict[str, str] | None = None,
    metadata: dict[str, Any] | None = None,
    apply_budget_cap: bool = True,
) -> DelegatedMandate:
    mandate = DelegatedMandate(
        parent_agent_id=wallet.agent_id,
        target_agent_id=target_agent_id,
        daily_limit_usd=usd_float(daily_limit),
        counterparty=counterparty,
        purpose_prefix=purpose_prefix,
        budget_tags=dict(budget_tags or {}),
        metadata=dict(metadata or {}),
    )
    applied_budget_cap = await wallet.client.create_budget_cap(mandate.to_budget_cap_payload()) if apply_budget_cap else None
    return DelegatedMandate(
        parent_agent_id=mandate.parent_agent_id,
        target_agent_id=mandate.target_agent_id,
        daily_limit_usd=mandate.daily_limit_usd,
        counterparty=mandate.counterparty,
        purpose_prefix=mandate.purpose_prefix,
        budget_tags=mandate.budget_tags,
        metadata=mandate.metadata,
        applied_budget_cap=applied_budget_cap,
    )
