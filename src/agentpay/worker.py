from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from .client import AsyncWallet, Wallet
from .runtime import AsyncGovernedActionRun, GovernedActionRun, GovernedExecutionRecord
from .webhooks import VerifiedWebhookRequest


@dataclass(frozen=True)
class WorkerTaskResult:
    name: str
    status: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "details": dict(self.details),
        }


def poll_queued_approvals(wallet: Wallet) -> list[dict[str, Any]]:
    return [approval.to_dict() for approval in wallet.pending_approvals()]


async def poll_queued_approvals_async(wallet: AsyncWallet) -> list[dict[str, Any]]:
    return [approval.to_dict() for approval in await wallet.pending_approvals()]


def resume_governed_run(
    run: GovernedActionRun,
    callback: Callable[[], Any],
    *,
    timeout_seconds: float = 60.0,
    poll_interval_seconds: float = 2.0,
    receipt_id: str | None = None,
    evidence: Mapping[str, Any] | Callable[..., Mapping[str, Any] | None] | None = None,
) -> GovernedExecutionRecord:
    decision = run.wait_for_approval(timeout_seconds=timeout_seconds, poll_interval_seconds=poll_interval_seconds)
    if decision.status != "approved":
        return run.fail(error=f"Governed run did not become approved. Current status: {decision.status}", receipt_id=receipt_id, evidence=evidence)
    return run.execute(callback, receipt_id=receipt_id, evidence=evidence)


async def resume_governed_run_async(
    run: AsyncGovernedActionRun,
    callback: Callable[[], Any],
    *,
    timeout_seconds: float = 60.0,
    poll_interval_seconds: float = 2.0,
    receipt_id: str | None = None,
    evidence: Mapping[str, Any] | Callable[..., Mapping[str, Any] | None] | None = None,
) -> GovernedExecutionRecord:
    decision = await run.wait_for_approval(timeout_seconds=timeout_seconds, poll_interval_seconds=poll_interval_seconds)
    if decision.status != "approved":
        return await run.fail(error=f"Governed run did not become approved. Current status: {decision.status}", receipt_id=receipt_id, evidence=evidence)
    return await run.execute(callback, receipt_id=receipt_id, evidence=evidence)


def sync_audit_exports(wallet: Wallet) -> WorkerTaskResult:
    export = wallet.client.export_audit()
    return WorkerTaskResult(name="sync_audit_exports", status=export.status or "exported", details=export.to_dict())


async def sync_audit_exports_async(wallet: AsyncWallet) -> WorkerTaskResult:
    export = await wallet.client.export_audit()
    return WorkerTaskResult(name="sync_audit_exports", status=export.status or "exported", details=export.to_dict())


def resume_run_from_webhook(
    wallet: Wallet,
    request: VerifiedWebhookRequest,
    *,
    action_name: str,
    callback: Callable[[], Any],
    receipt_id: str | None = None,
    evidence: Mapping[str, Any] | Callable[..., Mapping[str, Any] | None] | None = None,
) -> GovernedExecutionRecord:
    decision = {
        "paymentIntent": request.payload.get("paymentIntent") or request.payload.get("intent") or {},
        "approval": request.payload.get("approval"),
        "requiresApproval": False,
    }
    run = wallet.resume_governed_action(decision, action_name=action_name)
    return run.execute(callback, receipt_id=receipt_id, evidence=evidence)


async def resume_run_from_webhook_async(
    wallet: AsyncWallet,
    request: VerifiedWebhookRequest,
    *,
    action_name: str,
    callback: Callable[[], Any],
    receipt_id: str | None = None,
    evidence: Mapping[str, Any] | Callable[..., Mapping[str, Any] | None] | None = None,
) -> GovernedExecutionRecord:
    decision = {
        "paymentIntent": request.payload.get("paymentIntent") or request.payload.get("intent") or {},
        "approval": request.payload.get("approval"),
        "requiresApproval": False,
    }
    run = wallet.resume_governed_action(decision, action_name=action_name)
    return await run.execute(callback, receipt_id=receipt_id, evidence=evidence)
