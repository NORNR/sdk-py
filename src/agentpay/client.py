from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, cast

from .auth import DEFAULT_BASE_URL, load_login
from .budgeting import BudgetContext, budget as budget_scope, current_budget_scope
from .breakers import CircuitBreakerConfig, LocalCircuitBreaker
from .context import merge_business_context
from .counterparty import CounterpartyReview, review_counterparty as review_counterparty_sync, review_counterparty_async
from .delegation import DelegatedMandate, create_delegated_mandate, create_delegated_mandate_async
from .intent import IntentCheckRecord
from .models import (
    AnomalyRecord,
    ApiKeyRecord,
    ApiKeyTemplateRecord,
    AuditExportRecord,
    ApprovalChainRecord,
    ApprovalRecord,
    AuditReviewRecord,
    BalanceRecord,
    BudgetCapRecord,
    ComplianceRecord,
    CostReportRecord,
    DecisionRecord,
    EcosystemDirectoryRecord,
    EventRecord,
    FinancePacketRecord,
    HardwareBindingRecord,
    IdentityRecord,
    InteropValidationRecord,
    KillSwitchRecord,
    LedgerEntryRecord,
    MonthlyStatementRecord,
    PolicyPackApplyRecord,
    PolicyPackCatalogRecord,
    PolicyPackDetailRecord,
    PolicyPackReplayResultRecord,
    PolicyPackRollbackRecord,
    PolicyTemplateRecord,
    PolicyWorkbenchRecord,
    PolicySimulationRecord,
    ReceiptRecord,
    ReconciliationRecord,
    ReputationRecord,
    SettlementJobRecord,
    SettlementRunRecord,
    SignedArtifactRecord,
    TaxProfileRecord,
    TimelineReportRecord,
    TrustTierRecord,
    TrustManifestRecord,
    TrustProfileRecord,
    WalletStateRecord,
    WebhookDeliveryRecord,
    WebhookDrainRecord,
    WebhookRecord,
    WeeklyExpenseReportRecord,
    WeeklyReviewRecord,
    AgreementStandardRecord,
)
from .money import AmountLike, usd_decimal, usd_float, usd_text
from .replay import merge_replay_context
from .runtime import AsyncGovernedActionRun, GovernedActionRun, GovernedExecutionRecord, default_run_ids
from .transport import AsyncHttpTransport, SyncHttpTransport, TransportConfig


class AgentPayError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        payload: Any = None,
        request_id: str | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload
        self.request_id = request_id
        self.retryable = retryable


class AuthenticationError(AgentPayError):
    pass


class ValidationError(AgentPayError):
    pass


class RateLimitError(AgentPayError):
    pass


class TransportError(AgentPayError):
    pass


class ApprovalRequiredError(AgentPayError):
    @classmethod
    def from_decision(cls, decision: DecisionRecord) -> "ApprovalRequiredError":
        approval_url = decision.approval_url
        message = f"NORNR returned {decision.status} for {decision.payment_intent.counterparty or 'unknown counterparty'}"
        if approval_url:
            message = f"{message}. Approve it here: {approval_url}"
        return cls(
            message,
            payload=decision.to_dict(),
            retryable=decision.status == "queued",
        )


@dataclass(frozen=True)
class _RequestOptions:
    method: str = "GET"
    body: Any = None
    authenticated: bool = True
    parse_json: bool = True


def _items_payload(payload: Any, *keys: str) -> list[Any]:
    if isinstance(payload, Mapping):
        for key in ("items", *keys):
            items = payload.get(key)
            if isinstance(items, list):
                return list(items)
    if isinstance(payload, list):
        return list(payload)
    return []


def _coerce_error(status_code: int, payload: Any, fallback: str) -> AgentPayError:
    message = payload.get("message") if isinstance(payload, dict) else fallback
    request_id = payload.get("requestId") if isinstance(payload, dict) else None
    if status_code == 401:
        return AuthenticationError(message or fallback, status_code=status_code, payload=payload, request_id=request_id)
    if status_code == 429:
        return RateLimitError(message or fallback, status_code=status_code, payload=payload, request_id=request_id, retryable=True)
    if status_code >= 500:
        return TransportError(message or fallback, status_code=status_code, payload=payload, request_id=request_id, retryable=True)
    return ValidationError(message or fallback, status_code=status_code, payload=payload, request_id=request_id)


def _decode_payload(payload: str, parse_json: bool) -> Any:
    if not payload:
        return None
    return json.loads(payload) if parse_json else payload


def _control_room_url(base_url: str, approval_id: str | None) -> str | None:
    if not approval_id:
        return None
    root = base_url.rstrip("/")
    if root.endswith("/app"):
        root = root[: -len("/app")]
    return f"{root}/app/approvals/{approval_id}"


def _apply_business_context_tags(
    budget_tags: dict[str, str] | None,
    business_context: dict[str, Any] | None,
) -> dict[str, str] | None:
    merged = dict(budget_tags or {})
    if business_context:
        tags = business_context.get("tags") or {}
        for key, value in tags.items():
            merged[str(key)] = str(value)
        for source_key, target_key in {
            "ticketId": "ticketId",
            "customerSegment": "customerSegment",
            "priority": "priority",
            "sessionId": "sessionId",
            "threadId": "threadId",
        }.items():
            if business_context.get(source_key):
                merged[target_key] = str(business_context[source_key])
    return merged or None


class AgentPayClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str | None = None,
        *,
        timeout_seconds: float = 15.0,
        default_headers: Mapping[str, str] | None = None,
        transport: SyncHttpTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.default_headers = dict(default_headers or {})
        self.transport = transport or SyncHttpTransport(
            TransportConfig(timeout_seconds=timeout_seconds, default_headers=dict(self.default_headers)),
        )
        self._owns_transport = transport is None

    def with_api_key(self, api_key: str) -> "AgentPayClient":
        cloned = AgentPayClient(
            base_url=self.base_url,
            api_key=api_key,
            timeout_seconds=self.timeout_seconds,
            default_headers=self.default_headers,
            transport=self.transport,
        )
        cloned._owns_transport = False
        return cloned

    def with_timeout(self, timeout_seconds: float) -> "AgentPayClient":
        return AgentPayClient(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout_seconds=timeout_seconds,
            default_headers=self.default_headers,
        )

    def close(self) -> None:
        if self._owns_transport:
            self.transport.close()

    def __enter__(self) -> "AgentPayClient":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def onboard(self, payload: dict[str, Any]) -> Any:
        return self._request("/api/onboarding", _RequestOptions(method="POST", body=payload, authenticated=False))

    def get_bootstrap(self) -> Any:
        return self._request("/api/bootstrap")

    def create_agent(self, payload: dict[str, Any]) -> Any:
        return self._request("/api/agents", _RequestOptions(method="POST", body=payload))

    def create_policy(self, agent_id: str, payload: dict[str, Any]) -> Any:
        return self._request(f"/api/agents/{agent_id}/policies", _RequestOptions(method="POST", body=payload))

    def list_policy_templates(self) -> list[PolicyTemplateRecord]:
        return [PolicyTemplateRecord.from_payload(item) for item in _items_payload(self._request("/api/policy-templates"), "templates")]

    def list_policy_packs(self) -> PolicyPackCatalogRecord:
        return PolicyPackCatalogRecord.from_payload(self._request("/api/policy-packs"))

    def get_policy_pack(self, pack_id: str) -> PolicyPackDetailRecord:
        return PolicyPackDetailRecord.from_payload(self._request(f"/api/policy-packs/{pack_id}"))

    def replay_policy_pack(self, pack_id: str, payload: dict[str, Any]) -> PolicyPackReplayResultRecord:
        return PolicyPackReplayResultRecord.from_payload(
            self._request(f"/api/policy-packs/{pack_id}/replay", _RequestOptions(method="POST", body=payload))
        )

    def apply_policy_pack(self, pack_id: str, payload: dict[str, Any]) -> PolicyPackApplyRecord:
        return PolicyPackApplyRecord.from_payload(
            self._request(f"/api/policy-packs/{pack_id}/apply", _RequestOptions(method="POST", body=payload))
        )

    def rollback_policy_pack(self, pack_id: str, payload: dict[str, Any] | None = None) -> PolicyPackRollbackRecord:
        return PolicyPackRollbackRecord.from_payload(
            self._request(f"/api/policy-packs/{pack_id}/rollback", _RequestOptions(method="POST", body=payload or {}))
        )

    def list_api_key_templates(self) -> list[ApiKeyTemplateRecord]:
        return [ApiKeyTemplateRecord.from_payload(item) for item in _items_payload(self._request("/api/api-key-templates"), "templates")]

    def list_budget_caps(self) -> list[BudgetCapRecord]:
        return [BudgetCapRecord.from_payload(item) for item in _items_payload(self._request("/api/budget-caps"))]

    def create_budget_cap(self, payload: dict[str, Any]) -> BudgetCapRecord:
        return BudgetCapRecord.from_payload(self._request("/api/budget-caps", _RequestOptions(method="POST", body=payload)))

    def simulate_policy(self, payload: dict[str, Any]) -> Any:
        return self._request("/api/policies/simulate", _RequestOptions(method="POST", body=payload))

    def diff_policy(self, payload: dict[str, Any]) -> Any:
        return self._request("/api/policies/diff", _RequestOptions(method="POST", body=payload))

    def list_anomalies(self) -> list[AnomalyRecord]:
        return [AnomalyRecord.from_payload(item) for item in _items_payload(self._request("/api/anomalies"))]

    def update_anomaly(self, anomaly_id: str, payload: dict[str, Any]) -> AnomalyRecord:
        return AnomalyRecord.from_payload(self._request(f"/api/anomalies/{anomaly_id}", _RequestOptions(method="POST", body=payload)))

    def create_payment_intent(self, payload: dict[str, Any]) -> Any:
        return self._request("/api/payments/intents", _RequestOptions(method="POST", body=payload))

    def get_identity(self) -> IdentityRecord:
        return IdentityRecord.from_payload(self._request("/api/identity"))

    def update_identity(self, payload: dict[str, Any]) -> IdentityRecord:
        return IdentityRecord.from_payload(self._request("/api/identity", _RequestOptions(method="POST", body=payload)))

    def get_compliance(self) -> ComplianceRecord:
        return ComplianceRecord.from_payload(self._request("/api/compliance"))

    def list_kill_switches(self) -> list[KillSwitchRecord]:
        raw = self._request("/api/compliance/kill-switches")
        items = raw.get("items") if isinstance(raw, Mapping) else raw
        return [KillSwitchRecord.from_payload(item) for item in items or []]

    def save_kill_switch(self, payload: dict[str, Any]) -> KillSwitchRecord:
        return KillSwitchRecord.from_payload(
            self._request("/api/compliance/kill-switches", _RequestOptions(method="POST", body=payload))
        )

    def list_approval_chains(self) -> list[ApprovalChainRecord]:
        raw = self._request("/api/compliance/approval-chains")
        items = raw.get("items") if isinstance(raw, Mapping) else raw
        return [ApprovalChainRecord.from_payload(item) for item in items or []]

    def save_approval_chain(self, payload: dict[str, Any]) -> ApprovalChainRecord:
        return ApprovalChainRecord.from_payload(
            self._request("/api/compliance/approval-chains", _RequestOptions(method="POST", body=payload))
        )

    def list_hardware_bindings(self) -> list[HardwareBindingRecord]:
        raw = self._request("/api/compliance/hardware-bindings")
        items = raw.get("items") if isinstance(raw, Mapping) else raw
        return [HardwareBindingRecord.from_payload(item) for item in items or []]

    def save_hardware_binding(self, payload: dict[str, Any]) -> HardwareBindingRecord:
        return HardwareBindingRecord.from_payload(
            self._request("/api/compliance/hardware-bindings", _RequestOptions(method="POST", body=payload))
        )

    def get_tax_profile(self) -> TaxProfileRecord:
        return TaxProfileRecord.from_payload(self._request("/api/compliance/tax-profile"))

    def update_tax_profile(self, payload: dict[str, Any]) -> TaxProfileRecord:
        return TaxProfileRecord.from_payload(
            self._request("/api/compliance/tax-profile", _RequestOptions(method="POST", body=payload))
        )

    def update_compliance_settings(self, payload: dict[str, Any]) -> ComplianceRecord:
        return ComplianceRecord.from_payload(self._request("/api/compliance/settings", _RequestOptions(method="POST", body=payload)))

    def get_weekly_expense_report(self) -> WeeklyExpenseReportRecord:
        return WeeklyExpenseReportRecord.from_payload(self._request("/api/workspace/expense-report"))

    def get_reputation(self) -> ReputationRecord:
        return ReputationRecord.from_payload(self._request("/api/reputation"))

    def get_trust_profile(self) -> TrustProfileRecord:
        return TrustProfileRecord.from_payload(self._request("/api/trust/profile"))

    def get_trust_tiers(self) -> list[TrustTierRecord]:
        return [TrustTierRecord.from_payload(item) for item in _items_payload(self._request("/api/trust/tiers"), "tiers")]

    def get_trust_manifest(self) -> TrustManifestRecord:
        return TrustManifestRecord.from_payload(self._request("/api/trust/manifest"))

    def get_signed_trust_manifest(self) -> SignedArtifactRecord:
        return SignedArtifactRecord.from_payload(self._request("/api/trust/manifest/signed"))

    def verify_trust_manifest(self, payload: dict[str, Any]) -> Any:
        return self._request("/api/trust/verify", _RequestOptions(method="POST", body=payload))

    def handshake_trust_manifest(self, payload: dict[str, Any]) -> Any:
        return self._request("/api/trust/handshake", _RequestOptions(method="POST", body=payload))

    def get_portable_reputation(self) -> ReputationRecord:
        return ReputationRecord.from_payload(self._request("/api/reputation/portable"))

    def get_signed_portable_reputation(self) -> SignedArtifactRecord:
        return SignedArtifactRecord.from_payload(self._request("/api/reputation/portable/signed"))

    def export_agreement_standard(self) -> AgreementStandardRecord:
        return AgreementStandardRecord.from_payload(self._request("/api/standards/agreements"))

    def export_signed_agreement_standard(self) -> SignedArtifactRecord:
        return SignedArtifactRecord.from_payload(self._request("/api/standards/agreements/signed"))

    def get_agreement_standard_schema(self) -> AgreementStandardRecord:
        return AgreementStandardRecord.from_payload(self._request("/api/standards/agreement-schema"))

    def get_ecosystem_directory(self) -> EcosystemDirectoryRecord:
        return EcosystemDirectoryRecord.from_payload(self._request("/api/ecosystem/directory"))

    def get_signed_ecosystem_directory(self) -> SignedArtifactRecord:
        return SignedArtifactRecord.from_payload(self._request("/api/ecosystem/directory/signed"))

    def validate_interop_envelope(self, payload: dict[str, Any]) -> InteropValidationRecord:
        return InteropValidationRecord.from_payload(
            self._request("/api/interop/validate", _RequestOptions(method="POST", body=payload))
        )

    def list_events(self) -> list[EventRecord]:
        return [EventRecord.from_payload(item) for item in _items_payload(self._request("/api/events"))]

    def list_webhooks(self) -> list[WebhookRecord]:
        return [WebhookRecord.from_payload(item) for item in _items_payload(self._request("/api/webhooks"), "endpoints")]

    def create_webhook(self, payload: dict[str, Any]) -> WebhookRecord:
        return WebhookRecord.from_payload(self._request("/api/webhooks", _RequestOptions(method="POST", body=payload)))

    def list_webhook_deliveries(self) -> list[WebhookDeliveryRecord]:
        return [WebhookDeliveryRecord.from_payload(item) for item in _items_payload(self._request("/api/webhooks/deliveries"))]

    def drain_webhooks(self) -> WebhookDrainRecord:
        return WebhookDrainRecord.from_payload(self._request("/api/webhooks/drain", _RequestOptions(method="POST")))

    def test_webhook(self, endpoint_id: str, payload: dict[str, Any] | None = None) -> WebhookDeliveryRecord:
        return WebhookDeliveryRecord.from_payload(self._request(
            f"/api/webhooks/{endpoint_id}/test",
            _RequestOptions(method="POST", body=payload or {"drainNow": True}),
        ))

    def replay_webhook(self, endpoint_id: str, payload: dict[str, Any]) -> WebhookDeliveryRecord:
        return WebhookDeliveryRecord.from_payload(
            self._request(f"/api/webhooks/{endpoint_id}/replay", _RequestOptions(method="POST", body=payload))
        )

    def export_audit(self) -> AuditExportRecord:
        return AuditExportRecord.from_payload(self._request("/api/audit/export"))

    def get_audit_review(self, fmt: str = "json") -> Any:
        return self._request(f"/api/audit/review?format={fmt}", _RequestOptions(parse_json=fmt == "json"))

    def get_cost_report(self, fmt: str = "json") -> CostReportRecord | str:
        payload = self._request(f"/api/reporting/costs?format={fmt}", _RequestOptions(parse_json=fmt == "json"))
        if fmt != "json":
            return str(payload)
        return CostReportRecord.from_payload(payload)

    def get_monthly_statement(self, month: str | None = None) -> MonthlyStatementRecord:
        suffix = f"?month={month}" if month else ""
        return MonthlyStatementRecord.from_payload(self._request(f"/api/statements/monthly{suffix}"))

    def list_agreements(self) -> Any:
        return self._request("/api/agreements")

    def create_agreement(self, payload: dict[str, Any]) -> Any:
        return self._request("/api/agreements", _RequestOptions(method="POST", body=payload))

    def submit_milestone_proof(self, agreement_id: str, milestone_id: str, payload: dict[str, Any]) -> Any:
        return self._request(
            f"/api/agreements/{agreement_id}/milestones/{milestone_id}/proof",
            _RequestOptions(method="POST", body=payload),
        )

    def release_milestone(self, agreement_id: str, milestone_id: str) -> Any:
        return self._request(
            f"/api/agreements/{agreement_id}/milestones/{milestone_id}/release",
            _RequestOptions(method="POST"),
        )

    def dispute_milestone(self, agreement_id: str, milestone_id: str, payload: dict[str, Any]) -> Any:
        return self._request(
            f"/api/agreements/{agreement_id}/milestones/{milestone_id}/dispute",
            _RequestOptions(method="POST", body=payload),
        )

    def resolve_milestone(self, agreement_id: str, milestone_id: str, payload: dict[str, Any]) -> Any:
        return self._request(
            f"/api/agreements/{agreement_id}/milestones/{milestone_id}/resolve",
            _RequestOptions(method="POST", body=payload),
        )

    def get_wallet(self) -> WalletStateRecord:
        return WalletStateRecord.from_payload(self._request("/api/wallet"))

    def create_deposit(self, payload: dict[str, Any]) -> Any:
        return self._request("/api/wallet/deposits", _RequestOptions(method="POST", body=payload))

    def create_payout(self, payload: dict[str, Any]) -> Any:
        return self._request("/api/wallet/payouts", _RequestOptions(method="POST", body=payload))

    def list_settlement_jobs(self) -> list[SettlementJobRecord]:
        return [SettlementJobRecord.from_payload(item) for item in _items_payload(self._request("/api/settlement/jobs"), "jobs")]

    def run_settlement(self) -> SettlementRunRecord:
        return SettlementRunRecord.from_payload(self._request("/api/settlement/run", _RequestOptions(method="POST")))

    def get_reconciliation(self) -> ReconciliationRecord:
        return ReconciliationRecord.from_payload(self._request("/api/reconciliation"))

    def get_intent_timeline(self) -> TimelineReportRecord:
        return TimelineReportRecord.from_payload(self._request("/api/workspace/intent-timeline"))

    def get_weekly_review(self) -> WeeklyReviewRecord:
        return WeeklyReviewRecord.from_payload(self._request("/api/workspace/weekly-review"))

    def get_policy_workbench(self) -> PolicyWorkbenchRecord:
        return PolicyWorkbenchRecord.from_payload(self._request("/api/policy-workbench"))

    def approve_intent(self, approval_id: str, payload: dict[str, Any] | None = None) -> Any:
        return self._request(f"/api/approvals/{approval_id}/approve", _RequestOptions(method="POST", body=payload or {}))

    def reject_intent(self, approval_id: str, payload: dict[str, Any] | None = None) -> Any:
        return self._request(f"/api/approvals/{approval_id}/reject", _RequestOptions(method="POST", body=payload or {}))

    def list_approvals(self) -> list[ApprovalRecord]:
        return [record for record in (ApprovalRecord.from_payload(item) for item in _items_payload(self._request("/api/approvals"))) if record]

    def list_ledger(self, agent_id: str) -> list[LedgerEntryRecord]:
        return [LedgerEntryRecord.from_payload(item) for item in _items_payload(self._request(f"/api/agents/{agent_id}/ledger"), "entries")]

    def list_receipts(self, agent_id: str) -> list[ReceiptRecord]:
        return [ReceiptRecord.from_payload(item) for item in _items_payload(self._request(f"/api/agents/{agent_id}/receipts"))]

    def attach_receipt_evidence(self, receipt_id: str, payload: dict[str, Any]) -> ReceiptRecord:
        return ReceiptRecord.from_payload(
            self._request(f"/api/receipts/{receipt_id}/evidence", _RequestOptions(method="POST", body=payload))
        )

    def list_api_keys(self) -> list[ApiKeyRecord]:
        return [ApiKeyRecord.from_payload(item) for item in _items_payload(self._request("/api/api-keys"))]

    def create_api_key(self, payload: str | dict[str, Any]) -> ApiKeyRecord:
        body = {"label": payload} if isinstance(payload, str) else payload
        return ApiKeyRecord.from_payload(self._request("/api/api-keys", _RequestOptions(method="POST", body=body)))

    def revoke_api_key(self, api_key_id: str, payload: dict[str, Any] | None = None) -> ApiKeyRecord:
        return ApiKeyRecord.from_payload(
            self._request(f"/api/api-keys/{api_key_id}/revoke", _RequestOptions(method="POST", body=payload or {}))
        )

    def rotate_api_key(self, api_key_id: str, payload: dict[str, Any] | None = None) -> ApiKeyRecord:
        return ApiKeyRecord.from_payload(
            self._request(f"/api/api-keys/{api_key_id}/rotate", _RequestOptions(method="POST", body=payload or {}))
        )

    def _request(self, pathname: str, options: _RequestOptions = _RequestOptions()) -> Any:
        headers: dict[str, str] = {}
        if options.authenticated:
            if not self.api_key:
                raise AuthenticationError("Missing api_key for authenticated request")
            headers["x-api-key"] = self.api_key

        try:
            status_code, payload_text = self.transport.request(
                url=f"{self.base_url}{pathname}",
                method=options.method,
                headers=headers,
                body=options.body,
            )
        except Exception as exc:  # pragma: no cover - transport-specific failure path
            raise TransportError(f"Request failed: {exc}", retryable=True) from exc

        payload = _decode_payload(payload_text, options.parse_json)
        if status_code >= 400:
            raise _coerce_error(status_code, payload, f"Request failed with status {status_code}")
        return payload


class AsyncAgentPayClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str | None = None,
        *,
        timeout_seconds: float = 15.0,
        default_headers: Mapping[str, str] | None = None,
        transport: AsyncHttpTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.default_headers = dict(default_headers or {})
        self.transport = transport or AsyncHttpTransport(
            TransportConfig(timeout_seconds=timeout_seconds, default_headers=dict(self.default_headers)),
        )
        self._owns_transport = transport is None

    def with_api_key(self, api_key: str) -> "AsyncAgentPayClient":
        cloned = AsyncAgentPayClient(
            base_url=self.base_url,
            api_key=api_key,
            timeout_seconds=self.timeout_seconds,
            default_headers=self.default_headers,
            transport=self.transport,
        )
        cloned._owns_transport = False
        return cloned

    def with_timeout(self, timeout_seconds: float) -> "AsyncAgentPayClient":
        return AsyncAgentPayClient(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout_seconds=timeout_seconds,
            default_headers=self.default_headers,
        )

    async def close(self) -> None:
        if self._owns_transport:
            await self.transport.close()

    async def __aenter__(self) -> "AsyncAgentPayClient":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()

    async def onboard(self, payload: dict[str, Any]) -> Any:
        return await self._request("/api/onboarding", _RequestOptions(method="POST", body=payload, authenticated=False))

    async def get_bootstrap(self) -> Any:
        return await self._request("/api/bootstrap")

    async def create_agent(self, payload: dict[str, Any]) -> Any:
        return await self._request("/api/agents", _RequestOptions(method="POST", body=payload))

    async def create_policy(self, agent_id: str, payload: dict[str, Any]) -> Any:
        return await self._request(f"/api/agents/{agent_id}/policies", _RequestOptions(method="POST", body=payload))

    async def list_policy_templates(self) -> list[PolicyTemplateRecord]:
        return [PolicyTemplateRecord.from_payload(item) for item in _items_payload(await self._request("/api/policy-templates"), "templates")]

    async def list_api_key_templates(self) -> list[ApiKeyTemplateRecord]:
        return [ApiKeyTemplateRecord.from_payload(item) for item in _items_payload(await self._request("/api/api-key-templates"), "templates")]

    async def list_budget_caps(self) -> list[BudgetCapRecord]:
        return [BudgetCapRecord.from_payload(item) for item in _items_payload(await self._request("/api/budget-caps"))]

    async def create_budget_cap(self, payload: dict[str, Any]) -> BudgetCapRecord:
        return BudgetCapRecord.from_payload(await self._request("/api/budget-caps", _RequestOptions(method="POST", body=payload)))

    async def list_policy_packs(self) -> PolicyPackCatalogRecord:
        return PolicyPackCatalogRecord.from_payload(await self._request("/api/policy-packs"))

    async def get_policy_pack(self, pack_id: str) -> PolicyPackDetailRecord:
        return PolicyPackDetailRecord.from_payload(await self._request(f"/api/policy-packs/{pack_id}"))

    async def replay_policy_pack(self, pack_id: str, payload: dict[str, Any]) -> PolicyPackReplayResultRecord:
        return PolicyPackReplayResultRecord.from_payload(
            await self._request(f"/api/policy-packs/{pack_id}/replay", _RequestOptions(method="POST", body=payload))
        )

    async def apply_policy_pack(self, pack_id: str, payload: dict[str, Any]) -> PolicyPackApplyRecord:
        return PolicyPackApplyRecord.from_payload(
            await self._request(f"/api/policy-packs/{pack_id}/apply", _RequestOptions(method="POST", body=payload))
        )

    async def rollback_policy_pack(self, pack_id: str, payload: dict[str, Any] | None = None) -> PolicyPackRollbackRecord:
        return PolicyPackRollbackRecord.from_payload(
            await self._request(f"/api/policy-packs/{pack_id}/rollback", _RequestOptions(method="POST", body=payload or {}))
        )

    async def create_payment_intent(self, payload: dict[str, Any]) -> Any:
        return await self._request("/api/payments/intents", _RequestOptions(method="POST", body=payload))

    async def diff_policy(self, payload: dict[str, Any]) -> Any:
        return await self._request("/api/policies/diff", _RequestOptions(method="POST", body=payload))

    async def list_anomalies(self) -> list[AnomalyRecord]:
        return [AnomalyRecord.from_payload(item) for item in _items_payload(await self._request("/api/anomalies"))]

    async def update_anomaly(self, anomaly_id: str, payload: dict[str, Any]) -> AnomalyRecord:
        return AnomalyRecord.from_payload(
            await self._request(f"/api/anomalies/{anomaly_id}", _RequestOptions(method="POST", body=payload))
        )

    async def get_identity(self) -> IdentityRecord:
        return IdentityRecord.from_payload(await self._request("/api/identity"))

    async def update_identity(self, payload: dict[str, Any]) -> IdentityRecord:
        return IdentityRecord.from_payload(await self._request("/api/identity", _RequestOptions(method="POST", body=payload)))

    async def get_compliance(self) -> ComplianceRecord:
        return ComplianceRecord.from_payload(await self._request("/api/compliance"))

    async def get_wallet(self) -> WalletStateRecord:
        return WalletStateRecord.from_payload(await self._request("/api/wallet"))

    async def create_deposit(self, payload: dict[str, Any]) -> Any:
        return await self._request("/api/wallet/deposits", _RequestOptions(method="POST", body=payload))

    async def create_payout(self, payload: dict[str, Any]) -> Any:
        return await self._request("/api/wallet/payouts", _RequestOptions(method="POST", body=payload))

    async def list_settlement_jobs(self) -> list[SettlementJobRecord]:
        return [SettlementJobRecord.from_payload(item) for item in _items_payload(await self._request("/api/settlement/jobs"), "jobs")]

    async def run_settlement(self) -> SettlementRunRecord:
        return SettlementRunRecord.from_payload(await self._request("/api/settlement/run", _RequestOptions(method="POST")))

    async def get_reconciliation(self) -> ReconciliationRecord:
        return ReconciliationRecord.from_payload(await self._request("/api/reconciliation"))

    async def list_approvals(self) -> list[ApprovalRecord]:
        return [record for record in (ApprovalRecord.from_payload(item) for item in _items_payload(await self._request("/api/approvals"))) if record]

    async def approve_intent(self, approval_id: str, payload: dict[str, Any] | None = None) -> Any:
        return await self._request(f"/api/approvals/{approval_id}/approve", _RequestOptions(method="POST", body=payload or {}))

    async def reject_intent(self, approval_id: str, payload: dict[str, Any] | None = None) -> Any:
        return await self._request(f"/api/approvals/{approval_id}/reject", _RequestOptions(method="POST", body=payload or {}))

    async def list_ledger(self, agent_id: str) -> list[LedgerEntryRecord]:
        return [LedgerEntryRecord.from_payload(item) for item in _items_payload(await self._request(f"/api/agents/{agent_id}/ledger"), "entries")]

    async def list_receipts(self, agent_id: str) -> list[ReceiptRecord]:
        return [ReceiptRecord.from_payload(item) for item in _items_payload(await self._request(f"/api/agents/{agent_id}/receipts"))]

    async def attach_receipt_evidence(self, receipt_id: str, payload: dict[str, Any]) -> ReceiptRecord:
        return ReceiptRecord.from_payload(
            await self._request(f"/api/receipts/{receipt_id}/evidence", _RequestOptions(method="POST", body=payload))
        )

    async def list_api_keys(self) -> list[ApiKeyRecord]:
        return [ApiKeyRecord.from_payload(item) for item in _items_payload(await self._request("/api/api-keys"))]

    async def create_api_key(self, payload: str | dict[str, Any]) -> ApiKeyRecord:
        body = {"label": payload} if isinstance(payload, str) else payload
        return ApiKeyRecord.from_payload(await self._request("/api/api-keys", _RequestOptions(method="POST", body=body)))

    async def revoke_api_key(self, api_key_id: str, payload: dict[str, Any] | None = None) -> ApiKeyRecord:
        return ApiKeyRecord.from_payload(
            await self._request(f"/api/api-keys/{api_key_id}/revoke", _RequestOptions(method="POST", body=payload or {}))
        )

    async def rotate_api_key(self, api_key_id: str, payload: dict[str, Any] | None = None) -> ApiKeyRecord:
        return ApiKeyRecord.from_payload(
            await self._request(f"/api/api-keys/{api_key_id}/rotate", _RequestOptions(method="POST", body=payload or {}))
        )

    async def simulate_policy(self, payload: dict[str, Any]) -> Any:
        return await self._request("/api/policies/simulate", _RequestOptions(method="POST", body=payload))

    async def export_audit(self) -> AuditExportRecord:
        return AuditExportRecord.from_payload(await self._request("/api/audit/export"))

    async def get_audit_review(self, fmt: str = "json") -> Any:
        return await self._request(f"/api/audit/review?format={fmt}", _RequestOptions(parse_json=fmt == "json"))

    async def get_cost_report(self, fmt: str = "json") -> CostReportRecord | str:
        payload = await self._request(f"/api/reporting/costs?format={fmt}", _RequestOptions(parse_json=fmt == "json"))
        if fmt != "json":
            return str(payload)
        return CostReportRecord.from_payload(payload)

    async def get_monthly_statement(self, month: str | None = None) -> MonthlyStatementRecord:
        suffix = f"?month={month}" if month else ""
        return MonthlyStatementRecord.from_payload(await self._request(f"/api/statements/monthly{suffix}"))

    async def get_reputation(self) -> ReputationRecord:
        return ReputationRecord.from_payload(await self._request("/api/reputation"))

    async def get_trust_profile(self) -> TrustProfileRecord:
        return TrustProfileRecord.from_payload(await self._request("/api/trust/profile"))

    async def get_trust_tiers(self) -> list[TrustTierRecord]:
        return [TrustTierRecord.from_payload(item) for item in _items_payload(await self._request("/api/trust/tiers"), "tiers")]

    async def get_trust_manifest(self) -> TrustManifestRecord:
        return TrustManifestRecord.from_payload(await self._request("/api/trust/manifest"))

    async def get_signed_trust_manifest(self) -> SignedArtifactRecord:
        return SignedArtifactRecord.from_payload(await self._request("/api/trust/manifest/signed"))

    async def verify_trust_manifest(self, payload: dict[str, Any]) -> Any:
        return await self._request("/api/trust/verify", _RequestOptions(method="POST", body=payload))

    async def handshake_trust_manifest(self, payload: dict[str, Any]) -> Any:
        return await self._request("/api/trust/handshake", _RequestOptions(method="POST", body=payload))

    async def get_portable_reputation(self) -> ReputationRecord:
        return ReputationRecord.from_payload(await self._request("/api/reputation/portable"))

    async def get_signed_portable_reputation(self) -> SignedArtifactRecord:
        return SignedArtifactRecord.from_payload(await self._request("/api/reputation/portable/signed"))

    async def export_agreement_standard(self) -> AgreementStandardRecord:
        return AgreementStandardRecord.from_payload(await self._request("/api/standards/agreements"))

    async def export_signed_agreement_standard(self) -> SignedArtifactRecord:
        return SignedArtifactRecord.from_payload(await self._request("/api/standards/agreements/signed"))

    async def get_agreement_standard_schema(self) -> AgreementStandardRecord:
        return AgreementStandardRecord.from_payload(await self._request("/api/standards/agreement-schema"))

    async def get_ecosystem_directory(self) -> EcosystemDirectoryRecord:
        return EcosystemDirectoryRecord.from_payload(await self._request("/api/ecosystem/directory"))

    async def get_signed_ecosystem_directory(self) -> SignedArtifactRecord:
        return SignedArtifactRecord.from_payload(await self._request("/api/ecosystem/directory/signed"))

    async def validate_interop_envelope(self, payload: dict[str, Any]) -> InteropValidationRecord:
        return InteropValidationRecord.from_payload(
            await self._request("/api/interop/validate", _RequestOptions(method="POST", body=payload))
        )

    async def list_events(self) -> list[EventRecord]:
        return [EventRecord.from_payload(item) for item in _items_payload(await self._request("/api/events"))]

    async def list_webhooks(self) -> list[WebhookRecord]:
        return [WebhookRecord.from_payload(item) for item in _items_payload(await self._request("/api/webhooks"), "endpoints")]

    async def create_webhook(self, payload: dict[str, Any]) -> WebhookRecord:
        return WebhookRecord.from_payload(await self._request("/api/webhooks", _RequestOptions(method="POST", body=payload)))

    async def list_webhook_deliveries(self) -> list[WebhookDeliveryRecord]:
        return [WebhookDeliveryRecord.from_payload(item) for item in _items_payload(await self._request("/api/webhooks/deliveries"))]

    async def drain_webhooks(self) -> WebhookDrainRecord:
        return WebhookDrainRecord.from_payload(await self._request("/api/webhooks/drain", _RequestOptions(method="POST")))

    async def test_webhook(self, endpoint_id: str, payload: dict[str, Any] | None = None) -> WebhookDeliveryRecord:
        return WebhookDeliveryRecord.from_payload(await self._request(
            f"/api/webhooks/{endpoint_id}/test",
            _RequestOptions(method="POST", body=payload or {"drainNow": True}),
        ))

    async def replay_webhook(self, endpoint_id: str, payload: dict[str, Any]) -> WebhookDeliveryRecord:
        return WebhookDeliveryRecord.from_payload(
            await self._request(f"/api/webhooks/{endpoint_id}/replay", _RequestOptions(method="POST", body=payload))
        )

    async def get_intent_timeline(self) -> TimelineReportRecord:
        return TimelineReportRecord.from_payload(await self._request("/api/workspace/intent-timeline"))

    async def get_weekly_review(self) -> WeeklyReviewRecord:
        return WeeklyReviewRecord.from_payload(await self._request("/api/workspace/weekly-review"))

    async def get_policy_workbench(self) -> PolicyWorkbenchRecord:
        return PolicyWorkbenchRecord.from_payload(await self._request("/api/policy-workbench"))

    async def list_agreements(self) -> Any:
        return await self._request("/api/agreements")

    async def create_agreement(self, payload: dict[str, Any]) -> Any:
        return await self._request("/api/agreements", _RequestOptions(method="POST", body=payload))

    async def submit_milestone_proof(self, agreement_id: str, milestone_id: str, payload: dict[str, Any]) -> Any:
        return await self._request(
            f"/api/agreements/{agreement_id}/milestones/{milestone_id}/proof",
            _RequestOptions(method="POST", body=payload),
        )

    async def release_milestone(self, agreement_id: str, milestone_id: str) -> Any:
        return await self._request(
            f"/api/agreements/{agreement_id}/milestones/{milestone_id}/release",
            _RequestOptions(method="POST"),
        )

    async def dispute_milestone(self, agreement_id: str, milestone_id: str, payload: dict[str, Any]) -> Any:
        return await self._request(
            f"/api/agreements/{agreement_id}/milestones/{milestone_id}/dispute",
            _RequestOptions(method="POST", body=payload),
        )

    async def resolve_milestone(self, agreement_id: str, milestone_id: str, payload: dict[str, Any]) -> Any:
        return await self._request(
            f"/api/agreements/{agreement_id}/milestones/{milestone_id}/resolve",
            _RequestOptions(method="POST", body=payload),
        )

    async def list_kill_switches(self) -> list[KillSwitchRecord]:
        raw = await self._request("/api/compliance/kill-switches")
        items = raw.get("items") if isinstance(raw, Mapping) else raw
        return [KillSwitchRecord.from_payload(item) for item in items or []]

    async def save_kill_switch(self, payload: dict[str, Any]) -> KillSwitchRecord:
        return KillSwitchRecord.from_payload(
            await self._request("/api/compliance/kill-switches", _RequestOptions(method="POST", body=payload))
        )

    async def list_approval_chains(self) -> list[ApprovalChainRecord]:
        raw = await self._request("/api/compliance/approval-chains")
        items = raw.get("items") if isinstance(raw, Mapping) else raw
        return [ApprovalChainRecord.from_payload(item) for item in items or []]

    async def save_approval_chain(self, payload: dict[str, Any]) -> ApprovalChainRecord:
        return ApprovalChainRecord.from_payload(
            await self._request("/api/compliance/approval-chains", _RequestOptions(method="POST", body=payload))
        )

    async def list_hardware_bindings(self) -> list[HardwareBindingRecord]:
        raw = await self._request("/api/compliance/hardware-bindings")
        items = raw.get("items") if isinstance(raw, Mapping) else raw
        return [HardwareBindingRecord.from_payload(item) for item in items or []]

    async def save_hardware_binding(self, payload: dict[str, Any]) -> HardwareBindingRecord:
        return HardwareBindingRecord.from_payload(
            await self._request("/api/compliance/hardware-bindings", _RequestOptions(method="POST", body=payload))
        )

    async def get_tax_profile(self) -> TaxProfileRecord:
        return TaxProfileRecord.from_payload(await self._request("/api/compliance/tax-profile"))

    async def update_tax_profile(self, payload: dict[str, Any]) -> TaxProfileRecord:
        return TaxProfileRecord.from_payload(
            await self._request("/api/compliance/tax-profile", _RequestOptions(method="POST", body=payload))
        )

    async def update_compliance_settings(self, payload: dict[str, Any]) -> Any:
        return await self._request("/api/compliance/settings", _RequestOptions(method="POST", body=payload))

    async def get_weekly_expense_report(self) -> WeeklyExpenseReportRecord:
        return WeeklyExpenseReportRecord.from_payload(await self._request("/api/workspace/expense-report"))

    async def _request(self, pathname: str, options: _RequestOptions = _RequestOptions()) -> Any:
        headers: dict[str, str] = {}
        if options.authenticated:
            if not self.api_key:
                raise AuthenticationError("Missing api_key for authenticated request")
            headers["x-api-key"] = self.api_key
        try:
            status_code, payload_text = await self.transport.request(
                url=f"{self.base_url}{pathname}",
                method=options.method,
                headers=headers,
                body=options.body,
            )
        except Exception as exc:  # pragma: no cover - transport-specific failure path
            raise TransportError(f"Request failed: {exc}", retryable=True) from exc

        payload = _decode_payload(payload_text, options.parse_json)
        if status_code >= 400:
            raise _coerce_error(status_code, payload, f"Request failed with status {status_code}")
        return payload


def _looks_like_evm_address(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("0x") and len(value) == 42


def _first_agent(bootstrap: Mapping[str, Any]) -> dict[str, Any]:
    agents = bootstrap.get("agents") or []
    if not agents:
        raise AgentPayError("Wallet bootstrap did not return any agents")
    return cast(dict[str, Any], agents[0])


def _find_pending_approval(bootstrap: Mapping[str, Any], payment_intent_id: str) -> dict[str, Any] | None:
    approvals = bootstrap.get("approvals") or []
    return next((item for item in approvals if item.get("paymentIntentId") == payment_intent_id and item.get("status") == "pending"), None)


@dataclass
class Wallet:
    client: AgentPayClient
    workspace: dict[str, Any]
    agent: dict[str, Any]
    wallet: Mapping[str, Any] | None
    api_key: dict[str, Any] | None
    policy: dict[str, Any] | None = None
    circuit_breaker: LocalCircuitBreaker | None = None

    @classmethod
    def create(
        cls,
        *,
        owner: str,
        daily_limit: AmountLike = 100,
        base_url: str = DEFAULT_BASE_URL,
        workspace_name: str | None = None,
        require_approval_above: AmountLike | None = None,
        max_transaction: AmountLike | None = None,
        whitelist: list[str] | None = None,
        auto_pause_on_anomaly: bool = False,
        review_on_anomaly: bool = False,
        starting_balance: AmountLike = 100,
        timeout_seconds: float = 15.0,
        transport: SyncHttpTransport | None = None,
    ) -> "Wallet":
        public_client = AgentPayClient(base_url=base_url, timeout_seconds=timeout_seconds, transport=transport)
        onboarding = public_client.onboard(
            {
                "workspaceName": workspace_name or f"{owner} workspace",
                "agentName": owner,
                "dailyLimitUsd": usd_float(daily_limit),
                "requireApprovalOverUsd": usd_float(require_approval_above) if require_approval_above is not None else None,
                "maxTransactionUsd": usd_float(max_transaction) if max_transaction is not None else None,
                "counterpartyAllowlist": whitelist,
                "autoPauseOnAnomaly": auto_pause_on_anomaly,
                "reviewOnAnomaly": review_on_anomaly,
                "startingBalanceUsd": usd_float(starting_balance),
            }
        )
        client = public_client.with_api_key(onboarding["apiKey"]["key"])
        return cls(
            client=client,
            workspace=onboarding["workspace"],
            agent=onboarding["agent"],
            wallet=onboarding.get("wallet"),
            api_key=onboarding.get("apiKey"),
            policy=onboarding.get("policy"),
        )

    @classmethod
    def connect(
        cls,
        *,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        agent_id: str | None = None,
        auth_path: str | Path | None = None,
        timeout_seconds: float = 15.0,
        transport: SyncHttpTransport | None = None,
    ) -> "Wallet":
        resolved_api_key = api_key
        if not resolved_api_key:
            profile = load_login(base_url=base_url, path=Path(auth_path) if auth_path else None)
            if not profile:
                raise AuthenticationError("Missing api_key and no stored NORNR login found. Run `nornr login`.")
            resolved_api_key = profile.api_key
        client = AgentPayClient(base_url=base_url, api_key=resolved_api_key, timeout_seconds=timeout_seconds, transport=transport)
        bootstrap = client.get_bootstrap()
        agent = next((item for item in bootstrap.get("agents", []) if item.get("id") == agent_id), None) if agent_id else None
        return cls(
            client=client,
            workspace=bootstrap["workspace"],
            agent=agent or _first_agent(bootstrap),
            wallet=bootstrap.get("wallet"),
            api_key={"key": resolved_api_key},
        )

    @property
    def agent_id(self) -> str:
        return str(self.agent["id"])

    @property
    def workspace_id(self) -> str:
        return str(self.workspace["id"])

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "Wallet":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def refresh(self) -> dict[str, Any]:
        bootstrap = self.client.get_bootstrap()
        self.workspace = bootstrap["workspace"]
        self.agent = next((item for item in bootstrap.get("agents", []) if item.get("id") == self.agent_id), _first_agent(bootstrap))
        self.wallet = bootstrap.get("wallet")
        return bootstrap

    def pay(
        self,
        *,
        amount: AmountLike,
        to: str,
        purpose: str | None = None,
        counterparty: str | None = None,
        budget_tags: dict[str, str] | None = None,
        dry_run: bool = False,
        business_context: dict[str, Any] | None = None,
        replay_context: dict[str, Any] | None = None,
    ) -> DecisionRecord:
        normalized_amount = usd_decimal(amount)
        scoped_budget = current_budget_scope()
        if scoped_budget and normalized_amount > scoped_budget.limit_usd:
            raise ValidationError(
                f"Local NORNR budget scope blocked {usd_text(normalized_amount)} USD because the block limit is {usd_text(scoped_budget.limit_usd)} USD",
            )
        if self.circuit_breaker:
            try:
                self.circuit_breaker.check(normalized_amount)
            except RuntimeError as exc:
                raise ValidationError(str(exc)) from exc
        destination = to if _looks_like_evm_address(to) else None
        resolved_counterparty = counterparty or (to if not destination else "external")
        if scoped_budget and scoped_budget.counterparty and resolved_counterparty != scoped_budget.counterparty:
            raise ValidationError(
                f"Local NORNR budget scope only allows {scoped_budget.counterparty}, but got {resolved_counterparty}",
            )
        resolved_business_context = merge_business_context(business_context)
        merged_budget_tags = dict(budget_tags or {})
        if scoped_budget and scoped_budget.budget_tags:
            merged_budget_tags = {**scoped_budget.budget_tags, **merged_budget_tags}
        merged_budget_tags = _apply_business_context_tags(merged_budget_tags or None, resolved_business_context) or {}
        resolved_purpose = purpose or f"agent payment to {resolved_counterparty}"
        if scoped_budget and scoped_budget.purpose_prefix:
            resolved_purpose = f"{scoped_budget.purpose_prefix}: {resolved_purpose}"
        result = self.client.create_payment_intent(
            {
                "agentId": self.agent_id,
                "amountUsd": usd_float(normalized_amount),
                "counterparty": resolved_counterparty,
                "destination": destination,
                "budgetTags": merged_budget_tags or None,
                "purpose": resolved_purpose,
                "dryRun": bool(dry_run or (scoped_budget.dry_run if scoped_budget else False)),
                "businessContext": resolved_business_context,
                "executionContext": merge_replay_context(replay_context, default_source="wallet.pay"),
            }
        )
        payment_intent = result.get("paymentIntent") or {}
        if payment_intent.get("status") == "queued":
            bootstrap = self.client.get_bootstrap()
            approval = _find_pending_approval(bootstrap, payment_intent.get("id", ""))
            if approval:
                approval = {
                    **approval,
                    "approvalUrl": _control_room_url(self.client.base_url, approval.get("id")),
                }
                result["approval"] = approval
                result["approvalUrl"] = approval.get("approvalUrl")
            result["requiresApproval"] = approval is not None
        else:
            result["requiresApproval"] = False
        return DecisionRecord.from_payload(result)

    def pending_approvals(self) -> list[ApprovalRecord]:
        bootstrap = self.client.get_bootstrap()
        return [record for record in (ApprovalRecord.from_payload(item) for item in bootstrap.get("approvals", [])) if record and record.status == "pending"]

    def approve_if_needed(self, payment: Mapping[str, Any] | DecisionRecord, *, comment: str | None = None) -> Any:
        approval_payload = payment.get("approval") if isinstance(payment, Mapping) else None
        approval = ApprovalRecord.from_payload(approval_payload)
        if approval:
            return self.client.approve_intent(approval.id or "", {"comment": comment} if comment else {})
        payment_intent = payment.get("paymentIntent") if isinstance(payment, Mapping) else None
        status = payment_intent.get("status") if isinstance(payment_intent, Mapping) else None
        if status != "queued":
            return payment
        payment_intent_id = payment_intent.get("id") if isinstance(payment_intent, Mapping) else None
        if not payment_intent_id:
            raise AgentPayError("Queued payment is missing payment intent id")
        bootstrap = self.client.get_bootstrap()
        pending_approval = _find_pending_approval(bootstrap, str(payment_intent_id))
        if not pending_approval:
            raise AgentPayError("No pending approval found for payment intent")
        return self.client.approve_intent(pending_approval["id"], {"comment": comment} if comment else {})

    def reject(self, approval_id: str, *, comment: str | None = None) -> Any:
        return self.client.reject_intent(approval_id, {"comment": comment} if comment else {})

    def balance(self) -> BalanceRecord:
        wallet_state = self.client.get_wallet()
        self.wallet = wallet_state
        return BalanceRecord.from_payload(wallet_state)

    def settle(self) -> SettlementRunRecord:
        return self.client.run_settlement()

    def budget(
        self,
        limit: AmountLike,
        *,
        counterparty: str | None = None,
        purpose_prefix: str | None = None,
        budget_tags: dict[str, str] | None = None,
        dry_run: bool = False,
    ) -> BudgetContext:
        return budget_scope(
            limit,
            counterparty=counterparty,
            purpose_prefix=purpose_prefix,
            budget_tags=budget_tags,
            dry_run=dry_run,
        )

    def enable_circuit_breaker(
        self,
        *,
        max_requests: int = 10,
        window_seconds: float = 1.0,
        max_spend_usd: AmountLike | None = None,
        max_velocity_usd: AmountLike | None = None,
    ) -> "Wallet":
        self.circuit_breaker = LocalCircuitBreaker(
            CircuitBreakerConfig(
                max_requests=max_requests,
                window_seconds=window_seconds,
                max_spend_usd=max_spend_usd,
                max_velocity_usd=max_velocity_usd,
            )
        )
        return self

    def guard(
        self,
        *,
        amount: AmountLike,
        counterparty: str,
        purpose: str,
        destination: str | None = None,
        budget_tags: dict[str, str] | None = None,
    ) -> Any:
        from .guards import WalletGuard

        return WalletGuard(
            self,
            amount=usd_float(amount),
            counterparty=counterparty,
            purpose=purpose,
            destination=destination,
            budget_tags=budget_tags,
        )

    def simulate_policy(self, *, template_id: str, rollout_mode: str = "shadow") -> PolicySimulationRecord:
        payload = {
            "agentId": self.agent_id,
            "templateId": template_id,
            "rolloutMode": rollout_mode,
        }
        return PolicySimulationRecord.from_payload(self.client.simulate_policy(payload))

    def list_policy_packs(self) -> PolicyPackCatalogRecord:
        return self.client.list_policy_packs()

    def get_policy_pack(self, pack_id: str) -> PolicyPackDetailRecord:
        return self.client.get_policy_pack(pack_id)

    def replay_policy_pack(self, pack_id: str, *, mode: str = "shadow") -> PolicyPackReplayResultRecord:
        return self.client.replay_policy_pack(
            pack_id,
            {
                "agentId": self.agent_id,
                "mode": mode,
            },
        )

    def apply_policy_pack(self, pack_id: str, *, mode: str = "shadow") -> PolicyPackApplyRecord:
        return self.client.apply_policy_pack(
            pack_id,
            {
                "agentId": self.agent_id,
                "mode": mode,
            },
        )

    def rollback_policy_pack(self, pack_id: str) -> PolicyPackRollbackRecord:
        return self.client.rollback_policy_pack(
            pack_id,
            {
                "agentId": self.agent_id,
            },
        )

    def audit_review(self) -> AuditReviewRecord:
        return AuditReviewRecord.from_payload(self.client.get_audit_review())

    def finance_packet(self) -> FinancePacketRecord:
        return self.audit_review().finance_packet

    def timeline(self) -> TimelineReportRecord:
        return TimelineReportRecord.from_payload(self.client.get_intent_timeline())

    def weekly_review(self) -> WeeklyReviewRecord:
        return WeeklyReviewRecord.from_payload(self.client.get_weekly_review())

    def check(
        self,
        *,
        intent: str,
        cost: AmountLike,
        counterparty: str,
        budget_tags: dict[str, str] | None = None,
        business_context: dict[str, Any] | None = None,
    ) -> IntentCheckRecord:
        normalized_cost = usd_decimal(cost)
        decision = self.pay(
            amount=normalized_cost,
            to=counterparty,
            counterparty=counterparty,
            purpose=intent,
            budget_tags=budget_tags,
            dry_run=True,
            business_context=business_context or {"reason": intent},
        )
        return IntentCheckRecord.from_decision(decision, intent=intent, amount=usd_float(normalized_cost))

    def delegate_mandate(
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
        return create_delegated_mandate(
            self,
            target_agent_id=target_agent_id,
            daily_limit=daily_limit,
            counterparty=counterparty,
            purpose_prefix=purpose_prefix,
            budget_tags=budget_tags,
            metadata=metadata,
            apply_budget_cap=apply_budget_cap,
        )

    def review_counterparty(self, counterparty: str) -> CounterpartyReview:
        return review_counterparty_sync(self, counterparty)

    def begin_governed_action(
        self,
        *,
        action_name: str,
        amount: AmountLike,
        to: str,
        purpose: str,
        run_id: str | None = None,
        intent_key: str | None = None,
        idempotency_key: str | None = None,
        counterparty: str | None = None,
        budget_tags: dict[str, str] | None = None,
        business_context: dict[str, Any] | None = None,
        replay_context: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> GovernedActionRun:
        generated_run_id, generated_intent_key, generated_idempotency_key = default_run_ids(action_name)
        resolved_run_id, resolved_intent_key, resolved_idempotency_key = (
            run_id or generated_run_id,
            intent_key or generated_intent_key,
            idempotency_key or generated_idempotency_key,
        )
        enriched_context = {
            **dict(business_context or {}),
            "governedRun": {
                "runId": resolved_run_id,
                "intentKey": resolved_intent_key,
                "idempotencyKey": resolved_idempotency_key,
                "actionName": action_name,
            },
        }
        decision = self.pay(
            amount=amount,
            to=to,
            purpose=purpose,
            counterparty=counterparty,
            budget_tags=budget_tags,
            dry_run=dry_run,
            business_context=enriched_context,
            replay_context=merge_replay_context(
                {
                    **dict(replay_context or {}),
                    "runId": resolved_run_id,
                    "intentKey": resolved_intent_key,
                    "idempotencyKey": resolved_idempotency_key,
                },
                default_source="wallet.begin_governed_action",
            ),
        )
        return GovernedActionRun(
            wallet=self,
            action_name=action_name,
            decision=decision,
            requested_amount_usd=usd_float(amount),
            requested_counterparty=counterparty or to,
            purpose=purpose,
            run_id=resolved_run_id,
            intent_key=resolved_intent_key,
            idempotency_key=resolved_idempotency_key,
            business_context=dict(enriched_context or {}),
        )

    def resume_governed_action(
        self,
        decision: DecisionRecord | Mapping[str, Any],
        *,
        action_name: str,
        amount: AmountLike | None = None,
        counterparty: str | None = None,
        purpose: str | None = None,
        business_context: dict[str, Any] | None = None,
    ) -> GovernedActionRun:
        resolved = decision if isinstance(decision, DecisionRecord) else DecisionRecord.from_payload(decision)
        generated_run_id, generated_intent_key, generated_idempotency_key = default_run_ids(action_name)
        return GovernedActionRun(
            wallet=self,
            action_name=action_name,
            decision=resolved,
            requested_amount_usd=usd_float(amount if amount is not None else resolved.amount_decimal),
            requested_counterparty=counterparty or resolved.payment_intent.counterparty or "unknown",
            purpose=purpose or resolved.payment_intent.purpose or action_name,
            run_id=str((resolved.payment_intent.business_context or {}).get("governedRun", {}).get("runId") or generated_run_id),
            intent_key=str((resolved.payment_intent.business_context or {}).get("governedRun", {}).get("intentKey") or generated_intent_key),
            idempotency_key=str((resolved.payment_intent.business_context or {}).get("governedRun", {}).get("idempotencyKey") or generated_idempotency_key),
            business_context=dict(business_context or resolved.payment_intent.business_context or {}),
        )

    def execute_governed(
        self,
        *,
        action_name: str,
        amount: AmountLike,
        to: str,
        purpose: str,
        callback: Any,
        counterparty: str | None = None,
        budget_tags: dict[str, str] | None = None,
        business_context: dict[str, Any] | None = None,
        replay_context: dict[str, Any] | None = None,
        dry_run: bool = False,
        receipt_id: str | None = None,
        evidence: Mapping[str, Any] | Any | None = None,
        raise_on_error: bool = True,
    ) -> GovernedExecutionRecord:
        run = self.begin_governed_action(
            action_name=action_name,
            amount=amount,
            to=to,
            purpose=purpose,
            counterparty=counterparty,
            budget_tags=budget_tags,
            business_context=business_context,
            replay_context=replay_context,
            dry_run=dry_run,
        )
        return run.execute(callback, receipt_id=receipt_id, evidence=evidence, raise_on_error=raise_on_error)


@dataclass
class AsyncWallet:
    client: AsyncAgentPayClient
    workspace: dict[str, Any]
    agent: dict[str, Any]
    wallet: Mapping[str, Any] | None
    api_key: dict[str, Any] | None
    policy: dict[str, Any] | None = None
    circuit_breaker: LocalCircuitBreaker | None = None

    @classmethod
    async def create(
        cls,
        *,
        owner: str,
        daily_limit: AmountLike = 100,
        base_url: str = DEFAULT_BASE_URL,
        workspace_name: str | None = None,
        require_approval_above: AmountLike | None = None,
        max_transaction: AmountLike | None = None,
        whitelist: list[str] | None = None,
        auto_pause_on_anomaly: bool = False,
        review_on_anomaly: bool = False,
        starting_balance: AmountLike = 100,
        timeout_seconds: float = 15.0,
        transport: AsyncHttpTransport | None = None,
    ) -> "AsyncWallet":
        public_client = AsyncAgentPayClient(base_url=base_url, timeout_seconds=timeout_seconds, transport=transport)
        onboarding = await public_client.onboard(
            {
                "workspaceName": workspace_name or f"{owner} workspace",
                "agentName": owner,
                "dailyLimitUsd": usd_float(daily_limit),
                "requireApprovalOverUsd": usd_float(require_approval_above) if require_approval_above is not None else None,
                "maxTransactionUsd": usd_float(max_transaction) if max_transaction is not None else None,
                "counterpartyAllowlist": whitelist,
                "autoPauseOnAnomaly": auto_pause_on_anomaly,
                "reviewOnAnomaly": review_on_anomaly,
                "startingBalanceUsd": usd_float(starting_balance),
            }
        )
        client = public_client.with_api_key(onboarding["apiKey"]["key"])
        return cls(
            client=client,
            workspace=onboarding["workspace"],
            agent=onboarding["agent"],
            wallet=onboarding.get("wallet"),
            api_key=onboarding.get("apiKey"),
            policy=onboarding.get("policy"),
        )

    @classmethod
    async def connect(
        cls,
        *,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        agent_id: str | None = None,
        auth_path: str | Path | None = None,
        timeout_seconds: float = 15.0,
        transport: AsyncHttpTransport | None = None,
    ) -> "AsyncWallet":
        resolved_api_key = api_key
        if not resolved_api_key:
            profile = load_login(base_url=base_url, path=Path(auth_path) if auth_path else None)
            if not profile:
                raise AuthenticationError("Missing api_key and no stored NORNR login found. Run `nornr login`.")
            resolved_api_key = profile.api_key
        client = AsyncAgentPayClient(base_url=base_url, api_key=resolved_api_key, timeout_seconds=timeout_seconds, transport=transport)
        bootstrap = await client.get_bootstrap()
        agent = next((item for item in bootstrap.get("agents", []) if item.get("id") == agent_id), None) if agent_id else None
        return cls(
            client=client,
            workspace=bootstrap["workspace"],
            agent=agent or _first_agent(bootstrap),
            wallet=bootstrap.get("wallet"),
            api_key={"key": resolved_api_key},
        )

    @property
    def agent_id(self) -> str:
        return str(self.agent["id"])

    @property
    def workspace_id(self) -> str:
        return str(self.workspace["id"])

    async def close(self) -> None:
        await self.client.close()

    async def __aenter__(self) -> "AsyncWallet":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()

    async def refresh(self) -> dict[str, Any]:
        bootstrap = await self.client.get_bootstrap()
        self.workspace = bootstrap["workspace"]
        self.agent = next((item for item in bootstrap.get("agents", []) if item.get("id") == self.agent_id), _first_agent(bootstrap))
        self.wallet = bootstrap.get("wallet")
        return bootstrap

    async def pay(
        self,
        *,
        amount: AmountLike,
        to: str,
        purpose: str | None = None,
        counterparty: str | None = None,
        budget_tags: dict[str, str] | None = None,
        dry_run: bool = False,
        business_context: dict[str, Any] | None = None,
        replay_context: dict[str, Any] | None = None,
    ) -> DecisionRecord:
        normalized_amount = usd_decimal(amount)
        scoped_budget = current_budget_scope()
        if scoped_budget and normalized_amount > scoped_budget.limit_usd:
            raise ValidationError(
                f"Local NORNR budget scope blocked {usd_text(normalized_amount)} USD because the block limit is {usd_text(scoped_budget.limit_usd)} USD",
            )
        if self.circuit_breaker:
            try:
                self.circuit_breaker.check(normalized_amount)
            except RuntimeError as exc:
                raise ValidationError(str(exc)) from exc
        destination = to if _looks_like_evm_address(to) else None
        resolved_counterparty = counterparty or (to if not destination else "external")
        if scoped_budget and scoped_budget.counterparty and resolved_counterparty != scoped_budget.counterparty:
            raise ValidationError(
                f"Local NORNR budget scope only allows {scoped_budget.counterparty}, but got {resolved_counterparty}",
            )
        resolved_business_context = merge_business_context(business_context)
        merged_budget_tags = dict(budget_tags or {})
        if scoped_budget and scoped_budget.budget_tags:
            merged_budget_tags = {**scoped_budget.budget_tags, **merged_budget_tags}
        merged_budget_tags = _apply_business_context_tags(merged_budget_tags or None, resolved_business_context) or {}
        resolved_purpose = purpose or f"agent payment to {resolved_counterparty}"
        if scoped_budget and scoped_budget.purpose_prefix:
            resolved_purpose = f"{scoped_budget.purpose_prefix}: {resolved_purpose}"
        result = await self.client.create_payment_intent(
            {
                "agentId": self.agent_id,
                "amountUsd": usd_float(normalized_amount),
                "counterparty": resolved_counterparty,
                "destination": destination,
                "budgetTags": merged_budget_tags or None,
                "purpose": resolved_purpose,
                "dryRun": bool(dry_run or (scoped_budget.dry_run if scoped_budget else False)),
                "businessContext": resolved_business_context,
                "executionContext": merge_replay_context(replay_context, default_source="wallet.pay.async"),
            }
        )
        payment_intent = result.get("paymentIntent") or {}
        if payment_intent.get("status") == "queued":
            bootstrap = await self.client.get_bootstrap()
            approval = _find_pending_approval(bootstrap, payment_intent.get("id", ""))
            if approval:
                approval = {
                    **approval,
                    "approvalUrl": _control_room_url(self.client.base_url, approval.get("id")),
                }
                result["approval"] = approval
                result["approvalUrl"] = approval.get("approvalUrl")
            result["requiresApproval"] = approval is not None
        else:
            result["requiresApproval"] = False
        return DecisionRecord.from_payload(result)

    async def pending_approvals(self) -> list[ApprovalRecord]:
        bootstrap = await self.client.get_bootstrap()
        return [record for record in (ApprovalRecord.from_payload(item) for item in bootstrap.get("approvals", [])) if record and record.status == "pending"]

    async def approve_if_needed(self, payment: Mapping[str, Any] | DecisionRecord, *, comment: str | None = None) -> Any:
        approval_payload = payment.get("approval") if isinstance(payment, Mapping) else None
        approval = ApprovalRecord.from_payload(approval_payload)
        if approval:
            return await self.client.approve_intent(approval.id or "", {"comment": comment} if comment else {})
        payment_intent = payment.get("paymentIntent") if isinstance(payment, Mapping) else None
        status = payment_intent.get("status") if isinstance(payment_intent, Mapping) else None
        if status != "queued":
            return payment
        payment_intent_id = payment_intent.get("id") if isinstance(payment_intent, Mapping) else None
        if not payment_intent_id:
            raise AgentPayError("Queued payment is missing payment intent id")
        bootstrap = await self.client.get_bootstrap()
        pending_approval = _find_pending_approval(bootstrap, str(payment_intent_id))
        if not pending_approval:
            raise AgentPayError("No pending approval found for payment intent")
        return await self.client.approve_intent(pending_approval["id"], {"comment": comment} if comment else {})

    async def reject(self, approval_id: str, *, comment: str | None = None) -> Any:
        return await self.client.reject_intent(approval_id, {"comment": comment} if comment else {})

    async def balance(self) -> BalanceRecord:
        wallet_state = await self.client.get_wallet()
        self.wallet = wallet_state
        return BalanceRecord.from_payload(wallet_state)

    async def settle(self) -> SettlementRunRecord:
        return await self.client.run_settlement()

    def budget(
        self,
        limit: AmountLike,
        *,
        counterparty: str | None = None,
        purpose_prefix: str | None = None,
        budget_tags: dict[str, str] | None = None,
        dry_run: bool = False,
    ) -> BudgetContext:
        return budget_scope(
            limit,
            counterparty=counterparty,
            purpose_prefix=purpose_prefix,
            budget_tags=budget_tags,
            dry_run=dry_run,
        )

    def enable_circuit_breaker(
        self,
        *,
        max_requests: int = 10,
        window_seconds: float = 1.0,
        max_spend_usd: AmountLike | None = None,
        max_velocity_usd: AmountLike | None = None,
    ) -> "AsyncWallet":
        self.circuit_breaker = LocalCircuitBreaker(
            CircuitBreakerConfig(
                max_requests=max_requests,
                window_seconds=window_seconds,
                max_spend_usd=max_spend_usd,
                max_velocity_usd=max_velocity_usd,
            )
        )
        return self

    def guard(
        self,
        *,
        amount: AmountLike,
        counterparty: str,
        purpose: str,
        destination: str | None = None,
        budget_tags: dict[str, str] | None = None,
    ) -> Any:
        from .guards import AsyncWalletGuard

        return AsyncWalletGuard(
            self,
            amount=usd_float(amount),
            counterparty=counterparty,
            purpose=purpose,
            destination=destination,
            budget_tags=budget_tags,
        )

    async def simulate_policy(self, *, template_id: str, rollout_mode: str = "shadow") -> PolicySimulationRecord:
        return PolicySimulationRecord.from_payload(
            await self.client.simulate_policy(
                {
                    "agentId": self.agent_id,
                    "templateId": template_id,
                    "rolloutMode": rollout_mode,
                }
            )
        )

    async def list_policy_packs(self) -> PolicyPackCatalogRecord:
        return await self.client.list_policy_packs()

    async def get_policy_pack(self, pack_id: str) -> PolicyPackDetailRecord:
        return await self.client.get_policy_pack(pack_id)

    async def replay_policy_pack(self, pack_id: str, *, mode: str = "shadow") -> PolicyPackReplayResultRecord:
        return await self.client.replay_policy_pack(
            pack_id,
            {
                "agentId": self.agent_id,
                "mode": mode,
            },
        )

    async def apply_policy_pack(self, pack_id: str, *, mode: str = "shadow") -> PolicyPackApplyRecord:
        return await self.client.apply_policy_pack(
            pack_id,
            {
                "agentId": self.agent_id,
                "mode": mode,
            },
        )

    async def rollback_policy_pack(self, pack_id: str) -> PolicyPackRollbackRecord:
        return await self.client.rollback_policy_pack(
            pack_id,
            {
                "agentId": self.agent_id,
            },
        )

    async def audit_review(self) -> AuditReviewRecord:
        return AuditReviewRecord.from_payload(await self.client.get_audit_review())

    async def finance_packet(self) -> FinancePacketRecord:
        return (await self.audit_review()).finance_packet

    async def timeline(self) -> TimelineReportRecord:
        return TimelineReportRecord.from_payload(await self.client.get_intent_timeline())

    async def weekly_review(self) -> WeeklyReviewRecord:
        return WeeklyReviewRecord.from_payload(await self.client.get_weekly_review())

    async def check(
        self,
        *,
        intent: str,
        cost: AmountLike,
        counterparty: str,
        budget_tags: dict[str, str] | None = None,
        business_context: dict[str, Any] | None = None,
    ) -> IntentCheckRecord:
        normalized_cost = usd_decimal(cost)
        decision = await self.pay(
            amount=normalized_cost,
            to=counterparty,
            counterparty=counterparty,
            purpose=intent,
            budget_tags=budget_tags,
            dry_run=True,
            business_context=business_context or {"reason": intent},
        )
        return IntentCheckRecord.from_decision(decision, intent=intent, amount=usd_float(normalized_cost))

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
        return await create_delegated_mandate_async(
            self,
            target_agent_id=target_agent_id,
            daily_limit=daily_limit,
            counterparty=counterparty,
            purpose_prefix=purpose_prefix,
            budget_tags=budget_tags,
            metadata=metadata,
            apply_budget_cap=apply_budget_cap,
        )

    async def review_counterparty(self, counterparty: str) -> CounterpartyReview:
        return await review_counterparty_async(self, counterparty)

    async def begin_governed_action(
        self,
        *,
        action_name: str,
        amount: AmountLike,
        to: str,
        purpose: str,
        run_id: str | None = None,
        intent_key: str | None = None,
        idempotency_key: str | None = None,
        counterparty: str | None = None,
        budget_tags: dict[str, str] | None = None,
        business_context: dict[str, Any] | None = None,
        replay_context: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> AsyncGovernedActionRun:
        generated_run_id, generated_intent_key, generated_idempotency_key = default_run_ids(action_name)
        resolved_run_id, resolved_intent_key, resolved_idempotency_key = (
            run_id or generated_run_id,
            intent_key or generated_intent_key,
            idempotency_key or generated_idempotency_key,
        )
        enriched_context = {
            **dict(business_context or {}),
            "governedRun": {
                "runId": resolved_run_id,
                "intentKey": resolved_intent_key,
                "idempotencyKey": resolved_idempotency_key,
                "actionName": action_name,
            },
        }
        decision = await self.pay(
            amount=amount,
            to=to,
            purpose=purpose,
            counterparty=counterparty,
            budget_tags=budget_tags,
            dry_run=dry_run,
            business_context=enriched_context,
            replay_context=merge_replay_context(
                {
                    **dict(replay_context or {}),
                    "runId": resolved_run_id,
                    "intentKey": resolved_intent_key,
                    "idempotencyKey": resolved_idempotency_key,
                },
                default_source="wallet.begin_governed_action.async",
            ),
        )
        return AsyncGovernedActionRun(
            wallet=self,
            action_name=action_name,
            decision=decision,
            requested_amount_usd=usd_float(amount),
            requested_counterparty=counterparty or to,
            purpose=purpose,
            run_id=resolved_run_id,
            intent_key=resolved_intent_key,
            idempotency_key=resolved_idempotency_key,
            business_context=dict(enriched_context or {}),
        )

    def resume_governed_action(
        self,
        decision: DecisionRecord | Mapping[str, Any],
        *,
        action_name: str,
        amount: AmountLike | None = None,
        counterparty: str | None = None,
        purpose: str | None = None,
        business_context: dict[str, Any] | None = None,
    ) -> AsyncGovernedActionRun:
        resolved = decision if isinstance(decision, DecisionRecord) else DecisionRecord.from_payload(decision)
        generated_run_id, generated_intent_key, generated_idempotency_key = default_run_ids(action_name)
        return AsyncGovernedActionRun(
            wallet=self,
            action_name=action_name,
            decision=resolved,
            requested_amount_usd=usd_float(amount if amount is not None else resolved.amount_decimal),
            requested_counterparty=counterparty or resolved.payment_intent.counterparty or "unknown",
            purpose=purpose or resolved.payment_intent.purpose or action_name,
            run_id=str((resolved.payment_intent.business_context or {}).get("governedRun", {}).get("runId") or generated_run_id),
            intent_key=str((resolved.payment_intent.business_context or {}).get("governedRun", {}).get("intentKey") or generated_intent_key),
            idempotency_key=str((resolved.payment_intent.business_context or {}).get("governedRun", {}).get("idempotencyKey") or generated_idempotency_key),
            business_context=dict(business_context or resolved.payment_intent.business_context or {}),
        )

    async def execute_governed(
        self,
        *,
        action_name: str,
        amount: AmountLike,
        to: str,
        purpose: str,
        callback: Any,
        counterparty: str | None = None,
        budget_tags: dict[str, str] | None = None,
        business_context: dict[str, Any] | None = None,
        replay_context: dict[str, Any] | None = None,
        dry_run: bool = False,
        receipt_id: str | None = None,
        evidence: Mapping[str, Any] | Any | None = None,
        raise_on_error: bool = True,
    ) -> GovernedExecutionRecord:
        run = await self.begin_governed_action(
            action_name=action_name,
            amount=amount,
            to=to,
            purpose=purpose,
            counterparty=counterparty,
            budget_tags=budget_tags,
            business_context=business_context,
            replay_context=replay_context,
            dry_run=dry_run,
        )
        return await run.execute(callback, receipt_id=receipt_id, evidence=evidence, raise_on_error=raise_on_error)


NornrClient = AgentPayClient
NornrWallet = Wallet
