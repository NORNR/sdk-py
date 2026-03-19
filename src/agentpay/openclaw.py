from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .client import AgentPayError, DecisionRecord, Wallet, _find_pending_approval
from .workflows import run_monthly_close

DEFAULT_SKILL_NAME = "nornr-governance"


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _finance_ready(decision: DecisionRecord) -> bool:
    approval = decision.approval
    if decision.status == "approved":
        return True
    return bool(approval and approval.status in {"pending", "approved"})


def _control_room_url(decision: DecisionRecord) -> str | None:
    return decision.approval_url


def _prompt_risk(context: Mapping[str, Any] | None) -> str | None:
    if not context:
        return None
    excerpt = str(context.get("promptExcerpt") or context.get("prompt_excerpt") or "").lower()
    if not excerpt:
        return None
    risky_markers = (
        "ignore previous",
        "wire money",
        "buy now",
        "pay immediately",
        "use the card",
        "urgent purchase",
        "override policy",
    )
    for marker in risky_markers:
        if marker in excerpt:
            return f"Prompt excerpt contains risky instruction marker: {marker}"
    return None


def _context_payload(action: str, context: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = dict(context or {})
    return {
        "surface": "openclaw",
        "action": action,
        "skillName": raw.get("skillName") or raw.get("skill_name"),
        "runMode": raw.get("runMode") or raw.get("run_mode"),
        "runId": raw.get("runId") or raw.get("run_id"),
        "traceId": raw.get("traceId") or raw.get("trace_id"),
        "promptExcerpt": raw.get("promptExcerpt") or raw.get("prompt_excerpt"),
        "autonomous": bool(raw.get("autonomous", True)),
        **raw,
    }


def _matched_anomalies(wallet: Wallet, *, counterparty: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for anomaly in wallet.client.list_anomalies():
        payload = anomaly.to_dict()
        if anomaly.counterparty and anomaly.counterparty != counterparty:
            continue
        matches.append(
            {
                "id": anomaly.id,
                "status": anomaly.status,
                "severity": anomaly.severity,
                "reason": anomaly.reason,
                "counterparty": anomaly.counterparty,
                "amountUsd": anomaly.amount_usd,
                "raw": payload,
            }
        )
    return matches


@dataclass(frozen=True)
class OpenClawGovernanceResult:
    action: str
    purpose: str
    counterparty: str
    amount_usd: float
    governance_posture: str
    operator_next_move: str
    finance_ready: bool
    policy_decision: str
    approval_required: bool
    control_room_url: str | None
    openclaw_context: dict[str, Any]
    anomaly_signals: list[dict[str, Any]]
    evidence: dict[str, Any]
    decision: DecisionRecord

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "purpose": self.purpose,
            "counterparty": self.counterparty,
            "amountUsd": self.amount_usd,
            "governancePosture": self.governance_posture,
            "policyDecision": self.policy_decision,
            "approvalRequired": self.approval_required,
            "operatorNextMove": self.operator_next_move,
            "controlRoomUrl": self.control_room_url,
            "financeReadyAuditTrail": self.finance_ready,
            "openclawRun": self.openclaw_context,
            "anomalySignals": self.anomaly_signals,
            "evidence": self.evidence,
            "decision": self.decision.to_summary_dict(),
        }


class OpenClawGovernanceAdapter:
    """Put NORNR in front of paid or risky OpenClaw skill actions."""

    def __init__(self, wallet: Wallet) -> None:
        self.wallet = wallet

    def preflight_paid_action(
        self,
        *,
        action: str,
        amount_usd: float,
        counterparty: str,
        purpose: str,
        destination: str | None = None,
        budget_tags: Mapping[str, str] | None = None,
        context: Mapping[str, Any] | None = None,
        dry_run: bool = False,
    ) -> OpenClawGovernanceResult:
        openclaw_context = _context_payload(action, context)
        prompt_risk = _prompt_risk(openclaw_context)
        decision = self.wallet.pay(
            amount=amount_usd,
            to=destination or counterparty,
            counterparty=counterparty,
            purpose=purpose,
            budget_tags=dict(budget_tags or {}),
            dry_run=dry_run,
            business_context=openclaw_context,
            replay_context={
                "source": "openclaw.skill",
                "action": action,
            },
        )
        anomaly_signals = _matched_anomalies(self.wallet, counterparty=counterparty)
        if prompt_risk:
            anomaly_signals.insert(
                0,
                {
                    "id": "prompt-risk",
                    "status": "watch",
                    "severity": "high",
                    "reason": prompt_risk,
                    "counterparty": counterparty,
                    "amountUsd": amount_usd,
                    "raw": {"source": "openclaw.prompt_excerpt"},
                },
            )
        if decision.status == "approved":
            posture = "approved"
            next_move = "Action may proceed because NORNR cleared the intent before execution."
        elif decision.requires_approval:
            posture = "approval_required"
            next_move = "Pause the autonomous action and route it to operator approval before execution."
        else:
            posture = "blocked"
            next_move = "Do not proceed until the policy decision changes or the intent is rewritten."
        return OpenClawGovernanceResult(
            action=action,
            purpose=purpose,
            counterparty=counterparty,
            amount_usd=float(amount_usd),
            governance_posture=posture,
            operator_next_move=next_move,
            finance_ready=_finance_ready(decision),
            policy_decision=decision.status,
            approval_required=decision.requires_approval,
            control_room_url=_control_room_url(decision),
            openclaw_context={
                "skillName": openclaw_context.get("skillName"),
                "runMode": openclaw_context.get("runMode"),
                "runId": openclaw_context.get("runId"),
                "traceId": openclaw_context.get("traceId"),
                "autonomous": openclaw_context.get("autonomous"),
            },
            anomaly_signals=anomaly_signals,
            evidence={
                "receiptTrail": "NORNR keeps the decision, approval state, and finance trail attached to the same record.",
                "auditExportReady": _finance_ready(decision),
                "promptRiskObserved": bool(prompt_risk),
            },
            decision=decision,
        )

    def pending_approvals(self) -> list[dict[str, Any]]:
        return [approval.to_dict() for approval in self.wallet.pending_approvals()]

    def approve(self, payment_intent_id: str, *, comment: str | None = None) -> dict[str, Any]:
        bootstrap = self.wallet.refresh()
        approval = _find_pending_approval(bootstrap, payment_intent_id)
        if not approval:
            raise AgentPayError(f"No pending approval found for payment intent {payment_intent_id}")
        result = self.wallet.client.approve_intent(approval["id"], {"comment": comment} if comment else {})
        return dict(result or {})

    def reject(self, payment_intent_id: str, *, comment: str | None = None) -> dict[str, Any]:
        bootstrap = self.wallet.refresh()
        approval = _find_pending_approval(bootstrap, payment_intent_id)
        if not approval:
            raise AgentPayError(f"No pending approval found for payment intent {payment_intent_id}")
        result = self.wallet.client.reject_intent(approval["id"], {"comment": comment} if comment else {})
        return dict(result or {})

    def finance_packet(self) -> dict[str, Any]:
        return self.wallet.finance_packet().to_dict()

    def weekly_review(self) -> dict[str, Any]:
        return self.wallet.weekly_review().to_dict()

    def intent_timeline(self) -> dict[str, Any]:
        return self.wallet.timeline().to_dict()

    def anomalies(self, *, counterparty: str | None = None) -> list[dict[str, Any]]:
        items = _matched_anomalies(self.wallet, counterparty=counterparty or "")
        if counterparty:
            return items
        return [
            {
                "id": anomaly.id,
                "status": anomaly.status,
                "severity": anomaly.severity,
                "reason": anomaly.reason,
                "counterparty": anomaly.counterparty,
                "amountUsd": anomaly.amount_usd,
                "raw": anomaly.to_dict(),
            }
            for anomaly in self.wallet.client.list_anomalies()
        ]

    def audit_export(self) -> dict[str, Any]:
        return self.wallet.client.export_audit().to_dict()

    def monthly_close(
        self,
        *,
        provider: str = "quickbooks",
        month: str | None = None,
        workspace_label: str | None = None,
    ) -> dict[str, Any]:
        report = run_monthly_close(
            self.wallet,
            month=month,
            provider=provider,
            workspace_label=workspace_label or str(self.wallet.workspace.get("label") or "NORNR workspace"),
        )
        return report.to_summary_dict()

    def review_bundle(self, *, counterparty: str | None = None) -> dict[str, Any]:
        return {
            "pendingApprovals": self.pending_approvals(),
            "anomalies": self.anomalies(counterparty=counterparty),
            "intentTimeline": self.intent_timeline(),
            "financePacket": self.finance_packet(),
            "weeklyReview": self.weekly_review(),
        }


def create_openclaw_adapter(wallet: Wallet) -> OpenClawGovernanceAdapter:
    return OpenClawGovernanceAdapter(wallet)


def render_openclaw_skill_markdown(
    *,
    skill_name: str = DEFAULT_SKILL_NAME,
    script_name: str = "nornr_governance.py",
) -> str:
    return f"""---
name: {skill_name}
description: Put policy before paid actions, require approval for risky autonomous actions, and keep a finance-ready audit trail.
---

# {skill_name}

## What this skill is for

Use NORNR as the control layer before an OpenClaw skill triggers a paid action, risky autonomous action, or any downstream step that should leave behind a finance-ready audit trail.

## When to use it

- Before a skill triggers a purchase, subscription, or vendor-side paid action
- When an autonomous flow should pause for operator approval before execution
- When finance or operations need one defensible decision record after the action completes
- When prompt-injected or unusual autonomous spend should surface as reviewable posture instead of silent execution

## Installation

- `python -m pip install -r requirements.txt`

## Required environment

- `NORNR_API_KEY`
- `NORNR_BASE_URL` (optional, defaults to `https://nornr.com`)
- `NORNR_AGENT_ID` or a stored NORNR login profile

## Recommended API key scope

Minimum action scope for the full skill surface:

- `payments:write`
- `workspace:read`
- `approvals:write`
- `events:read`
- `audit:read`

Add these if you want the finance-close paths too:

- `reports:read`
- `webhooks:read`

## Dependency provenance

This skill delegates governance decisions to the official NORNR Python SDK, `agentpay`.

- Install source: `requirements.txt`
- Pinned SDK source: `https://github.com/NORNR/sdk-py/tree/bbe8bfc`
- Local bridge: `{script_name}`

## Commands

- `python {script_name} preflight --action purchase --amount-usd 25 --counterparty openai --purpose "Run the paid research action"`
- `python {script_name} approvals`
- `python {script_name} approve --payment-intent-id pi_123 --comment "Approved after review"`
- `python {script_name} reject --payment-intent-id pi_123 --comment "Rejected pending review"`
- `python {script_name} anomalies --counterparty openai`
- `python {script_name} timeline`
- `python {script_name} finance-packet`
- `python {script_name} audit-export`
- `python {script_name} weekly-review`
- `python {script_name} monthly-close --provider quickbooks`
- `python {script_name} review-bundle --counterparty openai`

## Operating rule

Do not let OpenClaw proceed with the autonomous action until NORNR returns `approved` or an operator explicitly approves the queued intent. Treat queued, blocked, anomalous, or prompt-risk posture as operator review states, not autonomous green lights.
"""


def _wallet_from_env() -> Wallet:
    api_key = os.environ.get("NORNR_API_KEY")
    base_url = os.environ.get("NORNR_BASE_URL", "https://nornr.com")
    agent_id = os.environ.get("NORNR_AGENT_ID")
    auth_path = os.environ.get("NORNR_AUTH_PATH")
    return Wallet.connect(
        api_key=api_key,
        base_url=base_url,
        agent_id=agent_id,
        auth_path=Path(auth_path) if auth_path else None,
    )


def _budget_tags(values: Sequence[str]) -> dict[str, str] | None:
    tags: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise AgentPayError(f"Expected budget tag in key=value form, got: {value}")
        key, raw_value = value.split("=", 1)
        tags[key] = raw_value
    return tags or None


def openclaw_cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nornr-openclaw")
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser("preflight", help="Evaluate a paid OpenClaw action before execution.")
    preflight.add_argument("--action", required=True)
    preflight.add_argument("--amount-usd", required=True, type=float)
    preflight.add_argument("--counterparty", required=True)
    preflight.add_argument("--purpose", required=True)
    preflight.add_argument("--destination")
    preflight.add_argument("--dry-run", action="store_true")
    preflight.add_argument("--context-json")
    preflight.add_argument("--skill-name")
    preflight.add_argument("--run-mode")
    preflight.add_argument("--run-id")
    preflight.add_argument("--trace-id")
    preflight.add_argument("--prompt-excerpt")
    preflight.add_argument("--autonomous", action="store_true")
    preflight.add_argument("--budget-tag", action="append", default=[])

    approvals = subparsers.add_parser("approvals", help="List pending NORNR approvals.")
    approvals.set_defaults(command="approvals")

    approve = subparsers.add_parser("approve", help="Approve a queued NORNR intent.")
    approve.add_argument("--payment-intent-id", required=True)
    approve.add_argument("--comment")

    reject = subparsers.add_parser("reject", help="Reject a queued NORNR intent.")
    reject.add_argument("--payment-intent-id", required=True)
    reject.add_argument("--comment")

    anomalies = subparsers.add_parser("anomalies", help="List anomaly posture for the OpenClaw lane.")
    anomalies.add_argument("--counterparty")

    timeline = subparsers.add_parser("timeline", help="Show the governed intent timeline.")
    timeline.set_defaults(command="timeline")

    finance_packet = subparsers.add_parser("finance-packet", help="Print the finance packet summary.")
    finance_packet.set_defaults(command="finance-packet")

    audit_export = subparsers.add_parser("audit-export", help="Export the audit artifact summary.")
    audit_export.set_defaults(command="audit-export")

    weekly_review = subparsers.add_parser("weekly-review", help="Print the weekly operator + finance review.")
    weekly_review.set_defaults(command="weekly-review")

    monthly_close = subparsers.add_parser("monthly-close", help="Assemble a close-ready finance summary.")
    monthly_close.add_argument("--provider", default="quickbooks")
    monthly_close.add_argument("--month")
    monthly_close.add_argument("--workspace-label")

    review_bundle = subparsers.add_parser("review-bundle", help="Return approvals, anomalies, timeline, and finance packet together.")
    review_bundle.add_argument("--counterparty")

    skill_markdown = subparsers.add_parser("skill-markdown", help="Render the minimal OpenClaw SKILL.md.")
    skill_markdown.set_defaults(command="skill-markdown")

    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "skill-markdown":
        print(render_openclaw_skill_markdown())
        return 0

    wallet = _wallet_from_env()
    adapter = OpenClawGovernanceAdapter(wallet)

    if args.command == "preflight":
        context = json.loads(args.context_json) if args.context_json else {}
        if not isinstance(context, dict):
            raise AgentPayError("OpenClaw preflight context_json must decode to an object.")
        if args.skill_name:
            context["skillName"] = args.skill_name
        if args.run_mode:
            context["runMode"] = args.run_mode
        if args.run_id:
            context["runId"] = args.run_id
        if args.trace_id:
            context["traceId"] = args.trace_id
        if args.prompt_excerpt:
            context["promptExcerpt"] = args.prompt_excerpt
        if args.autonomous:
            context["autonomous"] = True
        result = adapter.preflight_paid_action(
            action=args.action,
            amount_usd=args.amount_usd,
            counterparty=args.counterparty,
            purpose=args.purpose,
            destination=args.destination,
            budget_tags=_budget_tags(args.budget_tag),
            context=context,
            dry_run=args.dry_run,
        )
        print(_json_dumps(result.to_dict()))
        return 0

    if args.command == "approvals":
        print(_json_dumps(adapter.pending_approvals()))
        return 0

    if args.command == "approve":
        print(_json_dumps(adapter.approve(args.payment_intent_id, comment=args.comment)))
        return 0

    if args.command == "reject":
        print(_json_dumps(adapter.reject(args.payment_intent_id, comment=args.comment)))
        return 0

    if args.command == "anomalies":
        print(_json_dumps(adapter.anomalies(counterparty=args.counterparty)))
        return 0

    if args.command == "timeline":
        print(_json_dumps(adapter.intent_timeline()))
        return 0

    if args.command == "finance-packet":
        print(_json_dumps(adapter.finance_packet()))
        return 0

    if args.command == "audit-export":
        print(_json_dumps(adapter.audit_export()))
        return 0

    if args.command == "weekly-review":
        print(_json_dumps(adapter.weekly_review()))
        return 0

    if args.command == "monthly-close":
        print(
            _json_dumps(
                adapter.monthly_close(
                    provider=args.provider,
                    month=args.month,
                    workspace_label=args.workspace_label,
                )
            )
        )
        return 0

    if args.command == "review-bundle":
        print(_json_dumps(adapter.review_bundle(counterparty=args.counterparty)))
        return 0

    raise AgentPayError(f"Unsupported OpenClaw command: {args.command}")
