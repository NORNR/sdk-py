from __future__ import annotations

import inspect
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping
from uuid import uuid4

from .auth import DEFAULT_BASE_URL
from .client import AuthenticationError, ApprovalRequiredError, ValidationError, Wallet
from .runtime import GovernedExecutionError


@dataclass(frozen=True)
class NornrRequestContext:
    trace_id: str
    wallet: Wallet | None
    business_context: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "traceId": self.trace_id,
            "businessContext": dict(self.business_context),
        }


@dataclass(frozen=True)
class GovernedRouteSpec:
    route_name: str
    action_name: str
    amount: float
    counterparty: str
    purpose: str
    destination: str | None = None

    def business_context(self, request: Any, *, extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
        payload = request_business_context(
            request,
            extra={
                "routeName": self.route_name,
                "surface": "api",
                "workflow": "governed-route",
            },
        )
        if extra:
            payload.update(dict(extra))
        return payload


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def get_nornr_wallet(
    api_key: str,
    *,
    base_url: str = DEFAULT_BASE_URL,
    agent_id: str | None = None,
    transport: Any | None = None,
) -> Wallet:
    """Build a NORNR wallet for FastAPI or service-layer dependency injection."""

    return Wallet.connect(api_key=api_key, base_url=base_url, agent_id=agent_id, transport=transport)


def wallet_dependency(
    *,
    base_url: str = DEFAULT_BASE_URL,
    agent_id: str | None = None,
    api_key_header: str = "x-api-key",
    transport: Any | None = None,
) -> Callable[..., Awaitable[Wallet]]:
    """Create a FastAPI dependency that resolves a NORNR wallet from request headers."""

    try:
        from fastapi import Header, HTTPException
    except ImportError as exc:  # pragma: no cover - optional dependency path
        raise RuntimeError("Install fastapi to use NORNR FastAPI helpers: pip install fastapi") from exc

    async def dependency(api_key: str | None = Header(default=None, alias=api_key_header)) -> Wallet:
        if not api_key:
            raise HTTPException(status_code=401, detail=f"Missing {api_key_header} header for NORNR wallet")
        try:
            return get_nornr_wallet(api_key, base_url=base_url, agent_id=agent_id, transport=transport)
        except AuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - framework error wrapping
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return dependency


def build_request_context(request: Any, *, wallet: Wallet | None = None) -> NornrRequestContext:
    headers = getattr(request, "headers", {}) or {}
    trace_id = headers.get("x-request-id") or headers.get("x-trace-id") or f"nornr_{uuid4().hex}"
    business_context = {
        "traceId": trace_id,
        "sessionId": headers.get("x-session-id"),
        "threadId": headers.get("x-thread-id"),
        "priority": headers.get("x-priority"),
        "tags": {
            "route": getattr(getattr(request, "url", None), "path", None),
            "method": getattr(request, "method", None),
        },
    }
    return NornrRequestContext(trace_id=trace_id, wallet=wallet, business_context=business_context)


def request_business_context(request: Any, *, extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    state_context = getattr(getattr(request, "state", None), "nornr", None)
    if isinstance(state_context, NornrRequestContext):
        payload = dict(state_context.business_context)
    else:
        payload = build_request_context(request).business_context
    if extra:
        payload.update(dict(extra))
    return payload


def request_wallet(request: Any, *, wallet: Wallet | None = None) -> Wallet:
    if wallet is not None:
        return wallet
    resolved = getattr(getattr(request, "state", None), "nornr_wallet", None)
    if resolved is None:
        raise AuthenticationError("Missing NORNR wallet in request context")
    return resolved


def nornr_middleware(
    *,
    base_url: str = DEFAULT_BASE_URL,
    agent_id: str | None = None,
    api_key_header: str = "x-api-key",
    transport: Any | None = None,
) -> Callable[[Any, Callable[[Any], Awaitable[Any]]], Awaitable[Any]]:
    async def middleware(request: Any, call_next: Callable[[Any], Awaitable[Any]]) -> Any:
        wallet: Wallet | None = None
        api_key = None
        headers = getattr(request, "headers", {}) or {}
        if hasattr(headers, "get"):
            api_key = headers.get(api_key_header)
        if api_key:
            try:
                wallet = get_nornr_wallet(api_key, base_url=base_url, agent_id=agent_id, transport=transport)
            except Exception:
                wallet = None
        context = build_request_context(request, wallet=wallet)
        if hasattr(request, "state"):
            request.state.nornr = context
            request.state.nornr_wallet = wallet
            request.state.nornr_trace_id = context.trace_id
        response = await call_next(request)
        if hasattr(response, "headers"):
            response.headers["x-nornr-trace-id"] = context.trace_id
        return response

    return middleware


def governed_endpoint(
    handler: Callable[..., Awaitable[Any]],
    *,
    map_errors: bool = True,
) -> Callable[..., Awaitable[Any]]:
    try:
        from fastapi import HTTPException
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Install fastapi to use NORNR FastAPI helpers: pip install fastapi") from exc

    async def wrapped(*args: Any, **kwargs: Any) -> Any:
        try:
            return await handler(*args, **kwargs)
        except ApprovalRequiredError as exc:
            if not map_errors:
                raise
            raise HTTPException(status_code=409, detail={"type": "approval_required", "message": str(exc), "payload": exc.payload}) from exc
        except ValidationError as exc:
            if not map_errors:
                raise
            raise HTTPException(status_code=400, detail={"type": "validation_error", "message": str(exc), "payload": exc.payload}) from exc
        except GovernedExecutionError as exc:
            if not map_errors:
                raise
            raise HTTPException(status_code=422, detail={"type": "governed_execution_error", "message": str(exc), "record": exc.record.to_summary_dict()}) from exc

    return wrapped


async def governed_execute(
    request: Any,
    *,
    action_name: str,
    amount: float,
    counterparty: str,
    purpose: str,
    callback: Callable[[], Any],
    destination: str | None = None,
    budget_tags: dict[str, str] | None = None,
    business_context: Mapping[str, Any] | None = None,
    receipt_id: str | None = None,
    evidence: Mapping[str, Any] | Callable[..., Mapping[str, Any] | None] | None = None,
    raise_on_error: bool = True,
    wallet: Wallet | None = None,
) -> Any:
    resolved_wallet = request_wallet(request, wallet=wallet)
    merged_context = request_business_context(request, extra=business_context)
    run = resolved_wallet.begin_governed_action(
        action_name=action_name,
        amount=amount,
        to=destination or counterparty,
        counterparty=counterparty,
        purpose=purpose,
        budget_tags=budget_tags,
        business_context=merged_context,
    )
    started_monotonic = time.monotonic()
    started_at = _iso_now()
    if not run.approved:
        return run.finalize(
            started_at=started_at,
            finished_at=_iso_now(),
            duration_ms=0,
            executed=False,
            receipt_id=receipt_id,
            evidence=evidence,
        )
    try:
        callback_result = callback()
        if inspect.isawaitable(callback_result):
            callback_result = await callback_result
    except Exception as exc:
        record = run.finalize(
            callback_error=str(exc),
            receipt_id=receipt_id,
            evidence=evidence,
            started_at=started_at,
            finished_at=_iso_now(),
            duration_ms=int((time.monotonic() - started_monotonic) * 1000),
            executed=True,
        )
        if raise_on_error:
            raise GovernedExecutionError(record) from exc
        return record
    return run.finalize(
        callback_result=callback_result,
        receipt_id=receipt_id,
        evidence=evidence,
        started_at=started_at,
        finished_at=_iso_now(),
        duration_ms=int((time.monotonic() - started_monotonic) * 1000),
        executed=True,
    )


def governed_route(
    *,
    action_name: str,
    amount: float | Callable[..., float],
    counterparty: str | Callable[..., str],
    purpose: str | Callable[..., str],
    destination: str | Callable[..., str] | None = None,
    budget_tags: dict[str, str] | Callable[..., dict[str, str] | None] | None = None,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    from .guards import _resolve

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            request = kwargs.get("request") or next((arg for arg in args if hasattr(arg, "headers") and hasattr(arg, "state")), None)
            if request is None:
                raise AuthenticationError("Missing request for governed FastAPI route")
            record = await governed_execute(
                request,
                action_name=action_name,
                amount=_resolve(amount, args, kwargs),
                counterparty=_resolve(counterparty, args, kwargs),
                purpose=_resolve(purpose, args, kwargs),
                destination=_resolve(destination, args, kwargs),
                budget_tags=_resolve(budget_tags, args, kwargs),
                callback=lambda: func(*args, **kwargs),
            )
            if record.requires_handoff:
                raise ApprovalRequiredError.from_decision(record.decision)
            return record.result

        return governed_endpoint(wrapped)

    return decorator


async def execute_governed_route_spec(
    request: Any,
    spec: GovernedRouteSpec,
    *,
    callback: Callable[[], Any],
    budget_tags: dict[str, str] | None = None,
    receipt_id: str | None = None,
    evidence: Mapping[str, Any] | Callable[..., Mapping[str, Any] | None] | None = None,
    raise_on_error: bool = True,
    wallet: Wallet | None = None,
    extra_business_context: Mapping[str, Any] | None = None,
) -> Any:
    return await governed_execute(
        request,
        action_name=spec.action_name,
        amount=spec.amount,
        counterparty=spec.counterparty,
        purpose=spec.purpose,
        destination=spec.destination,
        callback=callback,
        budget_tags=budget_tags,
        business_context=spec.business_context(request, extra=extra_business_context),
        receipt_id=receipt_id,
        evidence=evidence,
        raise_on_error=raise_on_error,
        wallet=wallet,
    )
