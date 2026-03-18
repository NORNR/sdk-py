from __future__ import annotations

import webbrowser
from typing import Any, Callable

from .client import ApprovalRequiredError, DecisionRecord


def rescue_mode(
    decision: DecisionRecord,
    wallet: Any,
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> Any:
    """Offer a local human-in-the-loop prompt for queued NORNR decisions."""

    if decision.status == "approved":
        return decision
    if decision.status != "queued" or not decision.approval:
        raise ApprovalRequiredError.from_decision(decision)
    approval_id = decision.approval.id or ""
    while True:
        output_fn(
            f"Approval required: ${decision.payment_intent.amount_usd:.2f} to "
            f"{decision.payment_intent.counterparty}. [A]pprove / [D]eny / [O]pen browser / [S]kip"
        )
        choice = input_fn("> ").strip().lower()[:1]
        if choice == "a":
            return wallet.approve_if_needed(decision, comment="Approved from NORNR rescue mode")
        if choice == "d":
            return wallet.reject(approval_id, comment="Rejected from NORNR rescue mode")
        if choice == "o":
            if decision.approval_url:
                webbrowser.open(decision.approval_url)
                output_fn(f"Opened {decision.approval_url}")
            continue
        if choice in {"s", ""}:
            raise ApprovalRequiredError.from_decision(decision)
