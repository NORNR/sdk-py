from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Mapping

from .models import DecisionRecord
from .replay import SENSITIVE_MARKERS, redact_value


def decision_log_context(decision: DecisionRecord, *, extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "nornr_payment_intent_id": decision.payment_intent.id,
        "nornr_status": decision.status,
        "nornr_counterparty": decision.payment_intent.counterparty,
        "nornr_approval_id": decision.approval.id if decision.approval else None,
        **{
            f"nornr_{key}": ("[redacted]" if any(marker in str(key).lower() for marker in SENSITIVE_MARKERS) else redact_value(value))
            for key, value in dict(extra or {}).items()
        },
    }


def bind_logger(
    logger: logging.Logger,
    decision: DecisionRecord,
    *,
    extra: Mapping[str, Any] | None = None,
) -> logging.LoggerAdapter:
    return logging.LoggerAdapter(logger, extra=decision_log_context(decision, extra=extra))


@dataclass(frozen=True)
class DecisionEvent:
    name: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class MetricPoint:
    name: str
    value: float
    tags: dict[str, Any] = field(default_factory=dict)


class InMemoryEventSink:
    def __init__(self) -> None:
        self.events: list[DecisionEvent] = []

    def emit(self, name: str, payload: Mapping[str, Any]) -> DecisionEvent:
        event = DecisionEvent(name=name, payload=dict(payload))
        self.events.append(event)
        return event


class InMemoryMetricsCollector:
    def __init__(self) -> None:
        self.points: list[MetricPoint] = []

    def record(self, name: str, value: float = 1.0, *, tags: Mapping[str, Any] | None = None) -> MetricPoint:
        point = MetricPoint(
            name=name,
            value=float(value),
            tags={str(key): redact_value(item) for key, item in dict(tags or {}).items()},
        )
        self.points.append(point)
        return point


def decision_event_payload(
    decision: DecisionRecord,
    *,
    stage: str = "decision",
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payment_intent = decision.payment_intent
    return {
        "stage": stage,
        "status": decision.status,
        "paymentIntentId": payment_intent.id,
        "counterparty": payment_intent.counterparty,
        "amountUsd": payment_intent.amount_usd,
        "purpose": payment_intent.purpose,
        "approvalId": decision.approval.id if decision.approval else None,
        "requiresApproval": bool(decision.approval),
        "extra": redact_value(dict(extra or {})),
    }


def emit_decision_event(
    decision: DecisionRecord,
    *,
    logger: logging.Logger | None = None,
    sink: InMemoryEventSink | None = None,
    event_name: str = "nornr.decision",
    stage: str = "decision",
    extra: Mapping[str, Any] | None = None,
) -> DecisionEvent:
    payload = decision_event_payload(decision, stage=stage, extra=extra)
    if logger is not None:
        bind_logger(logger, decision, extra=extra).info("%s", event_name)
    if sink is not None:
        return sink.emit(event_name, payload)
    return DecisionEvent(name=event_name, payload=payload)


def record_decision_metric(
    decision: DecisionRecord,
    *,
    collector: InMemoryMetricsCollector,
    name: str = "nornr.decision.count",
    value: float = 1.0,
    extra_tags: Mapping[str, Any] | None = None,
) -> MetricPoint:
    tags = {
        "status": decision.status,
        "counterparty": decision.payment_intent.counterparty,
        "requiresApproval": bool(decision.approval),
        **dict(extra_tags or {}),
    }
    return collector.record(name, value=value, tags=tags)


def annotate_current_span(decision: DecisionRecord, *, extra: Mapping[str, Any] | None = None) -> None:
    try:
        from opentelemetry import trace
    except ImportError:
        return
    span = trace.get_current_span()
    if not span:
        return
    for key, value in decision_log_context(decision, extra=extra).items():
        if value is not None:
            span.set_attribute(key, value)
    span.add_event(
        "nornr.decision",
        attributes={
            "nornr_stage": "decision",
            "nornr_requires_approval": bool(decision.approval),
        },
    )
