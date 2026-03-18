from __future__ import annotations

import logging
from typing import Any

from .models import DecisionRecord


def decision_log_context(decision: DecisionRecord) -> dict[str, Any]:
    return {
        "nornr_payment_intent_id": decision.payment_intent.id,
        "nornr_status": decision.status,
        "nornr_counterparty": decision.payment_intent.counterparty,
        "nornr_approval_id": decision.approval.id if decision.approval else None,
    }


def bind_logger(logger: logging.Logger, decision: DecisionRecord) -> logging.LoggerAdapter:
    return logging.LoggerAdapter(logger, extra=decision_log_context(decision))


def annotate_current_span(decision: DecisionRecord) -> None:
    try:
        from opentelemetry import trace
    except ImportError:
        return
    span = trace.get_current_span()
    if not span:
        return
    for key, value in decision_log_context(decision).items():
        if value is not None:
            span.set_attribute(key, value)
