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
    parse_json: bool = True


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

    def list_policy_templates(self) -> Any:
        return self._request("/api/policy-templates")

    def list_api_key_templates(self) -> Any:
        return self._request("/api/api-key-templates")

    def list_budget_caps(self) -> Any:
        return self._request("/api/budget-caps")

    def create_budget_cap(self, payload: dict[str, Any]) -> Any:
        return self._request("/api/budget-caps", _RequestOptions(method="POST", body=payload))

    def simulate_policy(self, payload: dict[str, Any]) -> Any:
        return self._request("/api/policies/simulate", _RequestOptions(method="POST", body=payload))

    def diff_policy(self, payload: dict[str, Any]) -> Any:
        return self._request("/api/policies/diff", _RequestOptions(method="POST", body=payload))

    def list_anomalies(self) -> Any:
        return self._request("/api/anomalies")

    def update_anomaly(self, anomaly_id: str, payload: dict[str, Any]) -> Any:
        return self._request(f"/api/anomalies/{anomaly_id}", _RequestOptions(method="POST", body=payload))

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

    def test_webhook(self, endpoint_id: str, payload: dict[str, Any] | None = None) -> Any:
        return self._request(
            f"/api/webhooks/{endpoint_id}/test",
            _RequestOptions(method="POST", body=payload or {"drainNow": True}),
        )

    def replay_webhook(self, endpoint_id: str, payload: dict[str, Any]) -> Any:
        return self._request(f"/api/webhooks/{endpoint_id}/replay", _RequestOptions(method="POST", body=payload))

    def export_audit(self) -> Any:
        return self._request("/api/audit/export")

    def get_cost_report(self, fmt: str = "json") -> Any:
        return self._request(f"/api/reporting/costs?format={fmt}", _RequestOptions(parse_json=fmt == "json"))

    def get_monthly_statement(self, month: str | None = None) -> Any:
        suffix = f"?month={month}" if month else ""
        return self._request(f"/api/statements/monthly{suffix}")

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

    def approve_intent(self, approval_id: str, payload: dict[str, Any] | None = None) -> Any:
        return self._request(f"/api/approvals/{approval_id}/approve", _RequestOptions(method="POST", body=payload or {}))

    def reject_intent(self, approval_id: str, payload: dict[str, Any] | None = None) -> Any:
        return self._request(f"/api/approvals/{approval_id}/reject", _RequestOptions(method="POST", body=payload or {}))

    def list_ledger(self, agent_id: str) -> Any:
        return self._request(f"/api/agents/{agent_id}/ledger")

    def list_receipts(self, agent_id: str) -> Any:
        return self._request(f"/api/agents/{agent_id}/receipts")

    def attach_receipt_evidence(self, receipt_id: str, payload: dict[str, Any]) -> Any:
        return self._request(f"/api/receipts/{receipt_id}/evidence", _RequestOptions(method="POST", body=payload))

    def export_cost_report(self, fmt: str = "csv") -> Any:
        return self._request(f"/api/reporting/costs?format={fmt}", _RequestOptions(parse_json=fmt == "json"))

    def list_api_keys(self) -> Any:
        return self._request("/api/api-keys")

    def create_api_key(self, payload: str | dict[str, Any]) -> Any:
        body = {"label": payload} if isinstance(payload, str) else payload
        return self._request("/api/api-keys", _RequestOptions(method="POST", body=body))

    def revoke_api_key(self, api_key_id: str, payload: dict[str, Any] | None = None) -> Any:
        return self._request(
            f"/api/api-keys/{api_key_id}/revoke",
            _RequestOptions(method="POST", body=payload or {}),
        )

    def rotate_api_key(self, api_key_id: str, payload: dict[str, Any] | None = None) -> Any:
        return self._request(
            f"/api/api-keys/{api_key_id}/rotate",
            _RequestOptions(method="POST", body=payload or {}),
        )

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
                if not payload:
                    return None
                return json.loads(payload) if options.parse_json else payload
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            payload = json.loads(body) if body else None
            message = payload.get("message") if isinstance(payload, dict) else None
            raise AgentPayError(message or f"Request failed with status {exc.code}", status_code=exc.code, payload=payload) from exc
        except error.URLError as exc:
            raise AgentPayError(f"Request failed: {exc.reason}") from exc


def _looks_like_evm_address(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("0x") and len(value) == 42


def _first_agent(bootstrap: dict[str, Any]) -> dict[str, Any]:
    agents = bootstrap.get("agents") or []
    if not agents:
        raise AgentPayError("Wallet bootstrap did not return any agents")
    return agents[0]


def _find_pending_approval(bootstrap: dict[str, Any], payment_intent_id: str) -> dict[str, Any] | None:
    approvals = bootstrap.get("approvals") or []
    return next((item for item in approvals if item.get("paymentIntentId") == payment_intent_id), None)


@dataclass
class Wallet:
    client: AgentPayClient
    workspace: dict[str, Any]
    agent: dict[str, Any]
    wallet: dict[str, Any] | None
    api_key: dict[str, Any] | None
    policy: dict[str, Any] | None = None

    @classmethod
    def create(
        cls,
        *,
        owner: str,
        daily_limit: float = 100,
        base_url: str = "http://127.0.0.1:3000",
        workspace_name: str | None = None,
        require_approval_above: float | None = None,
        max_transaction: float | None = None,
        whitelist: list[str] | None = None,
        auto_pause_on_anomaly: bool = False,
        review_on_anomaly: bool = False,
        starting_balance: float = 100,
    ) -> "Wallet":
        public_client = AgentPayClient(base_url=base_url)
        onboarding = public_client.onboard(
            {
                "workspaceName": workspace_name or f"{owner} workspace",
                "agentName": owner,
                "dailyLimitUsd": daily_limit,
                "requireApprovalOverUsd": require_approval_above,
                "maxTransactionUsd": max_transaction,
                "counterpartyAllowlist": whitelist,
                "autoPauseOnAnomaly": auto_pause_on_anomaly,
                "reviewOnAnomaly": review_on_anomaly,
                "startingBalanceUsd": starting_balance,
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
        api_key: str,
        base_url: str = "http://127.0.0.1:3000",
        agent_id: str | None = None,
    ) -> "Wallet":
        client = AgentPayClient(base_url=base_url, api_key=api_key)
        bootstrap = client.get_bootstrap()
        agent = next((item for item in bootstrap.get("agents", []) if item.get("id") == agent_id), None) if agent_id else None
        return cls(
            client=client,
            workspace=bootstrap["workspace"],
            agent=agent or _first_agent(bootstrap),
            wallet=bootstrap.get("wallet"),
            api_key={"key": api_key},
        )

    @property
    def agent_id(self) -> str:
        return self.agent["id"]

    @property
    def workspace_id(self) -> str:
        return self.workspace["id"]

    def refresh(self) -> dict[str, Any]:
        bootstrap = self.client.get_bootstrap()
        self.workspace = bootstrap["workspace"]
        self.agent = next((item for item in bootstrap.get("agents", []) if item.get("id") == self.agent_id), _first_agent(bootstrap))
        self.wallet = bootstrap.get("wallet")
        return bootstrap

    def pay(
        self,
        *,
        amount: float,
        to: str,
        purpose: str | None = None,
        counterparty: str | None = None,
        budget_tags: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        destination = to if _looks_like_evm_address(to) else None
        resolved_counterparty = counterparty or (to if not destination else "external")
        result = self.client.create_payment_intent(
            {
                "agentId": self.agent_id,
                "amountUsd": amount,
                "counterparty": resolved_counterparty,
                "destination": destination,
                "budgetTags": budget_tags,
                "purpose": purpose or f"agent payment to {resolved_counterparty}",
            }
        )
        payment_intent = result.get("paymentIntent") or {}
        if payment_intent.get("status") == "queued":
            bootstrap = self.client.get_bootstrap()
            approval = _find_pending_approval(bootstrap, payment_intent.get("id", ""))
            if approval:
                result["approval"] = approval
            result["requiresApproval"] = approval is not None
        else:
            result["requiresApproval"] = False
        return result

    def approve_if_needed(self, payment: dict[str, Any], *, comment: str | None = None) -> dict[str, Any]:
        approval = payment.get("approval")
        if approval:
            return self.client.approve_intent(approval["id"], {"comment": comment} if comment else {})
        payment_intent = payment.get("paymentIntent") or {}
        if payment_intent.get("status") != "queued":
            return payment
        bootstrap = self.client.get_bootstrap()
        pending_approval = _find_pending_approval(bootstrap, payment_intent["id"])
        if not pending_approval:
            raise AgentPayError("No pending approval found for payment intent")
        return self.client.approve_intent(pending_approval["id"], {"comment": comment} if comment else {})

    def balance(self) -> dict[str, Any]:
        wallet_state = self.client.get_wallet()
        self.wallet = wallet_state
        return wallet_state

    def settle(self) -> dict[str, Any]:
        return self.client.run_settlement()
