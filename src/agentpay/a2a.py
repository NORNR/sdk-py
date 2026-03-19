from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Mapping, Protocol

from .client import AgentPayClient, ValidationError, Wallet
from .money import AmountLike, usd_decimal, usd_float


class _AgreementClientLike(Protocol):
    def create_agreement(self, payload: dict[str, Any]) -> Any: ...
    def submit_milestone_proof(self, agreement_id: str, milestone_id: str, payload: dict[str, Any]) -> Any: ...
    def release_milestone(self, agreement_id: str, milestone_id: str) -> Any: ...
    def dispute_milestone(self, agreement_id: str, milestone_id: str, payload: dict[str, Any]) -> Any: ...


def _coerce_client(source: AgentPayClient | Wallet | _AgreementClientLike) -> _AgreementClientLike:
    if isinstance(source, Wallet):
        return source.client
    return source


def _require_non_empty(value: str | None, field_name: str) -> str:
    if not value or not str(value).strip():
        raise ValidationError(f"{field_name} is required")
    return str(value).strip()


@dataclass(frozen=True)
class AgentAttestation:
    agent_id: str
    role: str
    summary: str
    status: str = "confirmed"
    artifact_hash: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "agentId": self.agent_id,
            "role": self.role,
            "summary": self.summary,
            "status": self.status,
            "metadata": self.metadata or None,
        }
        if self.artifact_hash:
            payload["artifactHash"] = self.artifact_hash
        return payload


@dataclass(frozen=True)
class A2AMilestone:
    title: str
    amount_usd: Decimal
    accepted_result_types: tuple[str, ...] = ("delivery_attestation",)

    def to_payload(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "amountUsd": usd_float(self.amount_usd),
            "proofRequirements": {
                "requireSummary": True,
                "requireArtifactHash": True,
                "acceptedResultTypes": list(self.accepted_result_types),
                "customChecks": [
                    "worker_attestation_required",
                    "buyer_attestation_required",
                    "nornr_handshake_required",
                ],
            },
        }


@dataclass(frozen=True)
class EscrowHandshake:
    agreement_id: str
    milestone_id: str
    buyer_agent_id: str
    worker_agent_id: str
    worker_destination: str
    escrow_required_usd: Decimal
    agreement: dict[str, Any]

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "agreementId": self.agreement_id,
            "milestoneId": self.milestone_id,
            "buyerAgentId": self.buyer_agent_id,
            "workerAgentId": self.worker_agent_id,
            "workerDestination": self.worker_destination,
            "escrowRequiredUsd": usd_float(self.escrow_required_usd),
        }


@dataclass(frozen=True)
class EscrowHandshakeOutcome:
    agreement_id: str
    milestone_id: str
    proof_submission: dict[str, Any]
    settlement_action: str
    settlement_response: dict[str, Any]


class A2AEscrow:
    """High-level proof-backed agent-to-agent escrow helpers."""

    def __init__(self, source: AgentPayClient | Wallet | _AgreementClientLike) -> None:
        self.client = _coerce_client(source)

    def create_three_way_handshake(
        self,
        *,
        buyer_agent_id: str,
        worker_agent_id: str,
        worker_destination: str,
        title: str,
        milestone_title: str,
        amount_usd: AmountLike,
        counterparty_name: str | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EscrowHandshake:
        normalized_amount = usd_decimal(amount_usd)
        agreement = self.client.create_agreement(
            {
                "buyerAgentId": _require_non_empty(buyer_agent_id, "buyer_agent_id"),
                "title": _require_non_empty(title, "title"),
                "description": description or "Proof-backed agent-to-agent escrow with dual attestation.",
                "counterpartyName": counterparty_name or worker_agent_id,
                "counterpartyDestination": _require_non_empty(worker_destination, "worker_destination"),
                "metadata": {
                    "workerAgentId": _require_non_empty(worker_agent_id, "worker_agent_id"),
                    "handshakeMode": "dual_attestation",
                    **(metadata or {}),
                },
                "milestones": [A2AMilestone(title=milestone_title, amount_usd=normalized_amount).to_payload()],
            }
        )
        agreement_payload = agreement.get("agreement") or agreement
        milestones = list(agreement_payload.get("milestones") or [])
        if not milestones:
            raise ValidationError("NORNR did not return any milestone for the escrow handshake.")
        milestone = milestones[0]
        return EscrowHandshake(
            agreement_id=str(agreement_payload["id"]),
            milestone_id=str(milestone["id"]),
            buyer_agent_id=buyer_agent_id,
            worker_agent_id=worker_agent_id,
            worker_destination=worker_destination,
            escrow_required_usd=usd_decimal(
                agreement_payload.get("escrowRequiredUsd") or milestone.get("totalDebitUsd") or normalized_amount
            ),
            agreement=dict(agreement_payload),
        )

    def build_handshake_proof(
        self,
        *,
        worker: AgentAttestation,
        buyer: AgentAttestation,
        artifact_hash: str,
        summary: str,
        url: str | None = None,
        result_type: str = "delivery_attestation",
        checks: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        worker_payload = worker.to_dict()
        buyer_payload = buyer.to_dict()
        if worker_payload["status"] != "confirmed":
            raise ValidationError("worker attestation must be confirmed before NORNR can release escrow.")
        if buyer_payload["status"] not in {"confirmed", "accepted"}:
            raise ValidationError("buyer attestation must confirm delivery before NORNR can release escrow.")
        return {
            "summary": _require_non_empty(summary, "summary"),
            "url": url,
            "artifactHash": _require_non_empty(artifact_hash, "artifact_hash"),
            "resultType": result_type,
            "checks": list(checks or ["worker_attestation_received", "buyer_attestation_received", "nornr_handshake_complete"]),
            "attestations": {
                "worker": worker_payload,
                "buyer": buyer_payload,
            },
            "metadata": {
                "handshakeMode": "dual_attestation",
                **(metadata or {}),
            },
        }

    def submit_handshake_proof(
        self,
        *,
        agreement_id: str,
        milestone_id: str,
        worker: AgentAttestation,
        buyer: AgentAttestation,
        artifact_hash: str,
        summary: str,
        url: str | None = None,
        result_type: str = "delivery_attestation",
        checks: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = self.build_handshake_proof(
            worker=worker,
            buyer=buyer,
            artifact_hash=artifact_hash,
            summary=summary,
            url=url,
            result_type=result_type,
            checks=checks,
            metadata=metadata,
        )
        response = self.client.submit_milestone_proof(agreement_id, milestone_id, payload)
        return dict(response) if isinstance(response, Mapping) else {"result": response}

    def settle_handshake(
        self,
        *,
        agreement_id: str,
        milestone_id: str,
        worker: AgentAttestation,
        buyer: AgentAttestation,
        artifact_hash: str,
        summary: str,
        url: str | None = None,
        dispute_reason: str | None = None,
        resolution_summary: str | None = None,
    ) -> EscrowHandshakeOutcome:
        proof_submission = self.submit_handshake_proof(
            agreement_id=agreement_id,
            milestone_id=milestone_id,
            worker=worker,
            buyer=buyer,
            artifact_hash=artifact_hash,
            summary=summary,
            url=url,
        )
        if worker.status == "confirmed" and buyer.status in {"confirmed", "accepted"}:
            action = "release"
            response = self.client.release_milestone(agreement_id, milestone_id)
        else:
            action = "dispute"
            response = self.client.dispute_milestone(
                agreement_id,
                milestone_id,
                {
                    "reason": dispute_reason or "Dual attestation did not complete.",
                    "resolutionSummary": resolution_summary or "Escrow held until buyer and worker attestations align.",
                },
            )
        return EscrowHandshakeOutcome(
            agreement_id=agreement_id,
            milestone_id=milestone_id,
            proof_submission=dict(proof_submission),
            settlement_action=action,
            settlement_response=dict(response),
        )
