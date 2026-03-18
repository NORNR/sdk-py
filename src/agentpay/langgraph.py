from __future__ import annotations

from typing import Any, Mapping

from .context import business_context
from .models import DecisionRecord


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


def state_context(state: Mapping[str, Any] | None):
    payload = state_business_context(state)
    return business_context(
        ticket_id=payload.get("ticketId"),
        customer_segment=payload.get("customerSegment"),
        priority=payload.get("priority"),
        session_id=payload.get("sessionId"),
        thread_id=payload.get("threadId"),
        tags=payload.get("tags"),
    )
