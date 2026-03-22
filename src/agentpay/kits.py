from __future__ import annotations

from dataclasses import dataclass, field
import importlib.util
from typing import Any

from .adapters import create_openai_agents_tools
from .browser import BrowserCheckoutGuard
from .client import Wallet
from .langgraph import nornr_state_reducer, record_decision, state_business_context, state_context
from .mcp import create_mcp_server, create_mcp_tools
from .pydanticai import NornrDeps, create_pydanticai_tools
from .templates import scenario_templates
from .wrappers import create_spend_aware_openai_client


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

    @property
    def wallet(self) -> Wallet | None:
        wallet = self.components.get("wallet")
        return wallet if isinstance(wallet, Wallet) else None

    def validate_environment(self) -> dict[str, Any]:
        dependency_map = {
            "openai-agents": ("agents",),
            "pydanticai": ("pydantic_ai",),
            "langgraph": ("langgraph",),
            "browser-agent": ("playwright",),
            "mcp": (),
        }
        modules = dependency_map.get(self.name, ())
        missing = [module for module in modules if importlib.util.find_spec(module) is None]
        return {
            "kit": self.name,
            "ok": not missing,
            "missingModules": missing,
            "recommendedPolicyPackId": self.recommended_policy_pack_id,
            "firstRunChecklist": self.first_run_checklist(),
        }

    def bootstrap(self, *, mode: str = "shadow") -> dict[str, Any]:
        if not self.wallet:
            raise RuntimeError("Kit is missing wallet component")
        if not self.recommended_policy_pack_id:
            return {
                "kit": self.name,
                "mode": mode,
                "status": "skipped",
                "reason": "Kit has no recommended policy pack.",
                "firstRunChecklist": self.first_run_checklist(),
            }
        if mode == "shadow":
            replay = self.wallet.replay_policy_pack(self.recommended_policy_pack_id, mode=mode)
            return {
                "kit": self.name,
                "mode": mode,
                "status": "replayed",
                "packId": self.recommended_policy_pack_id,
                "summary": replay.to_dict(),
                "firstRunChecklist": self.first_run_checklist(),
            }
        applied = self.wallet.apply_policy_pack(self.recommended_policy_pack_id, mode=mode)
        return {
            "kit": self.name,
            "mode": mode,
            "status": "applied",
            "packId": self.recommended_policy_pack_id,
            "summary": applied.to_dict(),
            "firstRunChecklist": self.first_run_checklist(),
        }

    def first_run_checklist(self) -> list[str]:
        steps = [
            f"Install dependencies for the `{self.name}` surface.",
            "Connect a NORNR wallet with least-privilege scopes.",
        ]
        if self.recommended_policy_pack_id:
            steps.append(f"Replay the recommended policy pack `{self.recommended_policy_pack_id}` in shadow mode first.")
        steps.append("Run one governed action and verify the returned decision basis, review path and audit export.")
        return steps

    def scaffold_config(self) -> dict[str, Any]:
        normalized_scenarios = [item.lower().replace(" ", "-") for item in self.scenarios]
        return {
            "kit": self.name,
            "recommendedPolicyPackId": self.recommended_policy_pack_id,
            "scenarios": list(self.scenarios),
            "templates": [item.to_dict() for item in scenario_templates() if any(term in item.name for term in normalized_scenarios)][:2],
        }


def create_openai_agents_kit(wallet: Wallet) -> NornrKit:
    return NornrKit(
        name="openai-agents",
        summary="Govern one consequential tool lane inside OpenAI Agents SDK flows without building custom approval tools first.",
        recommended_policy_pack_id="research-safe",
        quickstart="Use the generated OpenAI Agents tools, then let NORNR return one clear decision basis before the consequential provider call fires.",
        components={
            "wallet": wallet,
            "tools": create_openai_agents_tools(wallet),
            "examples": ["openai_agents_sdk_wallet.py", "wrap_openai_client.py"],
        },
        scenarios=("research buyer", "incident copilot", "customer escalation"),
    )


def create_provider_wrapper_kit(wallet: Wallet) -> NornrKit:
    return NornrKit(
        name="provider-wrapper",
        summary="Wrap one existing provider client with a thin NORNR spend-aware ingress before you widen into runtime, MCP or browser governance.",
        recommended_policy_pack_id="research-safe",
        quickstart="Use one spend-aware wrapper for the first provider lane, then upgrade the consequential path into a governed runtime or MCP lane once the team wants review, proof and finance-safe exports on the same path.",
        components={
            "wallet": wallet,
            "openaiFactory": create_spend_aware_openai_client,
            "examples": ["21_spend_aware_wrapper.py", "wrap_openai_client.py"],
        },
        scenarios=("existing provider client", "openai wrapper", "cost ingress"),
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
        summary="Treat NORNR decisions as first-class LangGraph state so one approval branch, payment-intent IDs and the last decision basis survive the graph.",
        recommended_policy_pack_id="browser-ops-guarded",
        quickstart="Use state_context(...) before consequential nodes and record_decision(...) after them so the graph stays replay-, review- and reason-aware.",
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
        summary="Expose NORNR as the default MCP control server so Claude Desktop, Cursor or another local agent gets one decision basis, queued review and finance-safe exports without a bespoke wrapper.",
        recommended_policy_pack_id="mcp-local-tools-guarded",
        quickstart="Run `nornr mcp serve`, drop the generated config into Claude Desktop, Cursor or another MCP client, start from `mcp-local-tools-guarded`, then let local agents ask NORNR for one clear decision basis before consequential tool use.",
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
        create_provider_wrapper_kit(wallet),
        create_openai_agents_kit(wallet),
        create_pydanticai_kit(wallet),
        create_langgraph_kit(wallet),
        create_browser_agent_kit(wallet),
        create_mcp_kit(wallet),
    ]
