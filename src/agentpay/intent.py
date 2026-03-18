from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .models import DecisionRecord


@dataclass(frozen=True)
class IntentCheckRecord:
    allowed: bool
    status: str
    requires_approval: bool
    recommended_action: str
    decision: DecisionRecord
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_decision(cls, decision: DecisionRecord, *, intent: str, amount: float) -> "IntentCheckRecord":
        if decision.status == "approved":
            action = f"Proceed with {intent} at {amount:.2f} USD."
        elif decision.status == "queued":
            action = "Request approval or reduce scope before running."
        else:
            action = "Change the plan, lower cost, or adjust the mandate before continuing."
        return cls(
            allowed=decision.status == "approved",
            status=decision.status,
            requires_approval=decision.requires_approval,
            recommended_action=action,
            decision=decision,
            _raw={
                "allowed": decision.status == "approved",
                "status": decision.status,
                "requiresApproval": decision.requires_approval,
                "recommendedAction": action,
                "decision": decision.to_dict(),
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return dict(self._raw)
