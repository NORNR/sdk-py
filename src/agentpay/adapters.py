from __future__ import annotations

import json
from typing import Any, Callable

from .client import AgentPayError, Wallet, _find_pending_approval


def _payment_summary(payload: Any) -> str:
    if hasattr(payload, "to_summary_dict"):
        return json.dumps(payload.to_summary_dict())
    payment_intent = payload.get("paymentIntent") or {}
    approval = payload.get("approval") or {}
    return json.dumps(
        {
            "paymentIntentId": payment_intent.get("id"),
            "status": payment_intent.get("status"),
            "requiresApproval": payload.get("requiresApproval", False),
            "approvalId": approval.get("id"),
        }
    )


def _budget_tags(team: str | None, project: str | None, customer: str | None, cost_center: str | None) -> dict[str, str] | None:
    tags = {
        "team": team,
        "project": project,
        "customer": customer,
        "costCenter": cost_center,
    }
    filtered = {key: value for key, value in tags.items() if value}
    return filtered or None


def _decorate_openai_tool(tool_fn: Callable[..., str]) -> Callable[..., str]:
    try:
        from agents import function_tool
    except ImportError:
        return tool_fn

    return function_tool(tool_fn)


def _decorate_langchain_tool(tool_fn: Callable[..., str], *, name: str) -> Any:
    try:
        from langchain.tools import tool
    except ImportError:
        try:
            from langchain_core.tools import tool
        except ImportError:
            return tool_fn

    return tool(name)(tool_fn)


def create_openai_agents_tools(wallet: Wallet) -> list[Callable[..., str]]:
    """Create OpenAI Agents SDK-compatible function tools for NORNR."""

    def nornr_spend(
        amount_usd: float,
        counterparty: str,
        purpose: str,
        destination: str | None = None,
        team: str | None = None,
        project: str | None = None,
        customer: str | None = None,
        cost_center: str | None = None,
    ) -> str:
        """Queue or approve spend in NORNR before a downstream action moves money."""

        decision = wallet.pay(
            amount=amount_usd,
            to=destination or counterparty,
            counterparty=counterparty,
            purpose=purpose,
            budget_tags=_budget_tags(team, project, customer, cost_center),
        )
        return _payment_summary(decision)

    def nornr_approve(payment_intent_id: str, comment: str | None = None) -> str:
        """Approve a queued NORNR spend decision after human review."""

        bootstrap = wallet.refresh()
        approval = _find_pending_approval(bootstrap, payment_intent_id)
        if not approval:
            raise AgentPayError("No pending approval found for payment intent")
        result = wallet.client.approve_intent(approval["id"], {"comment": comment} if comment else {})
        return json.dumps(result)

    def nornr_balance() -> str:
        """Return the current NORNR wallet balance for this agent workspace."""

        return json.dumps(wallet.balance())

    return [
        _decorate_openai_tool(nornr_spend),
        _decorate_openai_tool(nornr_approve),
        _decorate_openai_tool(nornr_balance),
    ]


def create_langchain_tools(wallet: Wallet) -> list[Any]:
    """Create LangChain-compatible tools for NORNR."""

    def nornr_spend(
        amount_usd: float,
        counterparty: str,
        purpose: str,
        destination: str | None = None,
        team: str | None = None,
        project: str | None = None,
        customer: str | None = None,
        cost_center: str | None = None,
    ) -> str:
        """Queue or approve spend in NORNR before a downstream action moves money."""

        decision = wallet.pay(
            amount=amount_usd,
            to=destination or counterparty,
            counterparty=counterparty,
            purpose=purpose,
            budget_tags=_budget_tags(team, project, customer, cost_center),
        )
        return _payment_summary(decision)

    def nornr_approve(payment_intent_id: str, comment: str | None = None) -> str:
        """Approve a queued NORNR spend decision after human review."""

        bootstrap = wallet.refresh()
        approval = _find_pending_approval(bootstrap, payment_intent_id)
        if not approval:
            raise AgentPayError("No pending approval found for payment intent")
        result = wallet.client.approve_intent(approval["id"], {"comment": comment} if comment else {})
        return json.dumps(result)

    def nornr_balance() -> str:
        """Return the current NORNR wallet balance for this agent workspace."""

        return json.dumps(wallet.balance())

    return [
        _decorate_langchain_tool(nornr_spend, name="nornr_spend"),
        _decorate_langchain_tool(nornr_approve, name="nornr_approve"),
        _decorate_langchain_tool(nornr_balance, name="nornr_balance"),
    ]
