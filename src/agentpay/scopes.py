from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


_SCOPE_TEMPLATES = {
    "read-only": ("workspace:read", "events:read", "audit:read"),
    "finance-close": ("workspace:read", "audit:read", "reports:read", "events:read"),
    "browser-guard": ("workspace:read", "payments:write", "events:read", "audit:read"),
    "mcp": ("workspace:read", "payments:write", "approvals:write", "events:read", "audit:read"),
    "openclaw": ("workspace:read", "payments:write", "approvals:write", "events:read", "audit:read"),
    "worker": ("workspace:read", "events:read", "webhooks:read", "audit:read", "reports:read"),
}


@dataclass(frozen=True)
class ScopeTemplate:
    name: str
    scopes: tuple[str, ...]
    summary: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "scopes": list(self.scopes),
            "summary": self.summary,
        }


@dataclass(frozen=True)
class ScopeReview:
    required: tuple[str, ...]
    granted: tuple[str, ...]
    missing: tuple[str, ...]
    excessive: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.missing

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "required": list(self.required),
            "granted": list(self.granted),
            "missing": list(self.missing),
            "excessive": list(self.excessive),
        }


@dataclass(frozen=True)
class CredentialPosture:
    scopes: tuple[str, ...]
    can_write_payments: bool
    can_write_approvals: bool
    can_read_audit: bool
    can_read_finance: bool
    can_admin_api_keys: bool
    posture: str
    summary: str

    def to_dict(self) -> dict[str, object]:
        return {
            "scopes": list(self.scopes),
            "canWritePayments": self.can_write_payments,
            "canWriteApprovals": self.can_write_approvals,
            "canReadAudit": self.can_read_audit,
            "canReadFinance": self.can_read_finance,
            "canAdminApiKeys": self.can_admin_api_keys,
            "posture": self.posture,
            "summary": self.summary,
        }


class InsufficientScopeError(RuntimeError):
    def __init__(self, review: "ScopeReview") -> None:
        super().__init__(f"Missing required NORNR scopes: {', '.join(review.missing) or 'unknown'}")
        self.review = review


def recommended_scopes(surface: str) -> ScopeTemplate:
    key = str(surface or "").strip().lower()
    scopes = _SCOPE_TEMPLATES.get(key)
    if not scopes:
        raise KeyError(f"Unknown NORNR scope surface: {surface}")
    return ScopeTemplate(
        name=key,
        scopes=tuple(scopes),
        summary=f"Least-privilege NORNR API scopes for the {key} integration surface.",
    )


def review_scopes(
    granted_scopes: Iterable[str] | Mapping[str, object] | None,
    *,
    required_scopes: Iterable[str] | None = None,
    surface: str | None = None,
) -> ScopeReview:
    if required_scopes is None:
        if not surface:
            raise ValueError("Provide required_scopes or a named surface")
        required = recommended_scopes(surface).scopes
    else:
        required = tuple(sorted({str(item) for item in required_scopes}))
    if isinstance(granted_scopes, Mapping):
        raw = granted_scopes.get("scopes") or granted_scopes.get("permissions") or []
        raw_items = raw if isinstance(raw, (list, tuple, set, frozenset)) else []
        granted = tuple(sorted({str(item) for item in raw_items}))
    else:
        granted = tuple(sorted({str(item) for item in granted_scopes or []}))
    missing = tuple(item for item in required if item not in granted)
    excessive = tuple(item for item in granted if item not in required)
    return ScopeReview(required=required, granted=granted, missing=missing, excessive=excessive)


def credential_posture(granted_scopes: Iterable[str] | Mapping[str, object] | None) -> CredentialPosture:
    review = review_scopes(granted_scopes, required_scopes=())
    granted = review.granted
    can_write_payments = "payments:write" in granted
    can_write_approvals = "approvals:write" in granted
    can_read_audit = "audit:read" in granted or "reports:read" in granted
    can_read_finance = "reports:read" in granted or "audit:read" in granted
    can_admin_api_keys = any(scope.startswith("api-keys:") for scope in granted)
    if can_write_payments and can_write_approvals:
        posture = "payments-control"
        summary = "This key can initiate governed spend and resolve approval flows."
    elif can_write_payments:
        posture = "payments-write"
        summary = "This key can initiate governed spend but cannot resolve approval flows."
    elif can_read_finance or can_read_audit:
        posture = "read-mostly"
        summary = "This key is finance- or audit-oriented and should not move money."
    else:
        posture = "limited"
        summary = "This key has limited privileges and is suitable for narrow read or routing surfaces."
    return CredentialPosture(
        scopes=granted,
        can_write_payments=can_write_payments,
        can_write_approvals=can_write_approvals,
        can_read_audit=can_read_audit,
        can_read_finance=can_read_finance,
        can_admin_api_keys=can_admin_api_keys,
        posture=posture,
        summary=summary,
    )


def require_scopes(
    granted_scopes: Iterable[str] | Mapping[str, object] | None,
    *,
    required_scopes: Iterable[str] | None = None,
    surface: str | None = None,
) -> ScopeReview:
    review = review_scopes(granted_scopes, required_scopes=required_scopes, surface=surface)
    if not review.ok:
        raise InsufficientScopeError(review)
    return review
