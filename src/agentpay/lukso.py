from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol
from urllib.request import Request, urlopen

from .auth import DEFAULT_BASE_URL
from .client import AgentPayClient, AsyncAgentPayClient, SignedArtifactRecord
from .wallets import AsyncWallet, Wallet


class _LuksoClientLike(Protocol):
    def get_trust_manifest(self) -> Any: ...
    def get_signed_trust_manifest(self) -> Any: ...
    def handshake_trust_manifest(self, payload: dict[str, Any]) -> Any: ...


class _AsyncLuksoClientLike(Protocol):
    async def get_trust_manifest(self) -> Any: ...
    async def get_signed_trust_manifest(self) -> Any: ...
    async def handshake_trust_manifest(self, payload: dict[str, Any]) -> Any: ...


def _coerce_client(source: AgentPayClient | Wallet | _LuksoClientLike) -> _LuksoClientLike:
    if isinstance(source, Wallet):
        return source.client
    return source


def _coerce_async_client(source: AsyncAgentPayClient | AsyncWallet | _AsyncLuksoClientLike) -> _AsyncLuksoClientLike:
    if isinstance(source, AsyncWallet):
        return source.client
    return source


def _coerce_base_url(
    source: AgentPayClient | AsyncAgentPayClient | Wallet | AsyncWallet | object,
    base_url: str | None,
) -> str:
    if base_url:
        return base_url.rstrip("/")
    if isinstance(source, Wallet):
        return source.client.base_url.rstrip("/")
    if isinstance(source, AsyncWallet):
        return source.client.base_url.rstrip("/")
    if isinstance(source, AgentPayClient):
        return source.base_url.rstrip("/")
    if isinstance(source, AsyncAgentPayClient):
        return source.base_url.rstrip("/")
    return DEFAULT_BASE_URL.rstrip("/")


def _mapping_dict(payload: Any) -> dict[str, Any]:
    if isinstance(payload, Mapping):
        return dict(payload)
    if hasattr(payload, "to_dict") and callable(payload.to_dict):
        result = payload.to_dict()
        return dict(result) if isinstance(result, Mapping) else {}
    return {}


def _normalize_address(value: Any, label: str) -> str:
    address = str(value or "").strip()
    if not address:
        raise ValueError(f"{label} is required")
    if not address.startswith("0x") or len(address) != 42:
        raise ValueError(f"{label} must look like an EVM address")
    return address


def _load_json_source(source: str | Path | Mapping[str, Any] | None) -> dict[str, Any]:
    if source is None:
        return {}
    if isinstance(source, Mapping):
        return dict(source)
    path_or_url = str(source).strip()
    if not path_or_url:
        return {}
    if path_or_url.startswith("{"):
        parsed = json.loads(path_or_url)
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        request = Request(path_or_url, headers={"accept": "application/json"})
        with urlopen(request, timeout=10) as response:  # noqa: S310 - explicit allow for adapter fetches
            parsed = json.loads(response.read().decode("utf-8"))
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    file_path = Path(path_or_url).expanduser()
    parsed = json.loads(file_path.read_text(encoding="utf-8"))
    return dict(parsed) if isinstance(parsed, Mapping) else {}


def _normalize_profile_metadata(payload: Mapping[str, Any]) -> tuple[dict[str, Any], str | None]:
    metadata_url = next(
        (
            str(payload.get(key)).strip()
            for key in ("profileMetadataUrl", "metadataUrl", "lsp3ProfileUrl")
            if payload.get(key)
        ),
        None,
    )
    raw_metadata = payload.get("profileMetadata") or payload.get("metadata") or payload.get("lsp3Profile") or {}
    metadata = _load_json_source(raw_metadata if raw_metadata else metadata_url)
    if isinstance(metadata.get("LSP3Profile"), Mapping):
        metadata = dict(metadata["LSP3Profile"])
    return metadata, metadata_url


def _normalize_controllers(payload: Mapping[str, Any]) -> list["LuksoControllerRecord"]:
    raw = payload.get("controllers") or payload.get("controllerPermissions") or []
    if isinstance(raw, Mapping):
        records = []
        for address, details in raw.items():
            if isinstance(details, Mapping):
                records.append(LuksoControllerRecord.from_payload({"address": address, **dict(details)}))
        return records
    return [LuksoControllerRecord.from_payload(item) for item in raw or [] if isinstance(item, Mapping)]


@dataclass(frozen=True)
class LuksoControllerRecord:
    address: str
    label: str | None
    permissions: list[str] = field(default_factory=list)
    allowed_calls: list[str] = field(default_factory=list)
    allowed_targets: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "LuksoControllerRecord":
        raw = dict(payload)
        address = _normalize_address(raw.get("address") or raw.get("controllerAddress"), "controller address")
        return cls(
            address=address,
            label=str(raw.get("label")).strip() if raw.get("label") else None,
            permissions=[str(item) for item in raw.get("permissions") or []],
            allowed_calls=[str(item) for item in raw.get("allowedCalls") or []],
            allowed_targets=[str(item) for item in raw.get("allowedTargets") or []],
            raw=raw,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "label": self.label,
            "permissions": list(self.permissions),
            "allowedCalls": list(self.allowed_calls),
            "allowedTargets": list(self.allowed_targets),
        }


@dataclass(frozen=True)
class LuksoIdentityRecord:
    universal_profile_address: str
    key_manager_address: str | None
    chain_id: str
    network: str
    profile_name: str | None
    profile_metadata_url: str | None
    profile_metadata: dict[str, Any] = field(default_factory=dict)
    controllers: list[LuksoControllerRecord] = field(default_factory=list)
    owners: list[str] = field(default_factory=list)
    interfaces: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "universalProfileAddress": self.universal_profile_address,
            "keyManagerAddress": self.key_manager_address,
            "chainId": self.chain_id,
            "network": self.network,
            "profileName": self.profile_name,
            "profileMetadataUrl": self.profile_metadata_url,
            "profileMetadata": dict(self.profile_metadata),
            "controllers": [item.to_dict() for item in self.controllers],
            "owners": list(self.owners),
            "interfaces": list(self.interfaces),
        }


@dataclass(frozen=True)
class LuksoGovernanceBinding:
    version: str
    generated_at: str
    subject: dict[str, Any]
    root_of_trust: dict[str, Any]
    nornr_binding: dict[str, Any]
    trust_manifest: dict[str, Any]
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "generatedAt": self.generated_at,
            "subject": dict(self.subject),
            "rootOfTrust": dict(self.root_of_trust),
            "nornrBinding": dict(self.nornr_binding),
            "trustManifest": dict(self.trust_manifest),
        }


class LuksoIdentityAdapter:
    """Treat LUKSO as one root-of-trust adapter while keeping NORNR policy and audit concepts first-class."""

    def __init__(
        self,
        source: AgentPayClient | Wallet | _LuksoClientLike,
        *,
        base_url: str | None = None,
        default_chain_id: str = "42",
        default_network: str = "lukso",
    ) -> None:
        self.client = _coerce_client(source)
        self.base_url = _coerce_base_url(source, base_url)
        self.default_chain_id = str(default_chain_id)
        self.default_network = str(default_network)

    def normalize_identity(self, payload: Mapping[str, Any] | str | Path | LuksoIdentityRecord) -> LuksoIdentityRecord:
        if isinstance(payload, LuksoIdentityRecord):
            return payload
        raw = _load_json_source(payload)
        metadata, metadata_url = _normalize_profile_metadata(raw)
        profile_name = next(
            (
                str(value).strip()
                for value in (
                    metadata.get("name"),
                    metadata.get("displayName"),
                    raw.get("profileName"),
                    raw.get("label"),
                )
                if value
            ),
            None,
        )
        key_manager = raw.get("keyManagerAddress") or raw.get("keyManager") or raw.get("lsp6KeyManagerAddress")
        owners = [_normalize_address(item, "owner address") for item in raw.get("owners") or []]
        interfaces = [str(item) for item in raw.get("interfaces") or []]
        return LuksoIdentityRecord(
            universal_profile_address=_normalize_address(
                raw.get("universalProfileAddress") or raw.get("upAddress") or raw.get("profileAddress") or raw.get("address"),
                "universal profile address",
            ),
            key_manager_address=_normalize_address(key_manager, "key manager address") if key_manager else None,
            chain_id=str(raw.get("chainId") or self.default_chain_id),
            network=str(raw.get("network") or self.default_network),
            profile_name=profile_name,
            profile_metadata_url=metadata_url,
            profile_metadata=metadata,
            controllers=_normalize_controllers(raw),
            owners=owners,
            interfaces=interfaces,
            raw=raw,
        )

    def get_workspace_trust_manifest(self, *, signed: bool = True) -> dict[str, Any]:
        payload = self.client.get_signed_trust_manifest() if signed else self.client.get_trust_manifest()
        return _mapping_dict(payload)

    def build_binding(
        self,
        identity: Mapping[str, Any] | str | Path | LuksoIdentityRecord,
        *,
        signed_manifest: Mapping[str, Any] | SignedArtifactRecord | None = None,
        mandate: Mapping[str, Any] | None = None,
        policy_decision: Mapping[str, Any] | None = None,
        counterparty_scope: Mapping[str, Any] | None = None,
        audit_export: Mapping[str, Any] | None = None,
    ) -> LuksoGovernanceBinding:
        normalized_identity = self.normalize_identity(identity)
        manifest = _mapping_dict(signed_manifest) if signed_manifest is not None else self.get_workspace_trust_manifest(signed=True)
        manifest_payload = dict(manifest.get("payload") or manifest)
        subject = dict(manifest_payload.get("subject") or {})
        verification = dict(manifest_payload.get("verification") or {})
        generated_at = str(manifest_payload.get("generatedAt") or manifest.get("generatedAt") or "")
        root_of_trust = {
            "provider": "lukso",
            "kind": "universal_profile",
            "chainId": normalized_identity.chain_id,
            "network": normalized_identity.network,
            "universalProfileAddress": normalized_identity.universal_profile_address,
            "keyManagerAddress": normalized_identity.key_manager_address,
            "profileName": normalized_identity.profile_name,
            "controllerCount": len(normalized_identity.controllers),
            "controllers": [item.to_dict() for item in normalized_identity.controllers],
            "owners": list(normalized_identity.owners),
            "interfaces": list(normalized_identity.interfaces),
        }
        nornr_binding = {
            "mandate": {
                "kind": "business_scope",
                "summary": "NORNR decides what clears in business context, even when authority exists on-chain.",
                **dict(mandate or {}),
            },
            "policyDecision": {
                "surface": "nornr_control_plane",
                "summary": "NORNR keeps policy decision, review posture and release path outside the protocol boundary.",
                **dict(policy_decision or {}),
            },
            "counterpartyScope": {
                "mode": "offchain_review",
                "summary": "Counterparty fit, thresholds and review posture stay in NORNR rather than in the identity layer.",
                **dict(counterparty_scope or {}),
            },
            "auditExport": {
                "artifactKind": "trust_manifest_binding",
                "survivesOutsideControlRoom": True,
                "verificationTier": verification.get("tier"),
                **dict(audit_export or {}),
            },
        }
        payload = {
            "version": "nornr.lukso-binding.v1",
            "generatedAt": generated_at,
            "subject": {
                "workspaceId": subject.get("workspaceId"),
                "displayName": subject.get("displayName") or normalized_identity.profile_name,
                "verificationTier": verification.get("tier"),
                "verificationLabel": verification.get("label"),
            },
            "rootOfTrust": root_of_trust,
            "nornrBinding": nornr_binding,
            "trustManifest": manifest,
        }
        return LuksoGovernanceBinding(
            version=str(payload["version"]),
            generated_at=str(payload["generatedAt"]),
            subject=_mapping_dict(payload["subject"]),
            root_of_trust=_mapping_dict(payload["rootOfTrust"]),
            nornr_binding=_mapping_dict(payload["nornrBinding"]),
            trust_manifest=_mapping_dict(payload["trustManifest"]),
            raw=payload,
        )

    def build_trust_handshake_input(
        self,
        binding: LuksoGovernanceBinding,
        *,
        min_tier: str = "verified",
        min_score: int | None = None,
    ) -> dict[str, Any]:
        return {
            "envelope": dict(binding.trust_manifest),
            "minTier": min_tier,
            "minScore": min_score,
        }

    def handshake(
        self,
        binding: LuksoGovernanceBinding,
        *,
        min_tier: str = "verified",
        min_score: int | None = None,
    ) -> Any:
        return self.client.handshake_trust_manifest(
            self.build_trust_handshake_input(binding, min_tier=min_tier, min_score=min_score),
        )


class AsyncLuksoIdentityAdapter:
    def __init__(
        self,
        source: AsyncAgentPayClient | AsyncWallet | _AsyncLuksoClientLike,
        *,
        base_url: str | None = None,
        default_chain_id: str = "42",
        default_network: str = "lukso",
    ) -> None:
        self.client = _coerce_async_client(source)
        self.base_url = _coerce_base_url(source, base_url)
        self.default_chain_id = str(default_chain_id)
        self.default_network = str(default_network)

    def _sync_helper(self) -> LuksoIdentityAdapter:
        return LuksoIdentityAdapter(
            AgentPayClient(base_url=self.base_url),
            base_url=self.base_url,
            default_chain_id=self.default_chain_id,
            default_network=self.default_network,
        )

    def normalize_identity(self, payload: Mapping[str, Any] | str | Path | LuksoIdentityRecord) -> LuksoIdentityRecord:
        return self._sync_helper().normalize_identity(payload)

    async def get_workspace_trust_manifest(self, *, signed: bool = True) -> dict[str, Any]:
        payload = await self.client.get_signed_trust_manifest() if signed else await self.client.get_trust_manifest()
        return _mapping_dict(payload)

    async def build_binding(
        self,
        identity: Mapping[str, Any] | str | Path | LuksoIdentityRecord,
        *,
        signed_manifest: Mapping[str, Any] | SignedArtifactRecord | None = None,
        mandate: Mapping[str, Any] | None = None,
        policy_decision: Mapping[str, Any] | None = None,
        counterparty_scope: Mapping[str, Any] | None = None,
        audit_export: Mapping[str, Any] | None = None,
    ) -> LuksoGovernanceBinding:
        normalized_identity = self.normalize_identity(identity)
        manifest = _mapping_dict(signed_manifest) if signed_manifest is not None else await self.get_workspace_trust_manifest(signed=True)
        return self._sync_helper().build_binding(
            normalized_identity,
            signed_manifest=manifest,
            mandate=mandate,
            policy_decision=policy_decision,
            counterparty_scope=counterparty_scope,
            audit_export=audit_export,
        )

    def build_trust_handshake_input(
        self,
        binding: LuksoGovernanceBinding,
        *,
        min_tier: str = "verified",
        min_score: int | None = None,
    ) -> dict[str, Any]:
        return {
            "envelope": dict(binding.trust_manifest),
            "minTier": min_tier,
            "minScore": min_score,
        }

    async def handshake(
        self,
        binding: LuksoGovernanceBinding,
        *,
        min_tier: str = "verified",
        min_score: int | None = None,
    ) -> Any:
        return await self.client.handshake_trust_manifest(
            self.build_trust_handshake_input(binding, min_tier=min_tier, min_score=min_score),
        )
