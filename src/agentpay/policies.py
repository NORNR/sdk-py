from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Type


@dataclass(frozen=True)
class PolicyDefinition:
    daily_limit: float | None = None
    require_approval_above: float | None = None
    max_transaction: float | None = None
    allowlist: list[str] | None = None
    mode: str = "enforced"
    auto_pause_on_anomaly: bool = False
    review_on_anomaly: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "dailyLimitUsd": self.daily_limit,
            "requireApprovalOverUsd": self.require_approval_above,
            "maxTransactionUsd": self.max_transaction,
            "counterpartyAllowlist": self.allowlist,
            "mode": self.mode,
            "autoPauseOnAnomaly": self.auto_pause_on_anomaly,
            "reviewOnAnomaly": self.review_on_anomaly,
        }


class Policy:
    daily_limit: float | None = None
    require_approval_above: float | None = None
    max_transaction: float | None = None
    allowlist: list[str] | None = None
    mode: str = "enforced"
    auto_pause_on_anomaly: bool = False
    review_on_anomaly: bool = False

    @classmethod
    def definition(cls) -> PolicyDefinition:
        return PolicyDefinition(
            daily_limit=cls.daily_limit,
            require_approval_above=cls.require_approval_above,
            max_transaction=cls.max_transaction,
            allowlist=list(cls.allowlist) if cls.allowlist else None,
            mode=cls.mode,
            auto_pause_on_anomaly=cls.auto_pause_on_anomaly,
            review_on_anomaly=cls.review_on_anomaly,
        )

    @classmethod
    def to_payload(cls) -> dict[str, Any]:
        return cls.definition().to_payload()


def apply_policy(target: Any, policy: Type[Policy] | PolicyDefinition, *, agent_id: str | None = None) -> Any:
    payload = policy.to_payload() if isinstance(policy, PolicyDefinition) else policy.definition().to_payload()
    if hasattr(target, "client") and hasattr(target, "agent_id"):
        return target.client.create_policy(target.agent_id, payload)
    if agent_id is None:
        raise ValueError("agent_id is required when applying a policy through a low-level client")
    return target.create_policy(agent_id, payload)
