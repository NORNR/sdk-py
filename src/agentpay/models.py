from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Iterator, Mapping

try:  # Optional runtime dependency for ML-native model validation.
    from pydantic import BaseModel, ConfigDict
except ImportError:  # pragma: no cover - optional dependency path
    BaseModel = None
    ConfigDict = None

if BaseModel:
    class PaymentIntentPayload(BaseModel):
        model_config = ConfigDict(extra="allow")

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


    class ApprovalPayload(BaseModel):
        model_config = ConfigDict(extra="allow")

        id: str | None = None
        status: str = "unknown"
        paymentIntentId: str | None = None
        reason: str | None = None
        assignedTo: str | None = None
        escalationLevel: str | None = None
        resolutionComment: str | None = None


    class DecisionPayload(BaseModel):
        model_config = ConfigDict(extra="allow")

        paymentIntent: PaymentIntentPayload
        approval: ApprovalPayload | None = None
        requiresApproval: bool = False


    class PolicySimulationPayload(BaseModel):
        model_config = ConfigDict(extra="allow")

        rolloutMode: str = "shadow"
        comparedAt: str | None = None
        candidate: dict[str, Any] = {}
        current: dict[str, Any] | None = None
        delta: dict[str, Any] | None = None
        guidance: list[str] = []


    class FinancePacketPayload(BaseModel):
        model_config = ConfigDict(extra="allow")

        score: float = 0
        headline: str | None = None
        openActions: list[dict[str, Any]] = []
        packetHistory: list[dict[str, Any]] = []
        lastHandoff: dict[str, Any] | None = None


    class AuditReviewPayload(BaseModel):
        model_config = ConfigDict(extra="allow")

        executiveSummary: dict[str, Any] = {}
        financePacket: FinancePacketPayload = FinancePacketPayload()
        evidenceCoverage: dict[str, Any] = {}
        financeActivity: dict[str, Any] = {}


    class TimelineReportPayload(BaseModel):
        model_config = ConfigDict(extra="allow")

        summary: dict[str, Any] = {}
        items: list[dict[str, Any]] = []
        degraded: bool = False


    class WeeklyReviewPayload(BaseModel):
        model_config = ConfigDict(extra="allow")

        summary: dict[str, Any] = {}
        highlights: list[str] = []
        finance: dict[str, Any] = {}
else:
    PaymentIntentPayload = None
    ApprovalPayload = None
    DecisionPayload = None
    PolicySimulationPayload = None
    FinancePacketPayload = None
    AuditReviewPayload = None
    TimelineReportPayload = None
    WeeklyReviewPayload = None


class RecordModel(Mapping[str, Any]):
    """Mapping-compatible wrapper for typed SDK records."""

    _raw: dict[str, Any]
    _pydantic_model: ClassVar[type[BaseModel] | None] = None

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

    def to_pydantic(self) -> BaseModel:
        if not BaseModel or self._pydantic_model is None:
            raise RuntimeError("Install pydantic to use model validation helpers: pip install 'agentpay[pydantic]'")
        return self._pydantic_model.model_validate(self.to_dict())


@dataclass(frozen=True)
class PaymentIntentRecord(RecordModel):
    _pydantic_model: ClassVar[type[BaseModel] | None] = PaymentIntentPayload
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
            amount_usd=float(raw.get("amountUsd") or 0),
            counterparty=raw.get("counterparty"),
            purpose=raw.get("purpose"),
            destination=raw.get("destination"),
            reasons=list(raw.get("reasons") or []),
            budget_tags=raw.get("budgetTags"),
            business_context=raw.get("businessContext"),
            execution_context=raw.get("executionContext"),
            _raw=raw,
        )


@dataclass(frozen=True)
class ApprovalRecord(RecordModel):
    _pydantic_model: ClassVar[type[BaseModel] | None] = ApprovalPayload
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
            available_usd=float(summary.get("availableUsd") or 0),
            reserved_usd=float(summary.get("reservedUsd") or 0),
            pending_settlement_usd=float(summary.get("pendingSettlementUsd") or 0),
            total_fees_usd=float(summary.get("totalFeesUsd") or 0),
            _raw=raw,
        )


@dataclass(frozen=True)
class DecisionRecord(RecordModel):
    _pydantic_model: ClassVar[type[BaseModel] | None] = DecisionPayload
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
    _pydantic_model: ClassVar[type[BaseModel] | None] = PolicySimulationPayload
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
    _pydantic_model: ClassVar[type[BaseModel] | None] = FinancePacketPayload
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
            score=float(raw.get("score") or 0),
            headline=raw.get("headline"),
            open_actions=list(raw.get("openActions") or []),
            packet_history=list(raw.get("packetHistory") or []),
            last_handoff=raw.get("lastHandoff"),
            _raw=raw,
        )


@dataclass(frozen=True)
class AuditReviewRecord(RecordModel):
    _pydantic_model: ClassVar[type[BaseModel] | None] = AuditReviewPayload
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
    _pydantic_model: ClassVar[type[BaseModel] | None] = TimelineReportPayload
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
    _pydantic_model: ClassVar[type[BaseModel] | None] = WeeklyReviewPayload
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


PYDANTIC_AVAILABLE = BaseModel is not None
