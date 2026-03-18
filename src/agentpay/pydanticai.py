from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .adapters import _budget_tags, _payment_summary
from .client import AgentPayError, Wallet, _find_pending_approval


@dataclass
class NornrDeps:
    wallet: Wallet
    default_budget_tags: dict[str, str] = field(default_factory=dict)
    default_business_context: dict[str, Any] = field(default_factory=dict)


def _decorate_pydanticai_tool(tool_fn: Callable[..., str]) -> Callable[..., str]:
    try:
        from pydantic_ai.tools import tool_plain
    except ImportError:
        return tool_fn
    return tool_plain(tool_fn)


def create_pydanticai_tools(wallet: Wallet, *, business_context: dict[str, Any] | None = None) -> list[Callable[..., str]]:
    """Create PydanticAI-friendly tools for NORNR spend control."""

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
            business_context=business_context,
        )
        return _payment_summary(decision)

    def nornr_approve(payment_intent_id: str, comment: str | None = None) -> str:
        bootstrap = wallet.refresh()
        approval = _find_pending_approval(bootstrap, payment_intent_id)
        if not approval:
            raise AgentPayError("No pending approval found for payment intent")
        result = wallet.client.approve_intent(approval["id"], {"comment": comment} if comment else {})
        return str(result)

    return [
        _decorate_pydanticai_tool(nornr_spend),
        _decorate_pydanticai_tool(nornr_approve),
    ]
