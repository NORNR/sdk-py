from __future__ import annotations

import inspect
import time
from uuid import uuid4
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Mapping

from .models import DecisionRecord, ReceiptRecord

if TYPE_CHECKING:
    from .client import AsyncWallet, Wallet


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _default_evidence(
    *,
    action_name: str,
    callback_result: Any = None,
    callback_error: str | None = None,
    business_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "actionName": action_name,
        "capturedAt": _iso_now(),
    }
    if business_context:
        evidence["businessContext"] = dict(business_context)
    if callback_result is not None:
        if hasattr(callback_result, "to_dict"):
            evidence["result"] = callback_result.to_dict()
        elif hasattr(callback_result, "to_summary_dict"):
            evidence["result"] = callback_result.to_summary_dict()
        elif isinstance(callback_result, Mapping):
            evidence["result"] = dict(callback_result)
        else:
            evidence["resultPreview"] = str(callback_result)
    if callback_error:
        evidence["error"] = callback_error
    return evidence


def _resolve_evidence(
    evidence: Mapping[str, Any] | Callable[..., Mapping[str, Any] | None] | None,
    *,
    action_name: str,
    callback_result: Any = None,
    callback_error: str | None = None,
    business_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload: Mapping[str, Any] | None
    if callable(evidence):
        payload = evidence(callback_result, callback_error)
    else:
        payload = evidence
    merged = _default_evidence(
        action_name=action_name,
        callback_result=callback_result,
        callback_error=callback_error,
        business_context=business_context,
    )
    if payload:
        merged.update(dict(payload))
    return merged


@dataclass(frozen=True)
class GovernedExecutionRecord:
    action_name: str
    decision: DecisionRecord
    execution_status: str
    started_at: str
    finished_at: str
    duration_ms: int
    executed: bool
    result: Any = None
    error: str | None = None
    receipt: ReceiptRecord | None = None
    evidence: dict[str, Any] | None = None
    _raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @property
    def approval_url(self) -> str | None:
        return self.decision.approval_url

    @property
    def payment_intent_id(self) -> str | None:
        return self.decision.payment_intent.id

    @property
    def requires_handoff(self) -> bool:
        return self.execution_status in {"queued", "blocked"}

    def to_summary_dict(self) -> dict[str, Any]:
        result_preview = self.result
        if hasattr(result_preview, "to_summary_dict"):
            result_preview = result_preview.to_summary_dict()
        elif hasattr(result_preview, "to_dict"):
            result_preview = result_preview.to_dict()
        return {
            "actionName": self.action_name,
            "paymentIntentId": self.payment_intent_id,
            "decisionStatus": self.decision.status,
            "executionStatus": self.execution_status,
            "executed": self.executed,
            "durationMs": self.duration_ms,
            "approvalUrl": self.approval_url,
            "receiptId": self.receipt.id if self.receipt else None,
            "error": self.error,
            "result": result_preview,
        }

    def to_handoff_dict(self) -> dict[str, Any]:
        return {
            "actionName": self.action_name,
            "paymentIntentId": self.payment_intent_id,
            "status": self.execution_status,
            "approvalUrl": self.approval_url,
            "decision": self.decision.to_summary_dict(),
        }


class GovernedExecutionError(RuntimeError):
    def __init__(self, record: GovernedExecutionRecord) -> None:
        super().__init__(record.error or f"Governed action {record.action_name} failed")
        self.record = record


class QueuedForApprovalError(GovernedExecutionError):
    pass


class BlockedByPolicyError(GovernedExecutionError):
    pass


class AnomalyEscalatedError(GovernedExecutionError):
    pass


class ReceiptEvidenceMissingError(GovernedExecutionError):
    pass


@dataclass(frozen=True)
class GovernedHandoffRecord:
    action_name: str
    run_id: str
    intent_key: str
    idempotency_key: str
    status: str
    payment_intent_id: str | None
    approval_id: str | None
    approval_url: str | None
    reason: str
    business_context: dict[str, Any]
    decision: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "actionName": self.action_name,
            "runId": self.run_id,
            "intentKey": self.intent_key,
            "idempotencyKey": self.idempotency_key,
            "status": self.status,
            "paymentIntentId": self.payment_intent_id,
            "approvalId": self.approval_id,
            "approvalUrl": self.approval_url,
            "reason": self.reason,
            "businessContext": dict(self.business_context),
            "decision": dict(self.decision or {}),
        }


@dataclass
class GovernedActionRun:
    wallet: "Wallet"
    action_name: str
    decision: DecisionRecord
    requested_amount_usd: float
    requested_counterparty: str
    purpose: str
    run_id: str
    intent_key: str
    idempotency_key: str
    business_context: dict[str, Any] | None = None

    @property
    def approved(self) -> bool:
        return self.decision.status == "approved"

    @property
    def blocked(self) -> bool:
        return self.decision.status == "blocked"

    @property
    def queued(self) -> bool:
        return self.decision.status == "queued"

    def to_handoff_dict(self) -> dict[str, Any]:
        return self.to_handoff_record().to_dict()

    def to_handoff_record(self) -> GovernedHandoffRecord:
        reason = "Approval is required before execution can continue." if self.queued else "Policy blocked execution."
        return GovernedHandoffRecord(
            action_name=self.action_name,
            run_id=self.run_id,
            intent_key=self.intent_key,
            idempotency_key=self.idempotency_key,
            status=self.decision.status,
            payment_intent_id=self.decision.payment_intent.id,
            approval_id=self.decision.approval.id if self.decision.approval else None,
            approval_url=self.decision.approval_url,
            reason=reason,
            business_context=dict(self.business_context or {}),
            decision=self.decision.to_summary_dict(),
        )

    def approve(self, *, comment: str | None = None) -> Any:
        return self.wallet.approve_if_needed(self.decision, comment=comment)

    def reject(self, *, comment: str | None = None) -> Any:
        if not self.decision.approval or not self.decision.approval.id:
            from .client import ApprovalRequiredError

            raise ApprovalRequiredError.from_decision(self.decision)
        return self.wallet.reject(self.decision.approval.id, comment=comment)

    def attach_receipt_evidence(self, receipt_id: str, payload: Mapping[str, Any]) -> ReceiptRecord:
        return self.wallet.client.attach_receipt_evidence(receipt_id, dict(payload))

    def attach_evidence(self, receipt_id: str, payload: Mapping[str, Any]) -> ReceiptRecord:
        return self.attach_receipt_evidence(receipt_id, payload)

    def attach_receipt(self, receipt_id: str, *, evidence: Mapping[str, Any] | None = None) -> ReceiptRecord:
        return self.attach_receipt_evidence(receipt_id, evidence or {"actionName": self.action_name, "attachedAt": _iso_now()})

    def finalize(
        self,
        *,
        callback_result: Any = None,
        callback_error: str | None = None,
        receipt_id: str | None = None,
        evidence: Mapping[str, Any] | Callable[..., Mapping[str, Any] | None] | None = None,
        started_at: str,
        finished_at: str,
        duration_ms: int,
        executed: bool,
    ) -> GovernedExecutionRecord:
        resolved_evidence = _resolve_evidence(
            evidence,
            action_name=self.action_name,
            callback_result=callback_result,
            callback_error=callback_error,
            business_context=self.business_context,
        )
        receipt = self.attach_receipt_evidence(receipt_id, resolved_evidence) if receipt_id else None
        execution_status = "succeeded" if executed and not callback_error else self.decision.status
        if executed and callback_error:
            execution_status = "failed"
        if not executed:
            execution_status = self.decision.status
        return GovernedExecutionRecord(
            action_name=self.action_name,
            decision=self.decision,
            execution_status=execution_status,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            executed=executed,
            result=callback_result,
            error=callback_error,
            receipt=receipt,
            evidence=resolved_evidence,
            _raw={
                "actionName": self.action_name,
                "decision": self.decision.to_dict(),
                "executionStatus": execution_status,
                "startedAt": started_at,
                "finishedAt": finished_at,
                "durationMs": duration_ms,
                "executed": executed,
                "error": callback_error,
                "receipt": receipt.to_dict() if receipt else None,
                "evidence": resolved_evidence,
            },
        )

    def complete(
        self,
        *,
        callback_result: Any = None,
        receipt_id: str | None = None,
        evidence: Mapping[str, Any] | Callable[..., Mapping[str, Any] | None] | None = None,
        require_receipt: bool = False,
    ) -> GovernedExecutionRecord:
        if receipt_id is None and require_receipt:
            raise ReceiptEvidenceMissingError(
                GovernedExecutionRecord(
                    action_name=self.action_name,
                    decision=self.decision,
                    execution_status="failed",
                    started_at=_iso_now(),
                    finished_at=_iso_now(),
                    duration_ms=0,
                    executed=True,
                    error="receipt_id is required to complete a governed action explicitly",
                )
            )
        return self.finalize(
            callback_result=callback_result,
            receipt_id=receipt_id,
            evidence=evidence,
            started_at=_iso_now(),
            finished_at=_iso_now(),
            duration_ms=0,
            executed=True,
        )

    def fail(
        self,
        *,
        error: str,
        receipt_id: str | None = None,
        evidence: Mapping[str, Any] | Callable[..., Mapping[str, Any] | None] | None = None,
    ) -> GovernedExecutionRecord:
        return self.finalize(
            callback_error=error,
            receipt_id=receipt_id,
            evidence=evidence,
            started_at=_iso_now(),
            finished_at=_iso_now(),
            duration_ms=0,
            executed=True,
        )

    def refresh(self) -> DecisionRecord:
        bootstrap = self.wallet.refresh()
        pending = [
            item for item in bootstrap.get("approvals", []) or []
            if str(item.get("paymentIntentId") or "") == str(self.decision.payment_intent.id or "")
        ]
        if pending:
            approval = dict(pending[0])
            approval["approvalUrl"] = self.decision.approval_url
            self.decision = DecisionRecord.from_payload(
                {
                    "paymentIntent": self.decision.payment_intent.to_dict(),
                    "approval": approval,
                    "requiresApproval": True,
                }
            )
            return self.decision
        timeline = self.wallet.timeline()
        entry = next(
            (
                item
                for item in timeline.entries
                if str(item.get("paymentIntentId") or item.get("id") or "") == str(self.decision.payment_intent.id or "")
            ),
            None,
        )
        if entry:
            payment_intent = {**self.decision.payment_intent.to_dict(), "status": entry.get("status") or self.decision.status}
            self.decision = DecisionRecord.from_payload(
                {
                    "paymentIntent": payment_intent,
                    "approval": None,
                    "requiresApproval": False,
                }
            )
        return self.decision

    def wait_for_approval(self, *, timeout_seconds: float = 60.0, poll_interval_seconds: float = 2.0) -> DecisionRecord:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() <= deadline:
            refreshed = self.refresh()
            if refreshed.status != "queued":
                return refreshed
            time.sleep(poll_interval_seconds)
        return self.decision

    def execute(
        self,
        callback: Callable[[], Any],
        *,
        receipt_id: str | None = None,
        evidence: Mapping[str, Any] | Callable[..., Mapping[str, Any] | None] | None = None,
        raise_on_error: bool = True,
    ) -> GovernedExecutionRecord:
        started_monotonic = time.monotonic()
        started_at = _iso_now()
        if not self.approved:
            return self.finalize(
                started_at=started_at,
                finished_at=_iso_now(),
                duration_ms=0,
                executed=False,
                receipt_id=receipt_id,
                evidence=evidence,
            )
        try:
            callback_result = callback()
        except Exception as exc:
            record = self.finalize(
                callback_error=str(exc),
                receipt_id=receipt_id,
                evidence=evidence,
                started_at=started_at,
                finished_at=_iso_now(),
                duration_ms=int((time.monotonic() - started_monotonic) * 1000),
                executed=True,
            )
            if raise_on_error:
                if self.decision.status == "queued":
                    raise QueuedForApprovalError(record) from exc
                if self.decision.status == "blocked":
                    raise BlockedByPolicyError(record) from exc
                raise GovernedExecutionError(record) from exc
            return record
        return self.finalize(
            callback_result=callback_result,
            receipt_id=receipt_id,
            evidence=evidence,
            started_at=started_at,
            finished_at=_iso_now(),
            duration_ms=int((time.monotonic() - started_monotonic) * 1000),
            executed=True,
        )


@dataclass
class AsyncGovernedActionRun:
    wallet: "AsyncWallet"
    action_name: str
    decision: DecisionRecord
    requested_amount_usd: float
    requested_counterparty: str
    purpose: str
    run_id: str
    intent_key: str
    idempotency_key: str
    business_context: dict[str, Any] | None = None

    @property
    def approved(self) -> bool:
        return self.decision.status == "approved"

    @property
    def blocked(self) -> bool:
        return self.decision.status == "blocked"

    @property
    def queued(self) -> bool:
        return self.decision.status == "queued"

    def to_handoff_dict(self) -> dict[str, Any]:
        return self.to_handoff_record().to_dict()

    def to_handoff_record(self) -> GovernedHandoffRecord:
        reason = "Approval is required before execution can continue." if self.queued else "Policy blocked execution."
        return GovernedHandoffRecord(
            action_name=self.action_name,
            run_id=self.run_id,
            intent_key=self.intent_key,
            idempotency_key=self.idempotency_key,
            status=self.decision.status,
            payment_intent_id=self.decision.payment_intent.id,
            approval_id=self.decision.approval.id if self.decision.approval else None,
            approval_url=self.decision.approval_url,
            reason=reason,
            business_context=dict(self.business_context or {}),
            decision=self.decision.to_summary_dict(),
        )

    async def approve(self, *, comment: str | None = None) -> Any:
        return await self.wallet.approve_if_needed(self.decision, comment=comment)

    async def reject(self, *, comment: str | None = None) -> Any:
        if not self.decision.approval or not self.decision.approval.id:
            from .client import ApprovalRequiredError

            raise ApprovalRequiredError.from_decision(self.decision)
        return await self.wallet.reject(self.decision.approval.id, comment=comment)

    async def attach_receipt_evidence(self, receipt_id: str, payload: Mapping[str, Any]) -> ReceiptRecord:
        return await self.wallet.client.attach_receipt_evidence(receipt_id, dict(payload))

    async def attach_evidence(self, receipt_id: str, payload: Mapping[str, Any]) -> ReceiptRecord:
        return await self.attach_receipt_evidence(receipt_id, payload)

    async def attach_receipt(self, receipt_id: str, *, evidence: Mapping[str, Any] | None = None) -> ReceiptRecord:
        return await self.attach_receipt_evidence(receipt_id, evidence or {"actionName": self.action_name, "attachedAt": _iso_now()})

    async def finalize(
        self,
        *,
        callback_result: Any = None,
        callback_error: str | None = None,
        receipt_id: str | None = None,
        evidence: Mapping[str, Any] | Callable[..., Mapping[str, Any] | None] | None = None,
        started_at: str,
        finished_at: str,
        duration_ms: int,
        executed: bool,
    ) -> GovernedExecutionRecord:
        resolved_evidence = _resolve_evidence(
            evidence,
            action_name=self.action_name,
            callback_result=callback_result,
            callback_error=callback_error,
            business_context=self.business_context,
        )
        receipt = await self.attach_receipt_evidence(receipt_id, resolved_evidence) if receipt_id else None
        execution_status = "succeeded" if executed and not callback_error else self.decision.status
        if executed and callback_error:
            execution_status = "failed"
        if not executed:
            execution_status = self.decision.status
        return GovernedExecutionRecord(
            action_name=self.action_name,
            decision=self.decision,
            execution_status=execution_status,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            executed=executed,
            result=callback_result,
            error=callback_error,
            receipt=receipt,
            evidence=resolved_evidence,
            _raw={
                "actionName": self.action_name,
                "decision": self.decision.to_dict(),
                "executionStatus": execution_status,
                "startedAt": started_at,
                "finishedAt": finished_at,
                "durationMs": duration_ms,
                "executed": executed,
                "error": callback_error,
                "receipt": receipt.to_dict() if receipt else None,
                "evidence": resolved_evidence,
            },
        )

    async def complete(
        self,
        *,
        callback_result: Any = None,
        receipt_id: str | None = None,
        evidence: Mapping[str, Any] | Callable[..., Mapping[str, Any] | None] | None = None,
        require_receipt: bool = False,
    ) -> GovernedExecutionRecord:
        if receipt_id is None and require_receipt:
            raise ReceiptEvidenceMissingError(
                GovernedExecutionRecord(
                    action_name=self.action_name,
                    decision=self.decision,
                    execution_status="failed",
                    started_at=_iso_now(),
                    finished_at=_iso_now(),
                    duration_ms=0,
                    executed=True,
                    error="receipt_id is required to complete a governed action explicitly",
                )
            )
        return await self.finalize(
            callback_result=callback_result,
            receipt_id=receipt_id,
            evidence=evidence,
            started_at=_iso_now(),
            finished_at=_iso_now(),
            duration_ms=0,
            executed=True,
        )

    async def fail(
        self,
        *,
        error: str,
        receipt_id: str | None = None,
        evidence: Mapping[str, Any] | Callable[..., Mapping[str, Any] | None] | None = None,
    ) -> GovernedExecutionRecord:
        return await self.finalize(
            callback_error=error,
            receipt_id=receipt_id,
            evidence=evidence,
            started_at=_iso_now(),
            finished_at=_iso_now(),
            duration_ms=0,
            executed=True,
        )

    async def refresh(self) -> DecisionRecord:
        bootstrap = await self.wallet.refresh()
        pending = [
            item for item in bootstrap.get("approvals", []) or []
            if str(item.get("paymentIntentId") or "") == str(self.decision.payment_intent.id or "")
        ]
        if pending:
            approval = dict(pending[0])
            approval["approvalUrl"] = self.decision.approval_url
            self.decision = DecisionRecord.from_payload(
                {
                    "paymentIntent": self.decision.payment_intent.to_dict(),
                    "approval": approval,
                    "requiresApproval": True,
                }
            )
            return self.decision
        timeline = await self.wallet.timeline()
        entry = next(
            (
                item
                for item in timeline.entries
                if str(item.get("paymentIntentId") or item.get("id") or "") == str(self.decision.payment_intent.id or "")
            ),
            None,
        )
        if entry:
            payment_intent = {**self.decision.payment_intent.to_dict(), "status": entry.get("status") or self.decision.status}
            self.decision = DecisionRecord.from_payload(
                {
                    "paymentIntent": payment_intent,
                    "approval": None,
                    "requiresApproval": False,
                }
            )
        return self.decision

    async def wait_for_approval(self, *, timeout_seconds: float = 60.0, poll_interval_seconds: float = 2.0) -> DecisionRecord:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() <= deadline:
            refreshed = await self.refresh()
            if refreshed.status != "queued":
                return refreshed
            await __import__("asyncio").sleep(poll_interval_seconds)
        return self.decision

    async def execute(
        self,
        callback: Callable[[], Any | Awaitable[Any]],
        *,
        receipt_id: str | None = None,
        evidence: Mapping[str, Any] | Callable[..., Mapping[str, Any] | None] | None = None,
        raise_on_error: bool = True,
    ) -> GovernedExecutionRecord:
        started_monotonic = time.monotonic()
        started_at = _iso_now()
        if not self.approved:
            return await self.finalize(
                started_at=started_at,
                finished_at=_iso_now(),
                duration_ms=0,
                executed=False,
                receipt_id=receipt_id,
                evidence=evidence,
            )
        try:
            callback_result = callback()
            if inspect.isawaitable(callback_result):
                callback_result = await callback_result
        except Exception as exc:
            record = await self.finalize(
                callback_error=str(exc),
                receipt_id=receipt_id,
                evidence=evidence,
                started_at=started_at,
                finished_at=_iso_now(),
                duration_ms=int((time.monotonic() - started_monotonic) * 1000),
                executed=True,
            )
            if raise_on_error:
                if self.decision.status == "queued":
                    raise QueuedForApprovalError(record) from exc
                if self.decision.status == "blocked":
                    raise BlockedByPolicyError(record) from exc
                raise GovernedExecutionError(record) from exc
            return record
        return await self.finalize(
            callback_result=callback_result,
            receipt_id=receipt_id,
            evidence=evidence,
            started_at=started_at,
            finished_at=_iso_now(),
            duration_ms=int((time.monotonic() - started_monotonic) * 1000),
            executed=True,
        )


def default_run_ids(action_name: str) -> tuple[str, str, str]:
    base = f"{action_name}:{uuid4().hex}"
    return base, f"intent:{base}", f"idempotency:{base}"
