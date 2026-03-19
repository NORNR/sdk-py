from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, Literal, Mapping


def _normalize_tags(value: Mapping[str, Any] | None) -> dict[str, str] | None:
    if not value:
        return None
    normalized = {str(key): str(item) for key, item in value.items() if item is not None and item != ""}
    return normalized or None


@dataclass(frozen=True)
class BusinessContext:
    reason: str | None = None
    ticket_id: str | None = None
    customer_segment: str | None = None
    priority: str | None = None
    session_id: str | None = None
    thread_id: str | None = None
    tags: dict[str, str] | None = None

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "reason": self.reason,
            "ticketId": self.ticket_id,
            "customerSegment": self.customer_segment,
            "priority": self.priority,
            "sessionId": self.session_id,
            "threadId": self.thread_id,
            "tags": self.tags or None,
        }
        return {key: value for key, value in payload.items() if value not in (None, "", {}, [])}


_ACTIVE_BUSINESS_CONTEXT: ContextVar[BusinessContext | None] = ContextVar("nornr_business_context", default=None)


class BusinessContextScope:
    def __init__(
        self,
        *,
        reason: str | None = None,
        ticket_id: str | None = None,
        customer_segment: str | None = None,
        priority: str | None = None,
        session_id: str | None = None,
        thread_id: str | None = None,
        tags: Mapping[str, Any] | None = None,
    ) -> None:
        current = _ACTIVE_BUSINESS_CONTEXT.get()
        current_tags = current.tags if current else None
        merged_tags = {
            **(current_tags or {}),
            **(_normalize_tags(tags) or {}),
        } or None
        self.context = BusinessContext(
            reason=reason or current.reason if current else reason,
            ticket_id=ticket_id or current.ticket_id if current else ticket_id,
            customer_segment=customer_segment or current.customer_segment if current else customer_segment,
            priority=priority or current.priority if current else priority,
            session_id=session_id or current.session_id if current else session_id,
            thread_id=thread_id or current.thread_id if current else thread_id,
            tags=merged_tags,
        )
        self._token: Token[BusinessContext | None] | None = None

    def __enter__(self) -> BusinessContext:
        self._token = _ACTIVE_BUSINESS_CONTEXT.set(self.context)
        return self.context

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> Literal[False]:
        if self._token is not None:
            _ACTIVE_BUSINESS_CONTEXT.reset(self._token)
        return False

    async def __aenter__(self) -> BusinessContext:
        return self.__enter__()

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> Literal[False]:
        return self.__exit__(exc_type, exc, tb)


def business_context(
    *,
    reason: str | None = None,
    ticket_id: str | None = None,
    customer_segment: str | None = None,
    priority: str | None = None,
    session_id: str | None = None,
    thread_id: str | None = None,
    tags: Mapping[str, Any] | None = None,
) -> BusinessContextScope:
    return BusinessContextScope(
        reason=reason,
        ticket_id=ticket_id,
        customer_segment=customer_segment,
        priority=priority,
        session_id=session_id,
        thread_id=thread_id,
        tags=tags,
    )


def current_business_context() -> BusinessContext | None:
    return _ACTIVE_BUSINESS_CONTEXT.get()


def merge_business_context(explicit: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    current = current_business_context()
    current_payload = current.to_payload() if current else {}
    explicit_payload = dict(explicit or {})
    explicit_tags = _normalize_tags(explicit_payload.get("tags"))
    merged_tags = {
        **(current_payload.get("tags") or {}),
        **(explicit_tags or {}),
    } or None
    merged = {
        **current_payload,
        **{key: value for key, value in explicit_payload.items() if value not in (None, "", {}, [])},
    }
    if merged_tags:
        merged["tags"] = merged_tags
    return merged or None
