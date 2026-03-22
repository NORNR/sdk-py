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

    def claim_workspace_access_link(self, payload: dict[str, Any]) -> Any:
        return self._request("/api/onboarding/magic-link/claim", _RequestOptions(method="POST", body=payload, authenticated=False))

    def get_bootstrap(self) -> Any:
        return _normalize_bootstrap(self._request("/api/bootstrap"))

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

    def list_workspace_access_links(self) -> list[dict[str, Any]]:
        payload = self._request("/api/workspace/access-links")
        items = payload.get("items") if isinstance(payload, Mapping) else payload
        return [dict(item) for item in items or [] if isinstance(item, Mapping)]

    def create_workspace_access_link(self, payload: dict[str, Any]) -> Any:
        return self._request("/api/workspace/access-links", _RequestOptions(method="POST", body=payload))

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

    def get_close_bundle(self, month: str | None = None, *, fmt: str = "json") -> Any:
        suffix = f"?month={month}&format={fmt}" if month else f"?format={fmt}" if fmt != "json" else ""
        return self._request(
            f"/api/statements/monthly/close-bundle{suffix}",
            _RequestOptions(parse_json=fmt == "json"),
        )

    def get_artifact_evidence(self, month: str | None = None) -> Any:
        suffix = f"?month={month}" if month else ""
        return self._request(f"/api/statements/monthly/evidence{suffix}")

    def compare_close_bundles(self, *, left: str, right: str) -> Any:
        return self._request(f"/api/statements/monthly/compare?left={left}&right={right}")

    def verify_close_bundle_manifest(self, payload: dict[str, Any]) -> Any:
        return self._request("/api/statements/monthly/manifest/verify", _RequestOptions(method="POST", body=payload))

    def get_signed_close_bundle_manifest(self, month: str | None = None) -> Any:
        suffix = f"?month={month}" if month else ""
        return self._request(f"/api/statements/monthly/manifest/signed{suffix}")

    def list_counterparty_profiles(self) -> list[dict[str, Any]]:
        raw = self._request("/api/counterparties/profiles")
        items = raw.get("items") if isinstance(raw, Mapping) else raw
        return [dict(item) for item in items or [] if isinstance(item, Mapping)]

    def get_counterparty_profile(self, profile_id: str) -> dict[str, Any]:
        raw = self._request(f"/api/counterparties/profiles/{profile_id}")
        if isinstance(raw, Mapping) and isinstance(raw.get("profile"), Mapping):
            return dict(raw["profile"])
        return {}

    def list_policy_authoring_drafts(self, *, include_archived: bool = False) -> dict[str, Any]:
        suffix = "?includeArchived=1" if include_archived else ""
        return self._request(f"/api/policies/authoring-drafts{suffix}")

    def get_policy_authoring_draft(self, draft_id: str) -> dict[str, Any]:
        raw = self._request(f"/api/policies/authoring-drafts/{draft_id}")
        if isinstance(raw, Mapping) and isinstance(raw.get("draft"), Mapping):
            return dict(raw["draft"])
        return {}

    def replay_policy_authoring_draft(self, draft_id: str) -> Any:
        return self._request(f"/api/policies/authoring-drafts/{draft_id}/replay", _RequestOptions(method="POST"))

    def duplicate_policy_authoring_draft(self, draft_id: str) -> Any:
        return self._request(f"/api/policies/authoring-drafts/{draft_id}/duplicate", _RequestOptions(method="POST"))

    def publish_policy_authoring_draft(self, draft_id: str, payload: dict[str, Any] | None = None) -> Any:
        return self._request(
            f"/api/policies/authoring-drafts/{draft_id}/publish",
            _RequestOptions(method="POST", body=payload or {}),
        )

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

    async def claim_workspace_access_link(self, payload: dict[str, Any]) -> Any:
        return await self._request("/api/onboarding/magic-link/claim", _RequestOptions(method="POST", body=payload, authenticated=False))

    async def get_bootstrap(self) -> Any:
        return _normalize_bootstrap(await self._request("/api/bootstrap"))

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

    async def get_close_bundle(self, month: str | None = None, *, fmt: str = "json") -> Any:
        suffix = f"?month={month}&format={fmt}" if month else f"?format={fmt}" if fmt != "json" else ""
        return await self._request(
            f"/api/statements/monthly/close-bundle{suffix}",
            _RequestOptions(parse_json=fmt == "json"),
        )

    async def get_artifact_evidence(self, month: str | None = None) -> Any:
        suffix = f"?month={month}" if month else ""
        return await self._request(f"/api/statements/monthly/evidence{suffix}")

    async def compare_close_bundles(self, *, left: str, right: str) -> Any:
        return await self._request(f"/api/statements/monthly/compare?left={left}&right={right}")

    async def verify_close_bundle_manifest(self, payload: dict[str, Any]) -> Any:
        return await self._request("/api/statements/monthly/manifest/verify", _RequestOptions(method="POST", body=payload))

    async def get_signed_close_bundle_manifest(self, month: str | None = None) -> Any:
        suffix = f"?month={month}" if month else ""
        return await self._request(f"/api/statements/monthly/manifest/signed{suffix}")

    async def list_counterparty_profiles(self) -> list[dict[str, Any]]:
        raw = await self._request("/api/counterparties/profiles")
        items = raw.get("items") if isinstance(raw, Mapping) else raw
        return [dict(item) for item in items or [] if isinstance(item, Mapping)]

    async def get_counterparty_profile(self, profile_id: str) -> dict[str, Any]:
        raw = await self._request(f"/api/counterparties/profiles/{profile_id}")
        if isinstance(raw, Mapping) and isinstance(raw.get("profile"), Mapping):
            return dict(raw["profile"])
        return {}

    async def list_policy_authoring_drafts(self, *, include_archived: bool = False) -> dict[str, Any]:
        suffix = "?includeArchived=1" if include_archived else ""
        return await self._request(f"/api/policies/authoring-drafts{suffix}")

    async def get_policy_authoring_draft(self, draft_id: str) -> dict[str, Any]:
        raw = await self._request(f"/api/policies/authoring-drafts/{draft_id}")
        if isinstance(raw, Mapping) and isinstance(raw.get("draft"), Mapping):
            return dict(raw["draft"])
        return {}

    async def replay_policy_authoring_draft(self, draft_id: str) -> Any:
        return await self._request(f"/api/policies/authoring-drafts/{draft_id}/replay", _RequestOptions(method="POST"))

    async def duplicate_policy_authoring_draft(self, draft_id: str) -> Any:
        return await self._request(f"/api/policies/authoring-drafts/{draft_id}/duplicate", _RequestOptions(method="POST"))

    async def publish_policy_authoring_draft(self, draft_id: str, payload: dict[str, Any] | None = None) -> Any:
        return await self._request(
            f"/api/policies/authoring-drafts/{draft_id}/publish",
            _RequestOptions(method="POST", body=payload or {}),
        )

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

    async def list_workspace_access_links(self) -> list[dict[str, Any]]:
        payload = await self._request("/api/workspace/access-links")
        items = payload.get("items") if isinstance(payload, Mapping) else payload
        return [dict(item) for item in items or [] if isinstance(item, Mapping)]

    async def create_workspace_access_link(self, payload: dict[str, Any]) -> Any:
        return await self._request("/api/workspace/access-links", _RequestOptions(method="POST", body=payload))

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


def _normalize_bootstrap(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    surfaces_raw = payload.get("surfaces")
    surfaces = cast(dict[str, Any], surfaces_raw if isinstance(surfaces_raw, dict) else {})
    core = cast(dict[str, Any], surfaces.get("core") if isinstance(surfaces.get("core"), dict) else {})
    governance = cast(dict[str, Any], surfaces.get("governance") if isinstance(surfaces.get("governance"), dict) else {})
    treasury = cast(dict[str, Any], surfaces.get("treasury") if isinstance(surfaces.get("treasury"), dict) else {})
    trust = cast(dict[str, Any], surfaces.get("trust") if isinstance(surfaces.get("trust"), dict) else {})
    access = cast(dict[str, Any], surfaces.get("access") if isinstance(surfaces.get("access"), dict) else {})
    reporting = cast(dict[str, Any], surfaces.get("reporting") if isinstance(surfaces.get("reporting"), dict) else {})

    normalized = dict(payload)
    normalized["surfaces"] = {
        "core": core,
        "governance": governance,
        "treasury": treasury,
        "trust": trust,
        "access": access,
        "reporting": reporting,
    }
    normalized["workspace"] = payload.get("workspace") or core.get("workspace")
    normalized["onboardingProfile"] = payload.get("onboardingProfile") or core.get("onboardingProfile")
    normalized["ownerProfile"] = payload.get("ownerProfile") or core.get("ownerProfile")
    normalized["commercialProfile"] = payload.get("commercialProfile") or core.get("commercialProfile")
    normalized["billingProfile"] = payload.get("billingProfile") or core.get("billingProfile")
    normalized["wallet"] = payload.get("wallet") or core.get("wallet")
    normalized["balanceSummary"] = payload.get("balanceSummary") or core.get("balanceSummary")
    normalized["apiKeys"] = payload.get("apiKeys") or governance.get("apiKeys") or []
    normalized["agents"] = payload.get("agents") or governance.get("agents") or []
    normalized["policies"] = payload.get("policies") or governance.get("policies") or []
    normalized["approvals"] = payload.get("approvals") or governance.get("approvals") or []
    normalized["paymentIntents"] = payload.get("paymentIntents") or governance.get("paymentIntents") or []
    normalized["ledgerEntries"] = payload.get("ledgerEntries") or treasury.get("ledgerEntries") or []
    normalized["receipts"] = payload.get("receipts") or treasury.get("receipts") or []
    normalized["settlementJobs"] = payload.get("settlementJobs") or treasury.get("settlementJobs") or []
    normalized["deposits"] = payload.get("deposits") or treasury.get("deposits") or []
    normalized["payouts"] = payload.get("payouts") or treasury.get("payouts") or []
    normalized["agreements"] = payload.get("agreements") or trust.get("agreements") or []
    normalized["counterparties"] = payload.get("counterparties") or trust.get("counterparties") or []
    normalized["complianceChecks"] = payload.get("complianceChecks") or trust.get("complianceChecks") or []
    normalized["identityProviders"] = payload.get("identityProviders") or trust.get("identityProviders") or []
    normalized["humanAccessGrants"] = payload.get("humanAccessGrants") or trust.get("humanAccessGrants") or []
    normalized["arbitrationConfig"] = payload.get("arbitrationConfig") or trust.get("arbitrationConfig")
    normalized["agencyAccount"] = payload.get("agencyAccount") or trust.get("agencyAccount")
    normalized["currentAccess"] = payload.get("currentAccess") or access.get("currentAccess")
    normalized["artifactSchema"] = payload.get("artifactSchema") or reporting.get("artifactSchema")
    normalized["packetSummary"] = payload.get("packetSummary") or reporting.get("packetSummary")
    return normalized


from .wallets import AsyncWallet, Wallet, _find_pending_approval


NornrClient = AgentPayClient
NornrWallet = Wallet
