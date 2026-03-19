from __future__ import annotations

import json
from typing import Any, Callable, Mapping, TypedDict, cast

from .client import AgentPayError, Wallet, _find_pending_approval


class AdapterBusinessContext(TypedDict, total=False):
    surface: str
    framework: str
    toolName: str | None
    workflow: str | None
    role: str | None
    tags: dict[str, str]


class AdapterReplayContext(TypedDict, total=False):
    source: str
    framework: str
    toolName: str
    workflow: str | None


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


def _json_summary(payload: Any) -> str:
    if hasattr(payload, "to_summary_dict"):
        return json.dumps(payload.to_summary_dict())
    if hasattr(payload, "to_dict"):
        return json.dumps(payload.to_dict())
    return json.dumps(payload)


def _budget_tags(team: str | None, project: str | None, customer: str | None, cost_center: str | None) -> dict[str, str] | None:
    tags = {
        "team": team,
        "project": project,
        "customer": customer,
        "costCenter": cost_center,
    }
    filtered = {key: value for key, value in tags.items() if value}
    return filtered or None


def adapter_business_context(
    *,
    surface: str,
    framework: str,
    tool_name: str | None = None,
    workflow: str | None = None,
    role: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> AdapterBusinessContext:
    payload: dict[str, Any] = {
        "surface": surface,
        "framework": framework,
        "toolName": tool_name,
        "workflow": workflow,
        "role": role,
        "tags": {
            "framework": framework,
        },
    }
    if extra:
        payload.update(dict(extra))
    return cast(AdapterBusinessContext, payload)


def adapter_replay_context(
    *,
    framework: str,
    tool_name: str,
    workflow: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> AdapterReplayContext:
    payload: dict[str, Any] = {
        "source": f"{framework}.tool.{tool_name}",
        "framework": framework,
        "toolName": tool_name,
        "workflow": workflow,
    }
    if extra:
        payload.update(dict(extra))
    return cast(AdapterReplayContext, payload)


def _merge_business_context(*contexts: Mapping[str, Any] | None) -> dict[str, Any] | None:
    merged: dict[str, Any] = {}
    for context in contexts:
        if context:
            merged.update(dict(context))
    return merged or None


def _decorate_openai_tool(tool_fn: Callable[..., str]) -> Callable[..., str]:
    try:
        from agents import function_tool
    except ImportError:
        return tool_fn

    return cast(Callable[..., str], function_tool(tool_fn))


def _decorate_langchain_tool(tool_fn: Callable[..., str], *, name: str) -> Any:
    try:
        from langchain.tools import tool
    except ImportError:
        try:
            from langchain_core.tools import tool
        except ImportError:
            return tool_fn

    return tool(name)(tool_fn)


def _governed_tool_payloads(
    wallet: Wallet,
    *,
    framework: str,
    surface: str,
    default_business_context: Mapping[str, Any] | None = None,
) -> dict[str, Callable[..., str]]:
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
        decision = wallet.pay(
            amount=amount_usd,
            to=destination or counterparty,
            counterparty=counterparty,
            purpose=purpose,
            budget_tags=_budget_tags(team, project, customer, cost_center),
            business_context=_merge_business_context(
                adapter_business_context(
                    surface=surface,
                    framework=framework,
                    tool_name="nornr_spend",
                    workflow="governed-spend",
                ),
                default_business_context,
            ),
            replay_context=cast(
                dict[str, Any],
                adapter_replay_context(
                framework=framework,
                tool_name="spend",
                workflow="governed-spend",
                ),
            ),
        )
        return _payment_summary(decision)

    def nornr_approve(payment_intent_id: str, comment: str | None = None) -> str:
        bootstrap = wallet.refresh()
        approval = _find_pending_approval(bootstrap, payment_intent_id)
        if not approval:
            raise AgentPayError("No pending approval found for payment intent")
        result = wallet.client.approve_intent(approval["id"], {"comment": comment} if comment else {})
        return json.dumps(result)

    def nornr_balance() -> str:
        return _json_summary(wallet.balance())

    def nornr_pending_approvals() -> str:
        return json.dumps([approval.to_dict() for approval in wallet.pending_approvals()])

    def nornr_finance_packet() -> str:
        return _json_summary(wallet.finance_packet())

    def nornr_weekly_review() -> str:
        return _json_summary(wallet.weekly_review())

    def nornr_anomaly_inbox() -> str:
        return json.dumps([record.to_dict() for record in wallet.client.list_anomalies()])

    def nornr_review_bundle() -> str:
        return json.dumps(
            {
                "timeline": wallet.timeline().to_dict(),
                "financePacket": wallet.finance_packet().to_dict(),
                "pendingApprovals": [approval.to_dict() for approval in wallet.pending_approvals()],
                "anomalies": [record.to_dict() for record in wallet.client.list_anomalies()],
                "controlRoomUrl": f"{wallet.client.base_url.rstrip('/')}/app",
            }
        )

    return {
        "nornr_spend": nornr_spend,
        "nornr_approve": nornr_approve,
        "nornr_balance": nornr_balance,
        "nornr_pending_approvals": nornr_pending_approvals,
        "nornr_finance_packet": nornr_finance_packet,
        "nornr_weekly_review": nornr_weekly_review,
        "nornr_anomaly_inbox": nornr_anomaly_inbox,
        "nornr_review_bundle": nornr_review_bundle,
    }


def create_openai_agents_tools(
    wallet: Wallet,
    *,
    business_context: Mapping[str, Any] | None = None,
) -> list[Callable[..., str]]:
    """Create OpenAI Agents SDK-compatible function tools for NORNR."""

    handlers = _governed_tool_payloads(
        wallet,
        framework="openai-agents",
        surface="agent-tool",
        default_business_context=business_context,
    )
    return [_decorate_openai_tool(handler) for handler in handlers.values()]


def create_langchain_tools(
    wallet: Wallet,
    *,
    business_context: Mapping[str, Any] | None = None,
) -> list[Any]:
    """Create LangChain-compatible tools for NORNR."""

    handlers = _governed_tool_payloads(
        wallet,
        framework="langchain",
        surface="agent-tool",
        default_business_context=business_context,
    )
    return [
        _decorate_langchain_tool(handler, name=name)
        for name, handler in handlers.items()
    ]
