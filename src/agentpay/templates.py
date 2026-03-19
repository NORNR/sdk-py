from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .scopes import recommended_scopes


@dataclass(frozen=True)
class ScenarioTemplate:
    name: str
    summary: str
    recommended_policy_pack_id: str | None
    required_scopes: tuple[str, ...]
    example: dict[str, Any]
    first_run_checklist: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "summary": self.summary,
            "recommendedPolicyPackId": self.recommended_policy_pack_id,
            "requiredScopes": list(self.required_scopes),
            "example": dict(self.example),
            "firstRunChecklist": list(self.first_run_checklist),
        }


def browser_checkout_template() -> ScenarioTemplate:
    return ScenarioTemplate(
        name="browser-checkout-governance",
        summary="Pause checkout-like browser actions before the click commits money.",
        recommended_policy_pack_id="browser-ops-guarded",
        required_scopes=recommended_scopes("browser-guard").scopes,
        example={"url": "https://stripe.com/checkout", "action": "click", "amount": 25, "counterparty": "stripe"},
        first_run_checklist=(
            "Set blocked or reviewed domains.",
            "Capture screenshot and DOM evidence.",
            "Run preflight before the click executes.",
        ),
    )


def paid_tool_call_template() -> ScenarioTemplate:
    return ScenarioTemplate(
        name="paid-api-tool-governance",
        summary="Put policy and approvals in front of a paid API or tool call.",
        recommended_policy_pack_id="research-safe",
        required_scopes=recommended_scopes("read-only").scopes + ("payments:write",),
        example={"actionName": "paid-tool-call", "counterparty": "openai", "amount": 8, "purpose": "Run governed inference"},
        first_run_checklist=(
            "Define the paid tool purpose and counterparty.",
            "Use execute_governed for the canonical lifecycle.",
            "Attach receipt evidence after success.",
        ),
    )


def mcp_local_tool_template() -> ScenarioTemplate:
    return ScenarioTemplate(
        name="mcp-local-tool-governance",
        summary="Expose NORNR to local agent runtimes through MCP with approval and finance visibility.",
        recommended_policy_pack_id="mcp-local-tools-guarded",
        required_scopes=recommended_scopes("mcp").scopes,
        example={"tool": "nornr.request_spend", "amount": 5, "counterparty": "openai"},
        first_run_checklist=(
            "Print the Claude Desktop config.",
            "Verify the approval queue is reachable.",
            "Read finance-close and anomaly resources from MCP.",
        ),
    )


def finance_close_template() -> ScenarioTemplate:
    return ScenarioTemplate(
        name="finance-close-workflow",
        summary="Bundle weekly review, audit export, and monthly statement into a finance-close flow.",
        recommended_policy_pack_id=None,
        required_scopes=recommended_scopes("finance-close").scopes,
        example={"workflow": "monthly-close", "format": "json"},
        first_run_checklist=(
            "Generate the finance packet.",
            "Export the audit bundle.",
            "Verify statement month and close-ready artifacts.",
        ),
    )


def delegated_sub_agent_budget_template() -> ScenarioTemplate:
    return ScenarioTemplate(
        name="delegated-sub-agent-budget",
        summary="Delegate a bounded mandate from a parent agent to a sub-agent and keep the trail attached.",
        recommended_policy_pack_id=None,
        required_scopes=recommended_scopes("worker").scopes + ("payments:write",),
        example={"targetAgentId": "agent_child", "dailyLimitUsd": 5, "counterparty": "openai"},
        first_run_checklist=(
            "Create the delegated mandate.",
            "Apply the budget cap if the child agent is long-lived.",
            "Attach the delegation metadata to every child action.",
        ),
    )


def scenario_templates() -> list[ScenarioTemplate]:
    return [
        browser_checkout_template(),
        paid_tool_call_template(),
        mcp_local_tool_template(),
        finance_close_template(),
        delegated_sub_agent_budget_template(),
    ]
