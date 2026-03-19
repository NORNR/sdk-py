from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Mapping, Protocol

from .accounting import AccountingBatch, AccountingBridge, AccountingDelivery, AccountingWorker
from .client import AgentPayClient, Wallet
from .money import usd_decimal, usd_text


class _WorkflowClientLike(Protocol):
    def get_monthly_statement(self, month: str | None = None) -> Any: ...
    def get_audit_review(self, fmt: str = "json") -> Any: ...
    def get_cost_report(self, fmt: str = "json") -> Any: ...
    def get_weekly_review(self) -> Any: ...
    def list_webhook_deliveries(self) -> Any: ...


def _coerce_client(source: AgentPayClient | Wallet | _WorkflowClientLike) -> _WorkflowClientLike:
    if isinstance(source, Wallet):
        return source.client
    return source


def _money(payload: Mapping[str, Any] | None, *keys: str) -> Decimal:
    if not payload:
        return usd_decimal(0)
    for key in keys:
        if payload.get(key) is not None:
            return usd_decimal(payload.get(key))
    return usd_decimal(0)


@dataclass(frozen=True)
class FinanceWorkflowAction:
    label: str
    status: str
    detail: str


@dataclass(frozen=True)
class FinanceCloseBundle:
    month: str
    workspace_label: str
    monthly_statement: dict[str, Any]
    weekly_review: dict[str, Any]
    audit_review: dict[str, Any]
    cost_report: dict[str, Any]
    accounting_batch: AccountingBatch
    provider_payloads: dict[str, Any]
    matched_deliveries: list[AccountingDelivery]

    @property
    def delivery_count(self) -> int:
        return len(self.matched_deliveries)

    @property
    def finance_packet_score(self) -> float:
        packet = self.audit_review.get("financePacket") if isinstance(self.audit_review, Mapping) else None
        if isinstance(packet, Mapping):
            return float(usd_decimal(packet.get("score")))
        return 0.0

    @property
    def close_ready(self) -> bool:
        return (
            any(bool(payload) for payload in self.provider_payloads.values())
            and self.delivery_count > 0
            and self.finance_packet_score >= 85
        )

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "month": self.month,
            "workspaceLabel": self.workspace_label,
            "providerPayloads": sorted(self.provider_payloads.keys()),
            "matchedDeliveries": self.delivery_count,
            "accountingBatch": self.accounting_batch.to_dict(),
            "financePacketScore": self.finance_packet_score,
            "closeReady": self.close_ready,
        }


@dataclass(frozen=True)
class FinanceWorkflowReport:
    workflow_name: str
    headline: str
    operator_posture: str
    actions: list[FinanceWorkflowAction] = field(default_factory=list)
    bundle: FinanceCloseBundle | None = None
    exported_payload: dict[str, Any] | None = None
    severity: str = "healthy"

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "workflowName": self.workflow_name,
            "headline": self.headline,
            "operatorPosture": self.operator_posture,
            "severity": self.severity,
            "actions": [action.__dict__ for action in self.actions],
            "bundle": self.bundle.to_summary_dict() if self.bundle else None,
            "exportedPayloadKeys": sorted((self.exported_payload or {}).keys()),
        }


def build_finance_close_bundle(
    source: AgentPayClient | Wallet | _WorkflowClientLike,
    *,
    month: str | None = None,
    workspace_label: str = "NORNR workspace",
    providers: tuple[str, ...] = ("quickbooks", "xero", "fortnox"),
) -> FinanceCloseBundle:
    client = _coerce_client(source)
    bridge = AccountingBridge(source, workspace_label=workspace_label)
    worker = AccountingWorker(source, workspace_label=workspace_label)
    accounting_batch = bridge.build_batch(month=month)
    provider_payloads = {provider: accounting_batch.for_provider(provider) for provider in providers}
    return FinanceCloseBundle(
        month=accounting_batch.month,
        workspace_label=workspace_label,
        monthly_statement=dict(client.get_monthly_statement(month) or {}),
        weekly_review=dict(client.get_weekly_review() or {}),
        audit_review=dict(client.get_audit_review() or {}),
        cost_report=dict(client.get_cost_report() or {}),
        accounting_batch=accounting_batch,
        provider_payloads=provider_payloads,
        matched_deliveries=worker.matching_deliveries(),
    )


def run_weekly_finance_handoff(
    source: AgentPayClient | Wallet | _WorkflowClientLike,
    *,
    workspace_label: str = "NORNR workspace",
    provider: str | None = None,
) -> FinanceWorkflowReport:
    client = _coerce_client(source)
    weekly_review = dict(client.get_weekly_review() or {})
    audit_review = dict(client.get_audit_review() or {})
    finance = dict(weekly_review.get("finance") or {})
    finance_packet = dict(audit_review.get("financePacket") or {})
    score = finance_packet.get("score")
    spend = _money(finance, "totalSpendUsd", "spendUsd")
    actions = [
        FinanceWorkflowAction(
            label="Weekly review",
            status="ready",
            detail=str(weekly_review.get("headline") or "Compile the 7-day operator and finance brief."),
        ),
        FinanceWorkflowAction(
            label="Finance packet",
            status="watch" if (score or 0) < 85 else "healthy",
            detail=f"Finance packet score {score if score is not None else 'n/a'} with governed spend at ${usd_text(spend)}.",
        ),
    ]
    exported_payload = None
    if provider:
        exported_payload = AccountingBridge(source, workspace_label=workspace_label).export_for_provider(provider)
        actions.append(
            FinanceWorkflowAction(
                label=f"{provider.title()} export",
                status="ready",
                detail=f"Accounting payload prepared for {provider}.",
            )
        )
    return FinanceWorkflowReport(
        workflow_name="weekly_finance_handoff",
        headline=str(weekly_review.get("headline") or "Weekly NORNR finance handoff ready"),
        operator_posture="Finance review stays armed while approvals, anomalies and evidence remain inside one packet.",
        actions=actions,
        exported_payload=exported_payload,
        severity="watch" if (score or 0) < 85 else "healthy",
    )


def run_monthly_close(
    source: AgentPayClient | Wallet | _WorkflowClientLike,
    *,
    month: str | None = None,
    provider: str = "quickbooks",
    workspace_label: str = "NORNR workspace",
) -> FinanceWorkflowReport:
    bundle = build_finance_close_bundle(source, month=month, workspace_label=workspace_label)
    review = bundle.audit_review
    finance_packet = dict(review.get("financePacket") or {})
    actions = [
        FinanceWorkflowAction(
            label="Statement",
            status="ready",
            detail=f"Monthly statement for {bundle.month} is attached to the close bundle.",
        ),
        FinanceWorkflowAction(
            label="Provider export",
            status="ready",
            detail=f"{provider.title()} journal payload prepared from the same governed trail.",
        ),
        FinanceWorkflowAction(
            label="Receipts + webhooks",
            status="watch" if not bundle.matched_deliveries else "ready",
            detail=f"{len(bundle.matched_deliveries)} webhook deliveries matched the close window.",
        ),
        FinanceWorkflowAction(
            label="Finance packet",
            status="watch" if (finance_packet.get("score") or 0) < 85 else "healthy",
            detail=f"Finance packet score {finance_packet.get('score', 'n/a')} and close narrative remain attached to the export.",
        ),
    ]
    return FinanceWorkflowReport(
        workflow_name="monthly_close",
        headline=f"Monthly NORNR close bundle ready for {bundle.month}",
        operator_posture="Close packages, exports and receipt proof remain sourced from the same governed audit trail.",
        actions=actions,
        bundle=bundle,
        exported_payload=bundle.provider_payloads.get(provider),
        severity="watch" if not bundle.close_ready else "healthy",
    )
