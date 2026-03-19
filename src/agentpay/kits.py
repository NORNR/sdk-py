from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .adapters import create_openai_agents_tools
from .browser import BrowserCheckoutGuard
from .client import Wallet
from .langgraph import nornr_state_reducer, record_decision, state_business_context, state_context
from .mcp import create_mcp_server, create_mcp_tools
from .pydanticai import NornrDeps, create_pydanticai_tools


@dataclass(frozen=True)
class NornrKit:
    name: str
    summary: str
    recommended_policy_pack_id: str | None
    quickstart: str
    components: dict[str, Any] = field(default_factory=dict)
    scenarios: tuple[str, ...] = field(default_factory=tuple)

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "summary": self.summary,
            "recommendedPolicyPackId": self.recommended_policy_pack_id,
            "quickstart": self.quickstart,
            "scenarios": list(self.scenarios),
            "componentKeys": sorted(self.components.keys()),
        }


def create_openai_agents_kit(wallet: Wallet) -> NornrKit:
    return NornrKit(
        name="openai-agents",
        summary="Govern paid tool calls inside OpenAI Agents SDK flows without building custom approval tools first.",
        recommended_policy_pack_id="research-safe",
        quickstart="Use the generated OpenAI Agents tools, then route higher-spend cases into NORNR before the provider call fires.",
        components={
            "wallet": wallet,
            "tools": create_openai_agents_tools(wallet),
            "examples": ["openai_agents_sdk_wallet.py", "wrap_openai_client.py"],
        },
        scenarios=("research buyer", "incident copilot", "customer escalation"),
    )


def create_pydanticai_kit(wallet: Wallet, *, business_context: dict[str, Any] | None = None) -> NornrKit:
    deps = NornrDeps(wallet=wallet, default_business_context=dict(business_context or {}))
    return NornrKit(
        name="pydanticai",
        summary="Attach NORNR spend and approval tools directly to PydanticAI agents with shared business context.",
        recommended_policy_pack_id="research-safe",
        quickstart="Pass NornrDeps into the agent, add NORNR tools, and let the control layer decide before the model or tool spends.",
        components={
            "wallet": wallet,
            "deps": deps,
            "tools": create_pydanticai_tools(wallet, business_context=business_context),
            "examples": ["pydanticai_agent.py"],
        },
        scenarios=("research buyer", "support copilot"),
    )


def create_langgraph_kit(wallet: Wallet) -> NornrKit:
    return NornrKit(
        name="langgraph",
        summary="Treat NORNR decisions as first-class LangGraph state so approvals, payment-intent IDs and last decision survive the graph.",
        recommended_policy_pack_id="browser-ops-guarded",
        quickstart="Use state_context(...) before paid nodes and record_decision(...) after them so the graph stays replay- and approval-aware.",
        components={
            "wallet": wallet,
            "stateReducer": nornr_state_reducer,
            "recordDecision": record_decision,
            "stateBusinessContext": state_business_context,
            "stateContext": state_context,
            "examples": ["langgraph_state.py"],
        },
        scenarios=("browser ops", "tool orchestration", "operator review graph"),
    )


def create_browser_agent_kit(
    wallet: Wallet,
    *,
    allow_domains: list[str] | None = None,
    blocked_domains: list[str] | None = None,
) -> NornrKit:
    guard = BrowserCheckoutGuard(wallet, allow_domains=allow_domains, blocked_domains=blocked_domains)
    return NornrKit(
        name="browser-agent",
        summary="Guard browser checkout clicks, card-detail fills and other high-risk purchase actions before the page completes them.",
        recommended_policy_pack_id="browser-ops-guarded",
        quickstart="Wrap click/fill callbacks with the checkout guard so NORNR can review or block the purchase moment itself.",
        components={
            "wallet": wallet,
            "guard": guard,
            "examples": ["browser_checkout_guard.py"],
        },
        scenarios=("browser checkout", "procurement agent", "subscription upgrade"),
    )


def create_mcp_kit(
    wallet: Wallet,
    *,
    server_name: str = "nornr-mcp",
    command: str = "nornr",
) -> NornrKit:
    server = create_mcp_server(wallet, server_name=server_name)
    return NornrKit(
        name="mcp",
        summary="Expose NORNR as a local MCP server so Claude Desktop, Cursor or any MCP client gets a spend-control layer without custom code.",
        recommended_policy_pack_id="mcp-local-tools-guarded",
        quickstart="Run `nornr mcp serve`, drop the generated Claude Desktop config into your MCP client, then let local agents ask NORNR before paid actions.",
        components={
            "wallet": wallet,
            "server": server,
            "tools": create_mcp_tools(wallet),
            "manifest": server.build_manifest(),
            "claudeDesktopConfig": server.build_claude_desktop_config(command=command),
            "examples": ["mcp_server.py"],
        },
        scenarios=("local MCP tools", "Claude Desktop", "Cursor agent"),
    )


def create_framework_kits(wallet: Wallet) -> list[NornrKit]:
    return [
        create_openai_agents_kit(wallet),
        create_pydanticai_kit(wallet),
        create_langgraph_kit(wallet),
        create_browser_agent_kit(wallet),
        create_mcp_kit(wallet),
    ]
