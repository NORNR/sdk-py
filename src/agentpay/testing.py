from __future__ import annotations

import json
import inspect
from dataclasses import dataclass, field
from typing import Any, Mapping, cast
from urllib.parse import urlparse

from .browser import BrowserGuardResult, CheckoutSignal
from .client import AgentPayClient, AsyncAgentPayClient, DEFAULT_BASE_URL, Wallet
from .transport import AsyncHttpTransport, SyncHttpTransport
from .models import AuditReviewRecord, BalanceRecord, DecisionRecord


def mock_decision(
    status: str = "approved",
    *,
    approval_id: str = "approval_mock",
    payment_intent_id: str = "pi_mock",
    amount_usd: float = 5.0,
    counterparty: str = "openai",
    purpose: str = "mocked call",
) -> DecisionRecord:
    payload = {
        "paymentIntent": {
            "id": payment_intent_id,
            "status": status,
            "amountUsd": amount_usd,
            "counterparty": counterparty,
            "purpose": purpose,
        },
        "requiresApproval": status == "queued",
    }
    if status == "queued":
        payload["approval"] = {
            "id": approval_id,
            "status": "pending",
            "paymentIntentId": payment_intent_id,
            "approvalUrl": f"https://nornr.com/app/approvals/{approval_id}",
        }
    return DecisionRecord.from_payload(payload)


def mock_bootstrap(
    *,
    workspace_id: str = "ws_mock",
    agent_id: str = "agent_mock",
    api_key: str = "nornr_test_key",
) -> dict[str, Any]:
    return {
        "workspace": {"id": workspace_id, "label": "Mock workspace"},
        "agents": [{"id": agent_id, "label": "Mock agent"}],
        "wallet": {
            "balanceSummary": {
                "availableUsd": 100,
                "reservedUsd": 0,
                "pendingSettlementUsd": 0,
                "totalFeesUsd": 0,
            }
        },
        "apiKey": {"key": api_key},
        "approvals": [],
    }


def mock_browser_result(
    status: str = "queued",
    *,
    url: str = "https://stripe.com/checkout/session",
    action: str = "click",
    amount_usd: float = 25.0,
    currency: str = "USD",
    merchant_label: str = "Stripe Checkout",
) -> BrowserGuardResult:
    signal = CheckoutSignal(
        url=url,
        action=action,
        reason="Mocked checkout signal",
        domain=urlparse(url).hostname or "stripe.com",
        counterparty="stripe",
        path=urlparse(url).path or "/",
        amount_usd=amount_usd,
        currency=currency,
        merchant_label=merchant_label,
        matched_terms=("checkout",),
    )
    return BrowserGuardResult(signal=signal, decision=mock_decision(status=status, counterparty="stripe", amount_usd=amount_usd))


def _json_payload(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    return json.dumps(payload)


@dataclass
class MockTransport:
    routes: Mapping[Any, Any]
    requests: list[dict[str, Any]] = field(default_factory=list)
    closed: bool = False

    def request(
        self,
        *,
        url: str,
        method: str = "GET",
        headers: Mapping[str, str] | None = None,
        body: Any = None,
    ) -> tuple[int, str]:
        normalized_method = method.upper()
        pathname = urlparse(url).path or "/"
        request_payload = {
            "url": url,
            "pathname": pathname,
            "method": normalized_method,
            "headers": dict(headers or {}),
            "body": body,
        }
        self.requests.append(request_payload)
        handler = self.routes.get((normalized_method, pathname))
        if handler is None:
            handler = self.routes.get(pathname)
        if handler is None:
            raise AssertionError(f"No mock route for {normalized_method} {pathname}")
        if callable(handler):
            response = handler(request_payload)
        else:
            response = handler
        if isinstance(response, tuple) and len(response) == 2:
            status_code, payload = response
        else:
            status_code, payload = 200, response
        return int(status_code), _json_payload(payload)

    def close(self) -> None:
        self.closed = True


@dataclass
class AsyncMockTransport:
    routes: Mapping[Any, Any]
    requests: list[dict[str, Any]] = field(default_factory=list)
    closed: bool = False

    async def request(
        self,
        *,
        url: str,
        method: str = "GET",
        headers: Mapping[str, str] | None = None,
        body: Any = None,
    ) -> tuple[int, str]:
        normalized_method = method.upper()
        pathname = urlparse(url).path or "/"
        request_payload = {
            "url": url,
            "pathname": pathname,
            "method": normalized_method,
            "headers": dict(headers or {}),
            "body": body,
        }
        self.requests.append(request_payload)
        handler = self.routes.get((normalized_method, pathname))
        if handler is None:
            handler = self.routes.get(pathname)
        if handler is None:
            raise AssertionError(f"No async mock route for {normalized_method} {pathname}")
        if callable(handler):
            response = handler(request_payload)
            if inspect.isawaitable(response):
                response = await response
        else:
            response = handler
        if isinstance(response, tuple) and len(response) == 2:
            status_code, payload = response
        else:
            status_code, payload = 200, response
        return int(status_code), _json_payload(payload)

    async def close(self) -> None:
        self.closed = True


def build_mock_client(
    routes: Mapping[Any, Any],
    *,
    api_key: str = "nornr_test_key",
    base_url: str = DEFAULT_BASE_URL,
) -> AgentPayClient:
    return AgentPayClient(base_url=base_url, api_key=api_key, transport=cast(SyncHttpTransport, MockTransport(routes)))


def build_mock_async_client(
    routes: Mapping[Any, Any],
    *,
    api_key: str = "nornr_test_key",
    base_url: str = DEFAULT_BASE_URL,
) -> AsyncAgentPayClient:
    return AsyncAgentPayClient(
        base_url=base_url,
        api_key=api_key,
        transport=cast(AsyncHttpTransport, AsyncMockTransport(routes)),
    )


def build_mock_wallet(
    routes: Mapping[Any, Any] | None = None,
    *,
    api_key: str = "nornr_test_key",
    base_url: str = DEFAULT_BASE_URL,
    bootstrap: Mapping[str, Any] | None = None,
) -> Wallet:
    bootstrap_payload = dict(bootstrap or mock_bootstrap(api_key=api_key))
    client_routes = {"/api/bootstrap": bootstrap_payload, **dict(routes or {})}
    client = build_mock_client(client_routes, api_key=api_key, base_url=base_url)
    return Wallet(
        client=client,
        workspace=dict(bootstrap_payload["workspace"]),
        agent=dict(bootstrap_payload["agents"][0]),
        wallet=dict(bootstrap_payload.get("wallet") or {}),
        api_key=dict(bootstrap_payload.get("apiKey") or {"key": api_key}),
    )


@dataclass
class MockWallet:
    status: str = "approved"

    def pay(self, *args: Any, **kwargs: Any) -> DecisionRecord:
        return mock_decision(self.status)

    def balance(self) -> BalanceRecord:
        return BalanceRecord.from_payload(
            {"balanceSummary": {"availableUsd": 100, "reservedUsd": 0, "pendingSettlementUsd": 0, "totalFeesUsd": 0}}
        )

    def audit_review(self) -> AuditReviewRecord:
        return AuditReviewRecord.from_payload(
            {"financePacket": {"score": 100, "openActions": [], "packetHistory": [], "lastHandoff": None}}
        )
