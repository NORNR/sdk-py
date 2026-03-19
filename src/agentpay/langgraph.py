from __future__ import annotations

from typing import Any, Mapping

from .context import business_context
from .models import DecisionRecord
from .runtime import GovernedActionRun, GovernedExecutionRecord, GovernedHandoffRecord


def decision_metadata(decision: DecisionRecord) -> dict[str, Any]:
    """Normalize a NORNR decision into LangGraph-friendly state fields."""

    return {
        "payment_intent_ids": [decision.payment_intent.id] if decision.payment_intent.id else [],
        "approval_ids": [decision.approval.id] if decision.approval and decision.approval.id else [],
        "decision_statuses": [decision.status],
        "last_decision": decision.to_summary_dict(),
    }


def nornr_state_reducer(current: Mapping[str, Any] | None, update: Mapping[str, Any] | None) -> dict[str, Any]:
    """Merge NORNR decision metadata into a LangGraph-style state object."""

    current_state = dict(current or {})
    next_state = dict(update or {})
    merged: dict[str, Any] = {**current_state, **next_state}
    for key in ("payment_intent_ids", "approval_ids", "decision_statuses"):
        values: list[Any] = []
        for item in current_state.get(key, []) or []:
            if item not in values:
                values.append(item)
        for item in next_state.get(key, []) or []:
            if item not in values:
                values.append(item)
        if values:
            merged[key] = values
    if "last_decision" not in merged:
        merged["last_decision"] = current_state.get("last_decision") or next_state.get("last_decision")
    return merged


def record_decision(state: Mapping[str, Any] | None, decision: DecisionRecord) -> dict[str, Any]:
    """Append a NORNR decision into an existing LangGraph state snapshot."""

    return nornr_state_reducer(state, decision_metadata(decision))


def execution_metadata(record: GovernedExecutionRecord) -> dict[str, Any]:
    return {
        "governed_run": record.to_summary_dict(),
        "last_execution_status": record.execution_status,
        "receipt_ids": [record.receipt.id] if record.receipt and record.receipt.id else [],
    }


def run_metadata(run: GovernedActionRun) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "governed_run_ids": [run.run_id],
        "intent_keys": [run.intent_key],
        "idempotency_keys": [run.idempotency_key],
        "last_run": {
            "runId": run.run_id,
            "intentKey": run.intent_key,
            "idempotencyKey": run.idempotency_key,
            "actionName": run.action_name,
            "status": run.decision.status,
        },
    }
    if run.queued or run.blocked:
        payload["handoff"] = run.to_handoff_dict()
        payload["requires_human_review"] = True
    return payload


def record_execution(state: Mapping[str, Any] | None, record: GovernedExecutionRecord) -> dict[str, Any]:
    current = nornr_state_reducer(state, {"last_decision": record.decision.to_summary_dict()})
    merged = {**current, **execution_metadata(record)}
    if state and "receipt_ids" in state:
        existing = list(state.get("receipt_ids") or [])
        for item in merged.get("receipt_ids", []) or []:
            if item not in existing:
                existing.append(item)
        merged["receipt_ids"] = existing
    return merged


def begin_stateful_action(
    wallet: Any,
    state: Mapping[str, Any] | None,
    *,
    action_name: str,
    amount: float,
    counterparty: str,
    purpose: str,
    budget_tags: dict[str, str] | None = None,
) -> Any:
    return wallet.begin_governed_action(
        action_name=action_name,
        amount=amount,
        to=counterparty,
        counterparty=counterparty,
        purpose=purpose,
        budget_tags=budget_tags,
        business_context=state_business_context(state),
        replay_context={"source": "langgraph.begin_stateful_action", "state": dict(state or {})},
    )


def handoff_state(run: GovernedActionRun) -> dict[str, Any]:
    return {
        "handoff": run.to_handoff_dict(),
        "requires_human_review": run.queued or run.blocked,
    }


def record_handoff(state: Mapping[str, Any] | None, run: GovernedActionRun | GovernedHandoffRecord) -> dict[str, Any]:
    handoff = run.to_dict() if isinstance(run, GovernedHandoffRecord) else run.to_handoff_dict()
    merged = nornr_state_reducer(state, {"handoff": handoff, "requires_human_review": True})
    merged["last_handoff_status"] = handoff.get("status")
    return merged


def record_resume(state: Mapping[str, Any] | None, decision: DecisionRecord | GovernedActionRun) -> dict[str, Any]:
    resolved_decision = decision.decision if isinstance(decision, GovernedActionRun) else decision
    merged = record_decision(state, resolved_decision)
    merged["requires_human_review"] = False
    merged["handoff"] = None
    merged["last_handoff_status"] = resolved_decision.status
    return merged


def resume_stateful_action(
    wallet: Any,
    state: Mapping[str, Any] | None,
    *,
    action_name: str,
) -> Any:
    decision = (state or {}).get("last_decision")
    if not decision:
        raise ValueError("LangGraph state is missing last_decision")
    return wallet.resume_governed_action(decision, action_name=action_name, business_context=state_business_context(state))


def state_business_context(state: Mapping[str, Any] | None) -> dict[str, Any]:
    current = dict(state or {})
    return {
        "ticketId": current.get("ticket_id") or current.get("ticketId"),
        "customerSegment": current.get("customer_segment") or current.get("customerSegment"),
        "priority": current.get("priority"),
        "sessionId": current.get("session_id") or current.get("sessionId"),
        "threadId": current.get("thread_id") or current.get("threadId"),
        "tags": current.get("budget_tags") or current.get("tags") or None,
    }


def tool_business_context(
    state: Mapping[str, Any] | None,
    *,
    node_name: str | None = None,
    tool_name: str | None = None,
) -> dict[str, Any]:
    payload = state_business_context(state)
    payload["langgraph"] = {
        "node": node_name,
        "tool": tool_name,
    }
    return payload


def node_business_context(
    state: Mapping[str, Any] | None,
    *,
    node_name: str,
    phase: str,
    tool_name: str | None = None,
) -> dict[str, Any]:
    payload = tool_business_context(state, node_name=node_name, tool_name=tool_name)
    payload["langgraph"]["phase"] = phase
    return payload


def record_tool_result(
    state: Mapping[str, Any] | None,
    *,
    node_name: str,
    tool_name: str,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    merged = nornr_state_reducer(state, {})
    tool_events = list(merged.get("tool_events", []) or [])
    tool_events.append(
        {
            "node": node_name,
            "tool": tool_name,
            "payload": dict(payload or {}),
        }
    )
    merged["tool_events"] = tool_events
    return merged


def state_context(state: Mapping[str, Any] | None) -> Any:
    payload = state_business_context(state)
    return business_context(
        ticket_id=payload.get("ticketId"),
        customer_segment=payload.get("customerSegment"),
        priority=payload.get("priority"),
        session_id=payload.get("sessionId"),
        thread_id=payload.get("threadId"),
        tags=payload.get("tags"),
    )
