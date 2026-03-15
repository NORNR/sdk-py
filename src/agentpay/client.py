from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import error, request


class AgentPayError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, payload: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


@dataclass(frozen=True)
class _RequestOptions:
    method: str = "GET"
    body: Any = None
    authenticated: bool = True


class AgentPayClient:
    def __init__(self, base_url: str = "http://127.0.0.1:3000", api_key: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def with_api_key(self, api_key: str) -> "AgentPayClient":
        return AgentPayClient(base_url=self.base_url, api_key=api_key)

    def onboard(self, payload: dict[str, Any]) -> Any:
        return self._request("/api/onboarding", _RequestOptions(method="POST", body=payload, authenticated=False))

    def get_bootstrap(self) -> Any:
        return self._request("/api/bootstrap")

    def create_agent(self, payload: dict[str, Any]) -> Any:
        return self._request("/api/agents", _RequestOptions(method="POST", body=payload))

    def create_policy(self, agent_id: str, payload: dict[str, Any]) -> Any:
        return self._request(f"/api/agents/{agent_id}/policies", _RequestOptions(method="POST", body=payload))

    def create_payment_intent(self, payload: dict[str, Any]) -> Any:
        return self._request("/api/payments/intents", _RequestOptions(method="POST", body=payload))

    def get_identity(self) -> Any:
        return self._request("/api/identity")

    def update_identity(self, payload: dict[str, Any]) -> Any:
        return self._request("/api/identity", _RequestOptions(method="POST", body=payload))

    def get_compliance(self) -> Any:
        return self._request("/api/compliance")

    def get_reputation(self) -> Any:
        return self._request("/api/reputation")

    def get_portable_reputation(self) -> Any:
        return self._request("/api/reputation/portable")

    def get_signed_portable_reputation(self) -> Any:
        return self._request("/api/reputation/portable/signed")

    def export_agreement_standard(self) -> Any:
        return self._request("/api/standards/agreements")

    def export_signed_agreement_standard(self) -> Any:
        return self._request("/api/standards/agreements/signed")

    def get_agreement_standard_schema(self) -> Any:
        return self._request("/api/standards/agreement-schema")

    def get_ecosystem_directory(self) -> Any:
        return self._request("/api/ecosystem/directory")

    def get_signed_ecosystem_directory(self) -> Any:
        return self._request("/api/ecosystem/directory/signed")

    def validate_interop_envelope(self, payload: dict[str, Any]) -> Any:
        return self._request("/api/interop/validate", _RequestOptions(method="POST", body=payload))

    def list_events(self) -> Any:
        return self._request("/api/events")

    def list_webhooks(self) -> Any:
        return self._request("/api/webhooks")

    def create_webhook(self, payload: dict[str, Any]) -> Any:
        return self._request("/api/webhooks", _RequestOptions(method="POST", body=payload))

    def list_webhook_deliveries(self) -> Any:
        return self._request("/api/webhooks/deliveries")

    def drain_webhooks(self) -> Any:
        return self._request("/api/webhooks/drain", _RequestOptions(method="POST"))

    def export_audit(self) -> Any:
        return self._request("/api/audit/export")

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

    def get_wallet(self) -> Any:
        return self._request("/api/wallet")

    def create_deposit(self, payload: dict[str, Any]) -> Any:
        return self._request("/api/wallet/deposits", _RequestOptions(method="POST", body=payload))

    def create_payout(self, payload: dict[str, Any]) -> Any:
        return self._request("/api/wallet/payouts", _RequestOptions(method="POST", body=payload))

    def list_settlement_jobs(self) -> Any:
        return self._request("/api/settlement/jobs")

    def run_settlement(self) -> Any:
        return self._request("/api/settlement/run", _RequestOptions(method="POST"))

    def get_reconciliation(self) -> Any:
        return self._request("/api/reconciliation")

    def approve_intent(self, approval_id: str) -> Any:
        return self._request(f"/api/approvals/{approval_id}/approve", _RequestOptions(method="POST"))

    def reject_intent(self, approval_id: str) -> Any:
        return self._request(f"/api/approvals/{approval_id}/reject", _RequestOptions(method="POST"))

    def list_ledger(self, agent_id: str) -> Any:
        return self._request(f"/api/agents/{agent_id}/ledger")

    def list_receipts(self, agent_id: str) -> Any:
        return self._request(f"/api/agents/{agent_id}/receipts")

    def create_api_key(self, label: str) -> Any:
        return self._request("/api/api-keys", _RequestOptions(method="POST", body={"label": label}))

    def _request(self, pathname: str, options: _RequestOptions = _RequestOptions()) -> Any:
        headers: dict[str, str] = {}
        data: bytes | None = None

        if options.body is not None:
            headers["content-type"] = "application/json"
            data = json.dumps(options.body).encode("utf-8")

        if options.authenticated:
            if not self.api_key:
                raise AgentPayError("Missing api_key for authenticated request")
            headers["x-api-key"] = self.api_key

        req = request.Request(
            f"{self.base_url}{pathname}",
            method=options.method,
            headers=headers,
            data=data,
        )

        try:
            with request.urlopen(req) as response:
                payload = response.read().decode("utf-8")
                return json.loads(payload) if payload else None
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            payload = json.loads(body) if body else None
            message = payload.get("message") if isinstance(payload, dict) else None
            raise AgentPayError(message or f"Request failed with status {exc.code}", status_code=exc.code, payload=payload) from exc
        except error.URLError as exc:
            raise AgentPayError(f"Request failed: {exc.reason}") from exc
