from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, TYPE_CHECKING

if TYPE_CHECKING:
    from .client import AsyncWallet, Wallet


@dataclass(frozen=True)
class MilestoneDisputeResult:
    agreement_id: str
    milestone_id: str
    action: str
    status: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agreementId": self.agreement_id,
            "milestoneId": self.milestone_id,
            "action": self.action,
            "status": self.status,
            "payload": dict(self.payload),
        }


def review_milestone(
    wallet: "Wallet",
    *,
    agreement_id: str,
    milestone_id: str,
    approve: bool,
    reason: str | None = None,
    resolution: Mapping[str, Any] | None = None,
) -> MilestoneDisputeResult:
    if approve:
        payload = wallet.client.release_milestone(agreement_id, milestone_id)
        return MilestoneDisputeResult(
            agreement_id=agreement_id,
            milestone_id=milestone_id,
            action="release",
            status=str((payload.get("milestone") or payload).get("status") or "released"),
            payload=dict(payload),
        )
    payload = wallet.client.dispute_milestone(
        agreement_id,
        milestone_id,
        {"reason": reason or "Operator disputed milestone outcome.", "resolution": dict(resolution or {})},
    )
    return MilestoneDisputeResult(
        agreement_id=agreement_id,
        milestone_id=milestone_id,
        action="dispute",
        status=str((payload.get("milestone") or payload).get("status") or "disputed"),
        payload=dict(payload),
    )


def resolve_milestone_dispute(
    wallet: "Wallet",
    *,
    agreement_id: str,
    milestone_id: str,
    resolution: Mapping[str, Any],
) -> MilestoneDisputeResult:
    payload = wallet.client.resolve_milestone(agreement_id, milestone_id, dict(resolution))
    return MilestoneDisputeResult(
        agreement_id=agreement_id,
        milestone_id=milestone_id,
        action="resolve",
        status=str((payload.get("milestone") or payload).get("status") or "resolved"),
        payload=dict(payload),
    )


async def review_milestone_async(
    wallet: "AsyncWallet",
    *,
    agreement_id: str,
    milestone_id: str,
    approve: bool,
    reason: str | None = None,
    resolution: Mapping[str, Any] | None = None,
) -> MilestoneDisputeResult:
    if approve:
        payload = await wallet.client.release_milestone(agreement_id, milestone_id)
        return MilestoneDisputeResult(
            agreement_id=agreement_id,
            milestone_id=milestone_id,
            action="release",
            status=str((payload.get("milestone") or payload).get("status") or "released"),
            payload=dict(payload),
        )
    payload = await wallet.client.dispute_milestone(
        agreement_id,
        milestone_id,
        {"reason": reason or "Operator disputed milestone outcome.", "resolution": dict(resolution or {})},
    )
    return MilestoneDisputeResult(
        agreement_id=agreement_id,
        milestone_id=milestone_id,
        action="dispute",
        status=str((payload.get("milestone") or payload).get("status") or "disputed"),
        payload=dict(payload),
    )


async def resolve_milestone_dispute_async(
    wallet: "AsyncWallet",
    *,
    agreement_id: str,
    milestone_id: str,
    resolution: Mapping[str, Any],
) -> MilestoneDisputeResult:
    payload = await wallet.client.resolve_milestone(agreement_id, milestone_id, dict(resolution))
    return MilestoneDisputeResult(
        agreement_id=agreement_id,
        milestone_id=milestone_id,
        action="resolve",
        status=str((payload.get("milestone") or payload).get("status") or "resolved"),
        payload=dict(payload),
    )
