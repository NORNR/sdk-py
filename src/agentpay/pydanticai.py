from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, cast

from .adapters import _governed_tool_payloads, adapter_business_context
from .client import Wallet


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
    return cast(Callable[..., str], tool_plain(tool_fn))


def pydanticai_business_context(
    *,
    agent_name: str | None = None,
    model_name: str | None = None,
    workflow: str = "governed-agent-tools",
    business_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        **adapter_business_context(
            surface="agent-tool",
            framework="pydanticai",
            workflow=workflow,
            extra={
                "agentName": agent_name,
                "modelName": model_name,
            },
        ),
        **dict(business_context or {}),
    }


def create_pydanticai_tools(
    wallet: Wallet,
    *,
    agent_name: str | None = None,
    model_name: str | None = None,
    business_context: dict[str, Any] | None = None,
) -> list[Callable[..., str]]:
    """Create PydanticAI-friendly tools for NORNR spend control."""
    handlers = _governed_tool_payloads(
        wallet,
        framework="pydanticai",
        surface="agent-tool",
        default_business_context=pydanticai_business_context(
            agent_name=agent_name,
            model_name=model_name,
            business_context=business_context,
        ),
    )
    return [_decorate_pydanticai_tool(handler) for handler in handlers.values()]


def create_pydanticai_tools_for(deps: NornrDeps, *, agent_name: str | None = None, model_name: str | None = None) -> list[Callable[..., str]]:
    return create_pydanticai_tools(
        deps.wallet,
        agent_name=agent_name,
        model_name=model_name,
        business_context=deps.default_business_context,
    )
