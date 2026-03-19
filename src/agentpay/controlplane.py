from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .client import AsyncWallet, Wallet
from .counterparty import CounterpartyReview
from .delegation import DelegatedMandate
from .money import AmountLike
from .runtime import AsyncGovernedActionRun, GovernedActionRun, GovernedExecutionRecord
from .scopes import CredentialPosture, ScopeTemplate, credential_posture, recommended_scopes


@dataclass(frozen=True)
class NornrRuntime:
    wallet: Wallet

    @classmethod
    def connect(cls, **kwargs: Any) -> "NornrRuntime":
        return cls(wallet=Wallet.connect(**kwargs))

    @classmethod
    def create(cls, **kwargs: Any) -> "NornrRuntime":
        return cls(wallet=Wallet.create(**kwargs))

    def begin(self, **kwargs: Any) -> GovernedActionRun:
        return self.wallet.begin_governed_action(**kwargs)

    def execute(self, **kwargs: Any) -> GovernedExecutionRecord:
        return self.wallet.execute_governed(**kwargs)

    def review_counterparty(self, counterparty: str) -> CounterpartyReview:
        return self.wallet.review_counterparty(counterparty)

    def delegate_mandate(self, **kwargs: Any) -> DelegatedMandate:
        return self.wallet.delegate_mandate(**kwargs)

    def scopes_for(self, surface: str) -> ScopeTemplate:
        return recommended_scopes(surface)

    def key_posture(self, granted_scopes: Mapping[str, object] | list[str]) -> CredentialPosture:
        return credential_posture(granted_scopes)


@dataclass(frozen=True)
class GovernedAgentRuntime:
    wallet: AsyncWallet

    @classmethod
    async def connect(cls, **kwargs: Any) -> "GovernedAgentRuntime":
        return cls(wallet=await AsyncWallet.connect(**kwargs))

    @classmethod
    async def create(cls, **kwargs: Any) -> "GovernedAgentRuntime":
        return cls(wallet=await AsyncWallet.create(**kwargs))

    async def begin(self, **kwargs: Any) -> AsyncGovernedActionRun:
        return await self.wallet.begin_governed_action(**kwargs)

    async def execute(self, **kwargs: Any) -> GovernedExecutionRecord:
        return await self.wallet.execute_governed(**kwargs)

    async def review_counterparty(self, counterparty: str) -> CounterpartyReview:
        return await self.wallet.review_counterparty(counterparty)

    async def delegate_mandate(
        self,
        *,
        target_agent_id: str,
        daily_limit: AmountLike,
        counterparty: str | None = None,
        purpose_prefix: str | None = None,
        budget_tags: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
        apply_budget_cap: bool = True,
    ) -> DelegatedMandate:
        return await self.wallet.delegate_mandate(
            target_agent_id=target_agent_id,
            daily_limit=daily_limit,
            counterparty=counterparty,
            purpose_prefix=purpose_prefix,
            budget_tags=budget_tags,
            metadata=metadata,
            apply_budget_cap=apply_budget_cap,
        )

    def scopes_for(self, surface: str) -> ScopeTemplate:
        return recommended_scopes(surface)

    def key_posture(self, granted_scopes: Mapping[str, object] | list[str]) -> CredentialPosture:
        return credential_posture(granted_scopes)
