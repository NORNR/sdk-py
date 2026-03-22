from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, ClassVar, Iterator, Mapping

from .money import usd_decimal, usd_float

_RuntimeBaseModel: Any
_RuntimeConfigDict: Any

try:  # Optional runtime dependency for ML-native model validation.
    from pydantic import BaseModel as _RuntimeBaseModel
    from pydantic import ConfigDict as _RuntimeConfigDict
    PYDANTIC_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency path
    _RuntimeBaseModel = None
    _RuntimeConfigDict = None
    PYDANTIC_AVAILABLE = False

PaymentIntentPayloadModel: type[Any] | None = None
ApprovalPayloadModel: type[Any] | None = None
DecisionPayloadModel: type[Any] | None = None
PolicySimulationPayloadModel: type[Any] | None = None
FinancePacketPayloadModel: type[Any] | None = None
AuditReviewPayloadModel: type[Any] | None = None
TimelineReportPayloadModel: type[Any] | None = None
WeeklyReviewPayloadModel: type[Any] | None = None

if PYDANTIC_AVAILABLE and _RuntimeBaseModel is not None and _RuntimeConfigDict is not None:
    class _PaymentIntentPayload(_RuntimeBaseModel):
        model_config = _RuntimeConfigDict(extra="allow")

        id: str | None = None
        status: str = "unknown"
        amountUsd: float = 0
        counterparty: str | None = None
        purpose: str | None = None
        destination: str | None = None
        reasons: list[str] = []
        budgetTags: dict[str, Any] | None = None
        businessContext: dict[str, Any] | None = None
        executionContext: dict[str, Any] | None = None


    class _ApprovalPayload(_RuntimeBaseModel):
        model_config = _RuntimeConfigDict(extra="allow")

        id: str | None = None
        status: str = "unknown"
        paymentIntentId: str | None = None
        reason: str | None = None
        assignedTo: str | None = None
        escalationLevel: str | None = None
        resolutionComment: str | None = None


    class _DecisionPayload(_RuntimeBaseModel):
        model_config = _RuntimeConfigDict(extra="allow")

        paymentIntent: _PaymentIntentPayload
        approval: _ApprovalPayload | None = None
        requiresApproval: bool = False


    class _PolicySimulationPayload(_RuntimeBaseModel):
        model_config = _RuntimeConfigDict(extra="allow")

        rolloutMode: str = "shadow"
        comparedAt: str | None = None
        candidate: dict[str, Any] = {}
        current: dict[str, Any] | None = None
        delta: dict[str, Any] | None = None
        guidance: list[str] = []


    class _FinancePacketPayload(_RuntimeBaseModel):
        model_config = _RuntimeConfigDict(extra="allow")

        score: float = 0
        headline: str | None = None
        openActions: list[dict[str, Any]] = []
        packetHistory: list[dict[str, Any]] = []
        lastHandoff: dict[str, Any] | None = None


    class _AuditReviewPayload(_RuntimeBaseModel):
        model_config = _RuntimeConfigDict(extra="allow")

        executiveSummary: dict[str, Any] = {}
        financePacket: _FinancePacketPayload = _FinancePacketPayload()
        evidenceCoverage: dict[str, Any] = {}
        financeActivity: dict[str, Any] = {}


    class _TimelineReportPayload(_RuntimeBaseModel):
        model_config = _RuntimeConfigDict(extra="allow")

        summary: dict[str, Any] = {}
        items: list[dict[str, Any]] = []
        degraded: bool = False


    class _WeeklyReviewPayload(_RuntimeBaseModel):
        model_config = _RuntimeConfigDict(extra="allow")

        summary: dict[str, Any] = {}
        highlights: list[str] = []
        finance: dict[str, Any] = {}

    PaymentIntentPayloadModel = _PaymentIntentPayload
    ApprovalPayloadModel = _ApprovalPayload
    DecisionPayloadModel = _DecisionPayload
    PolicySimulationPayloadModel = _PolicySimulationPayload
    FinancePacketPayloadModel = _FinancePacketPayload
    AuditReviewPayloadModel = _AuditReviewPayload
    TimelineReportPayloadModel = _TimelineReportPayload
    WeeklyReviewPayloadModel = _WeeklyReviewPayload


class RecordModel(Mapping[str, Any]):
    """Mapping-compatible wrapper for typed SDK records."""

    _raw: dict[str, Any]
    _pydantic_model: ClassVar[type[Any] | None] = None

    def __getitem__(self, key: str) -> Any:
        return self._raw[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._raw)

    def __len__(self) -> int:
        return len(self._raw)

    def get(self, key: str, default: Any = None) -> Any:
        return self._raw.get(key, default)

    def to_dict(self) -> dict[str, Any]:
        return dict(self._raw)

    def to_pydantic(self) -> Any:
        if not PYDANTIC_AVAILABLE or self._pydantic_model is None:
            raise RuntimeError("Install pydantic to use model validation helpers: pip install 'nornr-agentpay[pydantic]'")
        return self._pydantic_model.model_validate(self.to_dict())


@dataclass(frozen=True)
class PaymentIntentRecord(RecordModel):
    _pydantic_model: ClassVar[type[Any] | None] = PaymentIntentPayloadModel
    id: str | None
    status: str
    amount_usd: float
    counterparty: str | None
    purpose: str | None
    destination: str | None
    reasons: list[str]
    budget_tags: dict[str, Any] | None
    business_context: dict[str, Any] | None
    execution_context: dict[str, Any] | None
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "PaymentIntentRecord":
        raw = dict(payload or {})
        return cls(
            id=raw.get("id"),
            status=str(raw.get("status") or "unknown"),
            amount_usd=usd_float(raw.get("amountUsd")),
            counterparty=raw.get("counterparty"),
            purpose=raw.get("purpose"),
            destination=raw.get("destination"),
            reasons=list(raw.get("reasons") or []),
            budget_tags=raw.get("budgetTags"),
            business_context=raw.get("businessContext"),
            execution_context=raw.get("executionContext"),
            _raw=raw,
        )

    @property
    def amount_decimal(self) -> Decimal:
        return usd_decimal(self.amount_usd)


@dataclass(frozen=True)
class ApprovalRecord(RecordModel):
    _pydantic_model: ClassVar[type[Any] | None] = ApprovalPayloadModel
    id: str | None
    status: str
    payment_intent_id: str | None
    reason: str | None
    assigned_to: str | None
    escalation_level: str | None
    resolution_comment: str | None
    approval_url: str | None
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "ApprovalRecord | None":
        if not payload:
            return None
        raw = dict(payload)
        return cls(
            id=raw.get("id"),
            status=str(raw.get("status") or "unknown"),
            payment_intent_id=raw.get("paymentIntentId"),
            reason=raw.get("reason"),
            assigned_to=raw.get("assignedTo"),
            escalation_level=raw.get("escalationLevel"),
            resolution_comment=raw.get("resolutionComment"),
            approval_url=raw.get("approvalUrl"),
            _raw=raw,
        )


@dataclass(frozen=True)
class BalanceRecord(RecordModel):
    available_usd: float
    reserved_usd: float
    pending_settlement_usd: float
    total_fees_usd: float
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "BalanceRecord":
        raw = dict(payload or {})
        summary = raw.get("balanceSummary") or raw
        return cls(
            available_usd=usd_float(summary.get("availableUsd")),
            reserved_usd=usd_float(summary.get("reservedUsd")),
            pending_settlement_usd=usd_float(summary.get("pendingSettlementUsd")),
            total_fees_usd=usd_float(summary.get("totalFeesUsd")),
            _raw=raw,
        )

    @property
    def available_decimal(self) -> Decimal:
        return usd_decimal(self.available_usd)

    @property
    def reserved_decimal(self) -> Decimal:
        return usd_decimal(self.reserved_usd)

    @property
    def pending_settlement_decimal(self) -> Decimal:
        return usd_decimal(self.pending_settlement_usd)

    @property
    def total_fees_decimal(self) -> Decimal:
        return usd_decimal(self.total_fees_usd)


@dataclass(frozen=True)
class DecisionRecord(RecordModel):
    _pydantic_model: ClassVar[type[Any] | None] = DecisionPayloadModel
    payment_intent: PaymentIntentRecord
    approval: ApprovalRecord | None
    requires_approval: bool
    _raw: dict[str, Any] = field(repr=False)

    @property
    def status(self) -> str:
        return self.payment_intent.status

    @property
    def approval_url(self) -> str | None:
        if self.approval and self.approval.approval_url:
            return self.approval.approval_url
        return self._raw.get("approvalUrl")

    @property
    def amount_decimal(self) -> Decimal:
        return self.payment_intent.amount_decimal

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "DecisionRecord":
        raw = dict(payload or {})
        payment_intent = PaymentIntentRecord.from_payload(raw.get("paymentIntent"))
        approval = ApprovalRecord.from_payload(raw.get("approval"))
        requires_approval = bool(raw.get("requiresApproval") or payment_intent.status == "queued")
        normalized = dict(raw)
        normalized["paymentIntent"] = payment_intent.to_dict()
        if approval:
            normalized["approval"] = approval.to_dict()
        normalized["requiresApproval"] = requires_approval
        return cls(
            payment_intent=payment_intent,
            approval=approval,
            requires_approval=requires_approval,
            _raw=normalized,
        )

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "paymentIntentId": self.payment_intent.id,
            "status": self.payment_intent.status,
            "requiresApproval": self.requires_approval,
            "approvalId": self.approval.id if self.approval else None,
            "approvalUrl": self.approval_url,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._raw,
            "paymentIntent": self.payment_intent.to_dict(),
            "approval": self.approval.to_dict() if self.approval else None,
            "requiresApproval": self.requires_approval,
        }


@dataclass(frozen=True)
class PolicySimulationRecord(RecordModel):
    _pydantic_model: ClassVar[type[Any] | None] = PolicySimulationPayloadModel
    rollout_mode: str
    compared_at: str | None
    summary: dict[str, Any]
    current: dict[str, Any] | None
    delta: dict[str, Any] | None
    guidance: list[str]
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "PolicySimulationRecord":
        raw = dict(payload or {})
        candidate = dict(raw.get("candidate") or raw)
        return cls(
            rollout_mode=str(raw.get("rolloutMode") or "shadow"),
            compared_at=raw.get("comparedAt"),
            summary=dict(candidate.get("summary") or {}),
            current=raw.get("current"),
            delta=raw.get("delta"),
            guidance=list(raw.get("guidance") or []) + list(candidate.get("recommendations") or []),
            _raw=raw,
        )


@dataclass(frozen=True)
class FinancePacketRecord(RecordModel):
    _pydantic_model: ClassVar[type[Any] | None] = FinancePacketPayloadModel
    score: float
    headline: str | None
    open_actions: list[dict[str, Any]]
    packet_history: list[dict[str, Any]]
    last_handoff: dict[str, Any] | None
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "FinancePacketRecord":
        raw = dict(payload or {})
        return cls(
            score=usd_float(raw.get("score")),
            headline=raw.get("headline"),
            open_actions=list(raw.get("openActions") or []),
            packet_history=list(raw.get("packetHistory") or []),
            last_handoff=raw.get("lastHandoff"),
            _raw=raw,
        )


@dataclass(frozen=True)
class AuditReviewRecord(RecordModel):
    _pydantic_model: ClassVar[type[Any] | None] = AuditReviewPayloadModel
    executive_summary: dict[str, Any]
    finance_packet: FinancePacketRecord
    evidence_coverage: dict[str, Any]
    finance_activity: dict[str, Any]
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "AuditReviewRecord":
        raw = dict(payload or {})
        return cls(
            executive_summary=dict(raw.get("executiveSummary") or {}),
            finance_packet=FinancePacketRecord.from_payload(raw.get("financePacket")),
            evidence_coverage=dict(raw.get("evidenceCoverage") or {}),
            finance_activity=dict(raw.get("financeActivity") or {}),
            _raw=raw,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._raw,
            "financePacket": self.finance_packet.to_dict(),
        }


@dataclass(frozen=True)
class TimelineReportRecord(RecordModel):
    _pydantic_model: ClassVar[type[Any] | None] = TimelineReportPayloadModel
    summary: dict[str, Any]
    entries: list[dict[str, Any]]
    degraded: bool
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "TimelineReportRecord":
        raw = dict(payload or {})
        return cls(
            summary=dict(raw.get("summary") or {}),
            entries=list(raw.get("items") or []),
            degraded=bool(raw.get("degraded")),
            _raw=raw,
        )


@dataclass(frozen=True)
class WeeklyReviewRecord(RecordModel):
    _pydantic_model: ClassVar[type[Any] | None] = WeeklyReviewPayloadModel
    summary: dict[str, Any]
    highlights: list[str]
    finance: dict[str, Any]
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "WeeklyReviewRecord":
        raw = dict(payload or {})
        return cls(
            summary=dict(raw.get("summary") or {}),
            highlights=list(raw.get("highlights") or []),
            finance=dict(raw.get("finance") or {}),
            _raw=raw,
        )


@dataclass(frozen=True)
class PolicyPackSummaryRecord(RecordModel):
    id: str | None
    title: str | None
    recommended_rollout: str | None
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "PolicyPackSummaryRecord":
        raw = dict(payload or {})
        return cls(
            id=raw.get("id"),
            title=raw.get("title"),
            recommended_rollout=raw.get("recommendedRollout"),
            _raw=raw,
        )


@dataclass(frozen=True)
class PolicyPackInstallRecord(RecordModel):
    id: str | None
    mode: str | None
    rolled_back_at: str | None
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "PolicyPackInstallRecord":
        raw = dict(payload or {})
        return cls(
            id=raw.get("id"),
            mode=raw.get("mode"),
            rolled_back_at=raw.get("rolledBackAt"),
            _raw=raw,
        )


@dataclass(frozen=True)
class PolicyPackReplayRecord(RecordModel):
    replay_id: str | None
    mode: str | None
    summary: dict[str, Any]
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "PolicyPackReplayRecord":
        raw = dict(payload or {})
        candidate = dict(raw.get("candidate") or {})
        return cls(
            replay_id=raw.get("replayId"),
            mode=raw.get("mode"),
            summary=dict(candidate.get("summary") or {}),
            _raw=raw,
        )


@dataclass(frozen=True)
class PolicyPackCatalogRecord(RecordModel):
    recommended_pack_id: str | None
    packs: list[PolicyPackSummaryRecord]
    installs: list[PolicyPackInstallRecord]
    replays: list[PolicyPackReplayRecord]
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "PolicyPackCatalogRecord":
        raw = dict(payload or {})
        packs = [PolicyPackSummaryRecord.from_payload(item) for item in raw.get("packs") or []]
        installs = [PolicyPackInstallRecord.from_payload(item) for item in raw.get("installs") or []]
        replays = [PolicyPackReplayRecord.from_payload(item) for item in raw.get("replays") or []]
        return cls(
            recommended_pack_id=raw.get("recommendedPackId"),
            packs=packs,
            installs=installs,
            replays=replays,
            _raw=raw,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._raw,
            "packs": [item.to_dict() for item in self.packs],
            "installs": [item.to_dict() for item in self.installs],
            "replays": [item.to_dict() for item in self.replays],
        }


@dataclass(frozen=True)
class PolicyPackDetailRecord(RecordModel):
    pack: PolicyPackSummaryRecord
    installs: list[PolicyPackInstallRecord]
    replays: list[PolicyPackReplayRecord]
    recommended: bool
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "PolicyPackDetailRecord":
        raw = dict(payload or {})
        return cls(
            pack=PolicyPackSummaryRecord.from_payload(raw.get("pack")),
            installs=[PolicyPackInstallRecord.from_payload(item) for item in raw.get("installs") or []],
            replays=[PolicyPackReplayRecord.from_payload(item) for item in raw.get("replays") or []],
            recommended=bool(raw.get("recommended")),
            _raw=raw,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._raw,
            "pack": self.pack.to_dict(),
            "installs": [item.to_dict() for item in self.installs],
            "replays": [item.to_dict() for item in self.replays],
        }


@dataclass(frozen=True)
class PolicyPackApplyRecord(RecordModel):
    pack: PolicyPackSummaryRecord
    policy: dict[str, Any]
    install: PolicyPackInstallRecord
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "PolicyPackApplyRecord":
        raw = dict(payload or {})
        return cls(
            pack=PolicyPackSummaryRecord.from_payload(raw.get("pack")),
            policy=dict(raw.get("policy") or {}),
            install=PolicyPackInstallRecord.from_payload(raw.get("install")),
            _raw=raw,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._raw,
            "pack": self.pack.to_dict(),
            "install": self.install.to_dict(),
        }


@dataclass(frozen=True)
class PolicyPackReplayResultRecord(RecordModel):
    pack: PolicyPackSummaryRecord
    replay: PolicyPackReplayRecord
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "PolicyPackReplayResultRecord":
        raw = dict(payload or {})
        return cls(
            pack=PolicyPackSummaryRecord.from_payload(raw.get("pack")),
            replay=PolicyPackReplayRecord.from_payload(raw.get("replay")),
            _raw=raw,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._raw,
            "pack": self.pack.to_dict(),
            "replay": self.replay.to_dict(),
        }


@dataclass(frozen=True)
class PolicyPackRollbackRecord(RecordModel):
    pack: PolicyPackSummaryRecord
    install: PolicyPackInstallRecord
    restored_policies: list[dict[str, Any]]
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "PolicyPackRollbackRecord":
        raw = dict(payload or {})
        return cls(
            pack=PolicyPackSummaryRecord.from_payload(raw.get("pack")),
            install=PolicyPackInstallRecord.from_payload(raw.get("install")),
            restored_policies=list(raw.get("restoredPolicies") or []),
            _raw=raw,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._raw,
            "pack": self.pack.to_dict(),
            "install": self.install.to_dict(),
        }


@dataclass(frozen=True)
class TrustProfileRecord(RecordModel):
    workspace: dict[str, Any]
    counterparties: list[dict[str, Any]]
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "TrustProfileRecord":
        raw = dict(payload or {})
        return cls(
            workspace=dict(raw.get("workspace") or {}),
            counterparties=list(raw.get("counterparties") or []),
            _raw=raw,
        )


@dataclass(frozen=True)
class TrustManifestRecord(RecordModel):
    version: str | None
    verification: dict[str, Any]
    metrics: dict[str, Any]
    subject: dict[str, Any]
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "TrustManifestRecord":
        raw = dict(payload or {})
        return cls(
            version=raw.get("version"),
            verification=dict(raw.get("verification") or {}),
            metrics=dict(raw.get("metrics") or {}),
            subject=dict(raw.get("subject") or {}),
            _raw=raw,
        )


@dataclass(frozen=True)
class WeeklyExpenseReportRecord(RecordModel):
    summary: dict[str, Any]
    operator_posture: dict[str, Any]
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "WeeklyExpenseReportRecord":
        raw = dict(payload or {})
        return cls(
            summary=dict(raw.get("summary") or raw),
            operator_posture=dict(raw.get("operatorPosture") or {}),
            _raw=raw,
        )

    @property
    def total_spend_decimal(self) -> Decimal:
        return usd_decimal(self.summary.get("totalSpendUsd"))

    @property
    def queued_spend_decimal(self) -> Decimal:
        return usd_decimal(self.summary.get("queuedSpendUsd"))


@dataclass(frozen=True)
class KillSwitchRecord(RecordModel):
    id: str | None
    label: str | None
    enabled: bool
    status: str | None
    mode: str | None
    scope: dict[str, Any]
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "KillSwitchRecord":
        raw = dict(payload or {})
        return cls(
            id=raw.get("id"),
            label=raw.get("label"),
            enabled=bool(raw.get("enabled")) or raw.get("status") == "active",
            status=raw.get("status"),
            mode=raw.get("mode"),
            scope=dict(raw.get("scope") or {
                "type": raw.get("scopeType"),
                "value": raw.get("scopeValue"),
            }),
            _raw=raw,
        )


@dataclass(frozen=True)
class ApprovalChainRecord(RecordModel):
    id: str | None
    label: str | None
    steps: list[dict[str, Any]]
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "ApprovalChainRecord":
        raw = dict(payload or {})
        return cls(
            id=raw.get("id"),
            label=raw.get("label"),
            steps=list(raw.get("steps") or []),
            _raw=raw,
        )


@dataclass(frozen=True)
class HardwareBindingRecord(RecordModel):
    id: str | None
    provider: str | None
    status: str | None
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "HardwareBindingRecord":
        raw = dict(payload or {})
        return cls(
            id=raw.get("id"),
            provider=raw.get("provider"),
            status=raw.get("status"),
            _raw=raw,
        )


@dataclass(frozen=True)
class TaxProfileRecord(RecordModel):
    jurisdiction: str | None
    tax_code: str | None
    currency: str | None
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "TaxProfileRecord":
        raw = dict(payload or {})
        return cls(
            jurisdiction=raw.get("jurisdiction"),
            tax_code=raw.get("taxCode"),
            currency=raw.get("currency"),
            _raw=raw,
        )


@dataclass(frozen=True)
class PolicyTemplateRecord(RecordModel):
    id: str | None
    title: str | None
    description: str | None
    recommended_rollout: str | None
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "PolicyTemplateRecord":
        raw = dict(payload or {})
        return cls(
            id=raw.get("id"),
            title=raw.get("title") or raw.get("label") or raw.get("name"),
            description=raw.get("description"),
            recommended_rollout=raw.get("recommendedRollout"),
            _raw=raw,
        )


@dataclass(frozen=True)
class ApiKeyTemplateRecord(RecordModel):
    id: str | None
    label: str | None
    description: str | None
    scopes: list[str]
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "ApiKeyTemplateRecord":
        raw = dict(payload or {})
        return cls(
            id=raw.get("id"),
            label=raw.get("label") or raw.get("title") or raw.get("name"),
            description=raw.get("description"),
            scopes=[str(item) for item in raw.get("scopes") or []],
            _raw=raw,
        )


@dataclass(frozen=True)
class BudgetCapRecord(RecordModel):
    id: str | None
    label: str | None
    status: str | None
    limit_usd: float
    scope: dict[str, Any]
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "BudgetCapRecord":
        raw = dict(payload or {})
        raw = dict(raw.get("budgetCap") or raw)
        return cls(
            id=raw.get("id"),
            label=raw.get("label") or raw.get("title"),
            status=raw.get("status"),
            limit_usd=usd_float(raw.get("limitUsd") or raw.get("dailyLimitUsd")),
            scope=dict(raw.get("scope") or {}),
            _raw=raw,
        )


@dataclass(frozen=True)
class AnomalyRecord(RecordModel):
    id: str | None
    status: str | None
    severity: str | None
    reason: str | None
    counterparty: str | None
    amount_usd: float
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "AnomalyRecord":
        raw = dict(payload or {})
        raw = dict(raw.get("anomaly") or raw)
        return cls(
            id=raw.get("id"),
            status=raw.get("status"),
            severity=raw.get("severity"),
            reason=raw.get("reason") or raw.get("headline"),
            counterparty=raw.get("counterparty"),
            amount_usd=usd_float(raw.get("amountUsd")),
            _raw=raw,
        )


@dataclass(frozen=True)
class IdentityRecord(RecordModel):
    workspace: dict[str, Any]
    subject: dict[str, Any]
    controllers: list[dict[str, Any]]
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "IdentityRecord":
        raw = dict(payload or {})
        return cls(
            workspace=dict(raw.get("workspace") or {}),
            subject=dict(raw.get("subject") or raw.get("agent") or {}),
            controllers=[dict(item) for item in raw.get("controllers") or raw.get("keys") or [] if isinstance(item, Mapping)],
            _raw=raw,
        )


@dataclass(frozen=True)
class ComplianceRecord(RecordModel):
    settings: dict[str, Any]
    kill_switches: list[dict[str, Any]]
    approval_chains: list[dict[str, Any]]
    hardware_bindings: list[dict[str, Any]]
    tax_profile: dict[str, Any]
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "ComplianceRecord":
        raw = dict(payload or {})
        emergency_controls_raw = raw.get("emergencyControls")
        emergency_controls = dict(emergency_controls_raw) if isinstance(emergency_controls_raw, Mapping) else {}
        kill_switches = raw.get("killSwitches") or emergency_controls.get("killSwitches")
        approval_chains = raw.get("approvalChains")
        hardware_bindings = raw.get("hardwareBindings")
        return cls(
            settings=dict(raw.get("settings") or raw),
            kill_switches=[dict(item) for item in kill_switches if isinstance(item, Mapping)] if isinstance(kill_switches, list) else [],
            approval_chains=[dict(item) for item in approval_chains if isinstance(item, Mapping)] if isinstance(approval_chains, list) else [],
            hardware_bindings=[dict(item) for item in hardware_bindings if isinstance(item, Mapping)] if isinstance(hardware_bindings, list) else [],
            tax_profile=dict(raw.get("taxProfile") or {}),
            _raw=raw,
        )


@dataclass(frozen=True)
class ReputationRecord(RecordModel):
    summary: dict[str, Any]
    metrics: dict[str, Any]
    verification: dict[str, Any]
    highlights: list[str]
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "ReputationRecord":
        raw = dict(payload or {})
        return cls(
            summary=dict(raw.get("summary") or raw.get("subject") or {}),
            metrics=dict(raw.get("metrics") or {}),
            verification=dict(raw.get("verification") or {}),
            highlights=[str(item) for item in raw.get("highlights") or []],
            _raw=raw,
        )


@dataclass(frozen=True)
class TrustTierRecord(RecordModel):
    id: str | None
    label: str | None
    status: str | None
    score: float
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "TrustTierRecord":
        raw = dict(payload or {})
        return cls(
            id=raw.get("id") or raw.get("tier"),
            label=raw.get("label") or raw.get("title") or raw.get("tier"),
            status=raw.get("status"),
            score=usd_float(raw.get("score")),
            _raw=raw,
        )


@dataclass(frozen=True)
class SignedArtifactRecord(RecordModel):
    version: str | None
    subject: dict[str, Any]
    signature: dict[str, Any]
    payload: dict[str, Any]
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "SignedArtifactRecord":
        raw = dict(payload or {})
        return cls(
            version=raw.get("version"),
            subject=dict(raw.get("subject") or {}),
            signature=dict(raw.get("signature") or raw.get("verification") or {}),
            payload=dict(raw.get("payload") or raw.get("manifest") or raw),
            _raw=raw,
        )


@dataclass(frozen=True)
class AgreementStandardRecord(RecordModel):
    version: str | None
    title: str | None
    schema: dict[str, Any]
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "AgreementStandardRecord":
        raw = dict(payload or {})
        return cls(
            version=raw.get("version"),
            title=raw.get("title") or raw.get("name"),
            schema=dict(raw.get("schema") or raw.get("fields") or {}),
            _raw=raw,
        )


@dataclass(frozen=True)
class EcosystemDirectoryRecord(RecordModel):
    version: str | None
    generated_at: str | None
    entries: list[dict[str, Any]]
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "EcosystemDirectoryRecord":
        raw = dict(payload or {})
        return cls(
            version=raw.get("version"),
            generated_at=raw.get("generatedAt"),
            entries=[dict(item) for item in raw.get("entries") or raw.get("agents") or [] if isinstance(item, Mapping)],
            _raw=raw,
        )


@dataclass(frozen=True)
class InteropValidationRecord(RecordModel):
    valid: bool
    errors: list[str]
    summary: dict[str, Any]
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "InteropValidationRecord":
        raw = dict(payload or {})
        return cls(
            valid=bool(raw.get("valid") or raw.get("ok")),
            errors=[str(item) for item in raw.get("errors") or []],
            summary=dict(raw.get("summary") or raw),
            _raw=raw,
        )


@dataclass(frozen=True)
class EventRecord(RecordModel):
    id: str | None
    event_type: str | None
    status: str | None
    created_at: str | None
    summary: str | None
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "EventRecord":
        raw = dict(payload or {})
        return cls(
            id=raw.get("id"),
            event_type=raw.get("type") or raw.get("eventType"),
            status=raw.get("status"),
            created_at=raw.get("createdAt"),
            summary=raw.get("summary") or raw.get("headline"),
            _raw=raw,
        )


@dataclass(frozen=True)
class WebhookRecord(RecordModel):
    id: str | None
    label: str | None
    status: str | None
    url: str | None
    event_types: list[str]
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "WebhookRecord":
        raw = dict(payload or {})
        raw = dict(raw.get("endpoint") or raw.get("webhook") or raw)
        return cls(
            id=raw.get("id"),
            label=raw.get("label") or raw.get("name"),
            status=raw.get("status"),
            url=raw.get("url"),
            event_types=[str(item) for item in raw.get("eventTypes") or []],
            _raw=raw,
        )


@dataclass(frozen=True)
class WebhookDeliveryRecord(RecordModel):
    id: str | None
    event_type: str | None
    status: str | None
    endpoint_id: str | None
    created_at: str | None
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "WebhookDeliveryRecord":
        raw = dict(payload or {})
        return cls(
            id=raw.get("id") or raw.get("deliveryId"),
            event_type=raw.get("eventType"),
            status=raw.get("status"),
            endpoint_id=raw.get("endpointId"),
            created_at=raw.get("createdAt"),
            _raw=raw,
        )


@dataclass(frozen=True)
class WebhookDrainRecord(RecordModel):
    drained_count: int
    pending_count: int
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "WebhookDrainRecord":
        raw = dict(payload or {})
        return cls(
            drained_count=int(raw.get("drainedCount") or raw.get("processed") or 0),
            pending_count=int(raw.get("pendingCount") or 0),
            _raw=raw,
        )


@dataclass(frozen=True)
class AuditExportRecord(RecordModel):
    exported_at: str | None
    status: str | None
    artifacts: list[dict[str, Any]]
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "AuditExportRecord":
        raw = dict(payload or {})
        return cls(
            exported_at=raw.get("exportedAt"),
            status=raw.get("status"),
            artifacts=[dict(item) for item in raw.get("artifacts") or raw.get("exports") or [] if isinstance(item, Mapping)],
            _raw=raw,
        )


@dataclass(frozen=True)
class CostReportRecord(RecordModel):
    summary: dict[str, Any]
    entries: list[dict[str, Any]]
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "CostReportRecord":
        raw = dict(payload or {})
        return cls(
            summary=dict(raw.get("summary") or raw),
            entries=[
                dict(item)
                for item in raw.get("items") or raw.get("entries") or raw.get("rows") or []
                if isinstance(item, Mapping)
            ],
            _raw=raw,
        )


@dataclass(frozen=True)
class MonthlyStatementRecord(RecordModel):
    month: str | None
    summary: dict[str, Any]
    entries: list[dict[str, Any]]
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "MonthlyStatementRecord":
        raw = dict(payload or {})
        statement = dict(raw.get("statement") or raw)
        return cls(
            month=statement.get("month"),
            summary=dict(statement.get("summary") or raw.get("summary") or {}),
            entries=[
                dict(item)
                for item in statement.get("entries") or statement.get("transactions") or statement.get("lines") or raw.get("entries") or []
                if isinstance(item, Mapping)
            ],
            _raw=raw,
        )


@dataclass(frozen=True)
class WalletStateRecord(RecordModel):
    id: str | None
    balance_summary: dict[str, Any]
    available_usd: float
    reserved_usd: float
    pending_settlement_usd: float
    total_fees_usd: float
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "WalletStateRecord":
        raw = dict(payload or {})
        summary = dict(raw.get("balanceSummary") or raw)
        return cls(
            id=raw.get("id"),
            balance_summary=summary,
            available_usd=usd_float(summary.get("availableUsd")),
            reserved_usd=usd_float(summary.get("reservedUsd")),
            pending_settlement_usd=usd_float(summary.get("pendingSettlementUsd")),
            total_fees_usd=usd_float(summary.get("totalFeesUsd")),
            _raw=raw,
        )


@dataclass(frozen=True)
class SettlementJobRecord(RecordModel):
    id: str | None
    status: str | None
    created_at: str | None
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "SettlementJobRecord":
        raw = dict(payload or {})
        return cls(
            id=raw.get("id"),
            status=raw.get("status"),
            created_at=raw.get("createdAt"),
            _raw=raw,
        )


@dataclass(frozen=True)
class SettlementRunRecord(RecordModel):
    processed: int
    status: str | None
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "SettlementRunRecord":
        raw = dict(payload or {})
        return cls(
            processed=int(raw.get("processed") or 0),
            status=raw.get("status"),
            _raw=raw,
        )


@dataclass(frozen=True)
class ReconciliationRecord(RecordModel):
    summary: dict[str, Any]
    entries: list[dict[str, Any]]
    mismatches: list[dict[str, Any]]
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "ReconciliationRecord":
        raw = dict(payload or {})
        return cls(
            summary=dict(raw.get("summary") or raw),
            entries=[dict(item) for item in raw.get("items") or [] if isinstance(item, Mapping)],
            mismatches=[dict(item) for item in raw.get("mismatches") or [] if isinstance(item, Mapping)],
            _raw=raw,
        )


@dataclass(frozen=True)
class LedgerEntryRecord(RecordModel):
    id: str | None
    status: str | None
    counterparty: str | None
    purpose: str | None
    amount_usd: float
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "LedgerEntryRecord":
        raw = dict(payload or {})
        return cls(
            id=raw.get("id") or raw.get("paymentIntentId"),
            status=raw.get("status") or raw.get("type"),
            counterparty=raw.get("counterparty") or raw.get("destination"),
            purpose=raw.get("purpose"),
            amount_usd=usd_float(raw.get("amountUsd") or raw.get("totalUsd") or raw.get("amount")),
            _raw=raw,
        )


@dataclass(frozen=True)
class ReceiptRecord(RecordModel):
    id: str | None
    status: str | None
    payment_intent_id: str | None
    evidence_url: str | None
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "ReceiptRecord":
        raw = dict(payload or {})
        raw = dict(raw.get("receipt") or raw)
        return cls(
            id=raw.get("id"),
            status=raw.get("status"),
            payment_intent_id=raw.get("paymentIntentId"),
            evidence_url=raw.get("url") or raw.get("evidenceUrl"),
            _raw=raw,
        )


@dataclass(frozen=True)
class ApiKeyRecord(RecordModel):
    id: str | None
    label: str | None
    status: str | None
    last_four: str | None
    created_at: str | None
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "ApiKeyRecord":
        raw = dict(payload or {})
        raw = dict(raw.get("apiKey") or raw)
        return cls(
            id=raw.get("id"),
            label=raw.get("label") or raw.get("name"),
            status=raw.get("status"),
            last_four=raw.get("lastFour") or raw.get("preview"),
            created_at=raw.get("createdAt"),
            _raw=raw,
        )


@dataclass(frozen=True)
class PolicyWorkbenchRecord(RecordModel):
    summary: dict[str, Any]
    guidance: list[str]
    candidate: dict[str, Any]
    current: dict[str, Any]
    _raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "PolicyWorkbenchRecord":
        raw = dict(payload or {})
        return cls(
            summary=dict(raw.get("summary") or {}),
            guidance=[str(item) for item in raw.get("guidance") or []],
            candidate=dict(raw.get("candidate") or {}),
            current=dict(raw.get("current") or {}),
            _raw=raw,
        )
