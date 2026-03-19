from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from .auth import DEFAULT_BASE_URL
from .client import AgentPayClient, Wallet


class _ProfileClientLike(Protocol):
    def get_trust_profile(self) -> Any: ...
    def get_signed_trust_manifest(self) -> Any: ...
    def get_ecosystem_directory(self) -> Any: ...


def _coerce_client(source: AgentPayClient | Wallet | _ProfileClientLike) -> _ProfileClientLike:
    if isinstance(source, Wallet):
        return source.client
    return source


def _coerce_base_url(source: AgentPayClient | Wallet | _ProfileClientLike, base_url: str | None) -> str:
    if base_url:
        return base_url.rstrip("/")
    if isinstance(source, Wallet):
        return source.client.base_url.rstrip("/")
    if isinstance(source, AgentPayClient):
        return source.base_url.rstrip("/")
    return DEFAULT_BASE_URL.rstrip("/")


@dataclass(frozen=True)
class AgentResume:
    display_name: str
    workspace_id: str
    verification_status: str
    verification_label: str
    score: float
    tier: str
    verified_proof_rate_percent: float
    dispute_rate_percent: float
    refund_rate_percent: float
    completed_agreements: int
    capabilities: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)
    public_profile_url: str | None = None
    signed_manifest: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "displayName": self.display_name,
            "workspaceId": self.workspace_id,
            "verificationStatus": self.verification_status,
            "verificationLabel": self.verification_label,
            "score": self.score,
            "tier": self.tier,
            "verifiedProofRatePercent": self.verified_proof_rate_percent,
            "disputeRatePercent": self.dispute_rate_percent,
            "refundRatePercent": self.refund_rate_percent,
            "completedAgreements": self.completed_agreements,
            "capabilities": self.capabilities,
            "signals": self.signals,
            "publicProfileUrl": self.public_profile_url,
            "signedManifest": self.signed_manifest,
        }


class AgentResumeGenerator:
    """Build a public or portable NORNR resume from existing trust and directory signals."""

    def __init__(
        self,
        source: AgentPayClient | Wallet | _ProfileClientLike,
        *,
        base_url: str | None = None,
    ) -> None:
        self.client = _coerce_client(source)
        self.base_url = _coerce_base_url(source, base_url)

    def build(self) -> AgentResume:
        signed_manifest = self.client.get_signed_trust_manifest()
        manifest = dict(signed_manifest.get("payload") or {})
        verification = dict(manifest.get("verification") or {})
        metrics = dict(manifest.get("metrics") or {})
        subject = dict(manifest.get("subject") or {})
        workspace_id = str(subject.get("workspaceId") or "")

        trust_profile = self.client.get_trust_profile()
        directory = self.client.get_ecosystem_directory()

        capabilities = self._infer_capabilities(directory)
        signals = [str(item) for item in verification.get("signals") or []]
        if not signals and isinstance(trust_profile, Mapping):
            workspace = dict(trust_profile.get("workspace") or {})
            signals = [str(item) for item in workspace.get("signals") or []]

        return AgentResume(
            display_name=str(subject.get("displayName") or workspace_id or "NORNR workspace"),
            workspace_id=workspace_id,
            verification_status=str(verification.get("status") or "unknown"),
            verification_label=str(verification.get("label") or "Unverified"),
            score=float(verification.get("score") or 0),
            tier=str(verification.get("tier") or "unrated"),
            verified_proof_rate_percent=float(metrics.get("verifiedProofRatePercent") or 0),
            dispute_rate_percent=float(metrics.get("disputeRatePercent") or 0),
            refund_rate_percent=float(metrics.get("refundRatePercent") or 0),
            completed_agreements=int(metrics.get("completedAgreements") or 0),
            capabilities=capabilities,
            signals=signals,
            public_profile_url=self.public_profile_url(workspace_id),
            signed_manifest=dict(signed_manifest),
        )

    def public_profile_url(self, workspace_id: str) -> str | None:
        if not workspace_id:
            return None
        root = self.base_url
        if root.endswith("/app"):
            root = root[: -len("/app")]
        return f"{root}/verified/{workspace_id}"

    @staticmethod
    def _infer_capabilities(directory: Any) -> list[str]:
        entries = directory.get("entries") if isinstance(directory, Mapping) else None
        capabilities: set[str] = set()
        for entry in entries or []:
            if isinstance(entry, Mapping):
                for capability in entry.get("capabilities") or []:
                    capabilities.add(str(capability))
        return sorted(capabilities)

