from __future__ import annotations

import json
from typing import Any, Callable, Mapping, TypedDict, cast

from .guards import nornr_guard
from .pricing import estimate_cost


class ProviderBusinessContext(TypedDict, total=False):
    surface: str
    provider: str
    providerApi: str
    operationKind: str
    requestedModel: str | None
    stream: bool
    toolCount: int
    toolNames: list[str]
    messageCount: int
    inputCount: int


class ProviderReplayContext(TypedDict, total=False):
    source: str
    provider: str
    providerApi: str
    operationKind: str
    requestedModel: str | None


class SpendAwareBusinessContext(ProviderBusinessContext, total=False):
    wrapperMode: str
    spendCapUsd: float
    estimatedRequestUsd: float
    maxCompletionTokens: int
    fallbackEstimateUsed: bool


class _MethodWrapper:
    def __init__(self, target: Any, func: Any) -> None:
        self._target = target
        self._func = func

    def __getattr__(self, name: str) -> Any:
        return getattr(self._target, name)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._func(*args, **kwargs)


class _Proxy:
    def __init__(self, target: Any) -> None:
        self._target = target

    def __getattr__(self, name: str) -> Any:
        return getattr(self._target, name)


def _infer_requested_model(args: tuple[Any, ...], kwargs: dict[str, Any], fallback_model: str | None) -> str | None:
    direct = kwargs.get("model")
    if isinstance(direct, str) and direct:
        return direct
    for item in args:
        if isinstance(item, Mapping):
            candidate = item.get("model")
            if isinstance(candidate, str) and candidate:
                return candidate
    return fallback_model


def _infer_tool_count(args: tuple[Any, ...], kwargs: dict[str, Any]) -> int | None:
    direct = kwargs.get("tools")
    if isinstance(direct, (list, tuple)):
        return len(direct)
    for item in args:
        if isinstance(item, Mapping) and isinstance(item.get("tools"), (list, tuple)):
            return len(item["tools"])
    return None


def _infer_tool_names(args: tuple[Any, ...], kwargs: dict[str, Any]) -> list[str] | None:
    tools = kwargs.get("tools")
    if not isinstance(tools, (list, tuple)):
        for item in args:
            if isinstance(item, Mapping) and isinstance(item.get("tools"), (list, tuple)):
                tools = item["tools"]
                break
    if not isinstance(tools, (list, tuple)):
        return None
    names: list[str] = []
    for tool in tools:
        if isinstance(tool, Mapping):
            function = tool.get("function")
            if isinstance(function, Mapping) and isinstance(function.get("name"), str):
                names.append(function["name"])
                continue
            if isinstance(tool.get("name"), str):
                names.append(tool["name"])
    return names or None


def _infer_message_count(args: tuple[Any, ...], kwargs: dict[str, Any]) -> int | None:
    direct = kwargs.get("messages")
    if isinstance(direct, (list, tuple)):
        return len(direct)
    for item in args:
        if isinstance(item, Mapping) and isinstance(item.get("messages"), (list, tuple)):
            return len(item["messages"])
    return None


def _infer_input_count(args: tuple[Any, ...], kwargs: dict[str, Any]) -> int | None:
    direct = kwargs.get("input")
    if isinstance(direct, (list, tuple)):
        return len(direct)
    for item in args:
        if isinstance(item, Mapping) and isinstance(item.get("input"), (list, tuple)):
            return len(item["input"])
    return None


def _infer_completion_tokens(args: tuple[Any, ...], kwargs: dict[str, Any], fallback_tokens: int | None) -> int:
    direct = kwargs.get("max_output_tokens")
    if isinstance(direct, int) and direct > 0:
        return direct
    direct = kwargs.get("max_completion_tokens")
    if isinstance(direct, int) and direct > 0:
        return direct
    for item in args:
        if isinstance(item, Mapping):
            for key in ("max_output_tokens", "max_completion_tokens"):
                candidate = item.get(key)
                if isinstance(candidate, int) and candidate > 0:
                    return candidate
    return max(0, fallback_tokens or 0)


def _serialize_prompt_payload(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=True, default=str)
    except TypeError:
        return str(value)


def _infer_prompt_text(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    if "messages" in kwargs:
        return _serialize_prompt_payload(kwargs.get("messages"))
    if "input" in kwargs:
        return _serialize_prompt_payload(kwargs.get("input"))
    for item in args:
        if isinstance(item, Mapping):
            if "messages" in item:
                return _serialize_prompt_payload(item.get("messages"))
            if "input" in item:
                return _serialize_prompt_payload(item.get("input"))
    return ""


def _infer_operation_kind(operation_path: str) -> str:
    if operation_path.endswith(".stream"):
        return "stream"
    if "responses" in operation_path:
        return "responses"
    if "messages" in operation_path:
        return "messages"
    if "chat.completions" in operation_path:
        return "chat-completions"
    return "provider-call"


def _spend_aware_amount_resolver(
    *,
    max_spend_usd: float,
    model: str | None,
    fallback_estimate_usd: float | None,
    default_max_completion_tokens: int | None,
) -> Callable[..., float]:
    def _resolve_amount(*args: Any, **kwargs: Any) -> float:
        requested_model = _infer_requested_model(args, kwargs, model)
        if not requested_model:
            return round(max_spend_usd, 6)
        completion_tokens = _infer_completion_tokens(args, kwargs, default_max_completion_tokens)
        estimate = estimate_cost(
            model=requested_model,
            prompt=_infer_prompt_text(args, kwargs),
            completion_tokens=completion_tokens,
        )
        if estimate.estimated_total_usd > 0:
            return round(min(max_spend_usd, estimate.estimated_total_usd), 6)
        if fallback_estimate_usd is not None:
            return round(min(max_spend_usd, fallback_estimate_usd), 6)
        return round(max_spend_usd, 6)

    return _resolve_amount


def _spend_aware_business_context(
    provider: str,
    *,
    max_spend_usd: float,
    model: str | None,
    fallback_estimate_usd: float | None,
    default_max_completion_tokens: int | None,
    user_business_context: Mapping[str, Any] | Callable[..., Mapping[str, Any] | None] | None,
) -> Callable[..., SpendAwareBusinessContext]:
    def _build(*args: Any, **kwargs: Any) -> SpendAwareBusinessContext:
        requested_model = _infer_requested_model(args, kwargs, model)
        completion_tokens = _infer_completion_tokens(args, kwargs, default_max_completion_tokens)
        fallback_estimate_used = True
        estimate_total = round(max_spend_usd, 6)
        if requested_model:
            estimate = estimate_cost(
                model=requested_model,
                prompt=_infer_prompt_text(args, kwargs),
                completion_tokens=completion_tokens,
            )
            if estimate.estimated_total_usd > 0:
                estimate_total = round(min(max_spend_usd, estimate.estimated_total_usd), 6)
                fallback_estimate_used = False
            elif fallback_estimate_usd is not None:
                estimate_total = round(min(max_spend_usd, fallback_estimate_usd), 6)
        payload: dict[str, Any] = {
            "surface": "provider-sdk-wrapper",
            "provider": provider,
            "providerApi": "provider-wrapper",
            "operationKind": "wrapper-preflight",
            "requestedModel": requested_model,
            "stream": False,
            "wrapperMode": "spend-aware",
            "spendCapUsd": round(max_spend_usd, 6),
            "estimatedRequestUsd": estimate_total,
            "maxCompletionTokens": completion_tokens,
            "fallbackEstimateUsed": fallback_estimate_used,
        }
        if user_business_context:
            extra = user_business_context(*args, **kwargs) if callable(user_business_context) else user_business_context
            if extra:
                payload.update(dict(extra))
        return cast(SpendAwareBusinessContext, payload)

    return _build


def _wrap_method(
    method: Any,
    *,
    wallet: Any,
    amount: float | Callable[..., float],
    counterparty: str,
    purpose: str,
    destination: str | None,
    budget_tags: dict[str, str] | None,
    provider: str,
    model: str | None,
    operation_path: str,
    user_business_context: Mapping[str, Any] | Callable[..., Mapping[str, Any] | None] | None,
) -> Any:
    if not callable(method):
        return method

    def _business_context(*args: Any, **kwargs: Any) -> ProviderBusinessContext:
        requested_model = _infer_requested_model(args, kwargs, model)
        tool_count = _infer_tool_count(args, kwargs)
        tool_names = _infer_tool_names(args, kwargs)
        message_count = _infer_message_count(args, kwargs)
        input_count = _infer_input_count(args, kwargs)
        payload: dict[str, Any] = {
            "surface": "provider-sdk",
            "provider": provider,
            "providerApi": operation_path,
            "operationKind": _infer_operation_kind(operation_path),
            "requestedModel": requested_model,
            "stream": operation_path.endswith(".stream") or bool(kwargs.get("stream")),
        }
        if tool_count is not None:
            payload["toolCount"] = tool_count
        if tool_names is not None:
            payload["toolNames"] = tool_names
        if message_count is not None:
            payload["messageCount"] = message_count
        if input_count is not None:
            payload["inputCount"] = input_count
        if user_business_context:
            extra = user_business_context(*args, **kwargs) if callable(user_business_context) else user_business_context
            if extra:
                payload.update(dict(extra))
        return cast(ProviderBusinessContext, payload)

    def _replay_context(*args: Any, **kwargs: Any) -> ProviderReplayContext:
        return {
            "source": "sdk.wrapper",
            "provider": provider,
            "providerApi": operation_path,
            "operationKind": _infer_operation_kind(operation_path),
            "requestedModel": _infer_requested_model(args, kwargs, model),
        }

    return nornr_guard(
        wallet,
        amount=amount,
        counterparty=counterparty,
        purpose=lambda *args, **kwargs: purpose,
        destination=destination,
        budget_tags=budget_tags,
        business_context=_business_context,
        replay_context=_replay_context,
    )(method)


def _wrap_client(
    client: Any,
    wallet: Any,
    *,
    amount: float | Callable[..., float],
    counterparty: str,
    purpose: str,
    destination: str | None = None,
    budget_tags: dict[str, str] | None = None,
    provider: str | None = None,
    model: str | None = None,
    business_context: Mapping[str, Any] | Callable[..., Mapping[str, Any] | None] | None = None,
) -> Any:
    inferred_provider = provider or getattr(client, "__class__", type("Client", (), {})).__name__.lower()
    root = _Proxy(client)
    for branch_name in ("chat", "responses", "messages"):
        branch = getattr(client, branch_name, None)
        if branch is None:
            continue
        branch_proxy = _Proxy(branch)
        for operation_name in ("create", "stream"):
            method = getattr(branch, operation_name, None)
            if callable(method):
                setattr(
                    branch_proxy,
                    operation_name,
                    _wrap_method(
                        method,
                        wallet=wallet,
                        amount=amount,
                        counterparty=counterparty,
                        purpose=purpose,
                        destination=destination,
                        budget_tags=budget_tags,
                        provider=inferred_provider,
                        model=model,
                        operation_path=f"{branch_name}.{operation_name}",
                        user_business_context=business_context,
                    ),
                )
        completions = getattr(branch, "completions", None)
        if completions is not None:
            completions_proxy = _Proxy(completions)
            for operation_name in ("create", "stream"):
                method = getattr(completions, operation_name, None)
                if callable(method):
                    setattr(
                        completions_proxy,
                        operation_name,
                        _wrap_method(
                            method,
                            wallet=wallet,
                            amount=amount,
                            counterparty=counterparty,
                            purpose=purpose,
                            destination=destination,
                            budget_tags=budget_tags,
                            provider=inferred_provider,
                            model=model,
                            operation_path=f"{branch_name}.completions.{operation_name}",
                            user_business_context=business_context,
                        ),
                    )
            setattr(branch_proxy, "completions", completions_proxy)
        setattr(root, branch_name, branch_proxy)
    setattr(
        root,
        "_nornr_provider_context",
        {
            "provider": inferred_provider,
            "model": model,
            "wrappedBranches": [name for name in ("chat", "responses", "messages") if getattr(client, name, None) is not None],
        },
    )
    return root


def wrap(
    client: Any,
    wallet: Any,
    *,
    amount: float,
    counterparty: str,
    purpose: str,
    destination: str | None = None,
    budget_tags: dict[str, str] | None = None,
    provider: str | None = None,
    model: str | None = None,
    business_context: Mapping[str, Any] | Callable[..., Mapping[str, Any] | None] | None = None,
) -> Any:
    """Wrap an OpenAI- or Anthropic-style client with a NORNR preflight guard."""
    return _wrap_client(
        client,
        wallet,
        amount=amount,
        counterparty=counterparty,
        purpose=purpose,
        destination=destination,
        budget_tags=budget_tags,
        provider=provider,
        model=model,
        business_context=business_context,
    )


def create_spend_aware_client(
    client: Any,
    wallet: Any,
    *,
    max_spend_usd: float,
    counterparty: str,
    purpose: str,
    destination: str | None = None,
    budget_tags: dict[str, str] | None = None,
    provider: str | None = None,
    model: str | None = None,
    fallback_estimate_usd: float | None = None,
    default_max_completion_tokens: int | None = 512,
    business_context: Mapping[str, Any] | Callable[..., Mapping[str, Any] | None] | None = None,
) -> Any:
    """Wrap a provider client with a spend-aware NORNR preflight based on an estimated per-request cap."""
    inferred_provider = provider or getattr(client, "__class__", type("Client", (), {})).__name__.lower()
    return _wrap_client(
        client,
        wallet,
        amount=_spend_aware_amount_resolver(
            max_spend_usd=max_spend_usd,
            model=model,
            fallback_estimate_usd=fallback_estimate_usd,
            default_max_completion_tokens=default_max_completion_tokens,
        ),
        counterparty=counterparty,
        purpose=purpose,
        destination=destination,
        budget_tags=budget_tags,
        provider=inferred_provider,
        model=model,
        business_context=_spend_aware_business_context(
            inferred_provider,
            max_spend_usd=max_spend_usd,
            model=model,
            fallback_estimate_usd=fallback_estimate_usd,
            default_max_completion_tokens=default_max_completion_tokens,
            user_business_context=business_context,
        ),
    )


def wrap_async(
    client: Any,
    wallet: Any,
    *,
    amount: float,
    counterparty: str,
    purpose: str,
    destination: str | None = None,
    budget_tags: dict[str, str] | None = None,
    provider: str | None = None,
    model: str | None = None,
    business_context: Mapping[str, Any] | Callable[..., Mapping[str, Any] | None] | None = None,
) -> Any:
    return _wrap_client(
        client,
        wallet,
        amount=amount,
        counterparty=counterparty,
        purpose=purpose,
        destination=destination,
        budget_tags=budget_tags,
        provider=provider,
        model=model,
        business_context=business_context,
    )


def wrap_openai_client(
    client: Any,
    wallet: Any,
    *,
    amount: float,
    purpose: str,
    destination: str | None = None,
    budget_tags: dict[str, str] | None = None,
    model: str | None = None,
    business_context: Mapping[str, Any] | Callable[..., Mapping[str, Any] | None] | None = None,
) -> Any:
    return wrap(
        client,
        wallet,
        amount=amount,
        counterparty="openai",
        purpose=purpose,
        destination=destination,
        budget_tags=budget_tags,
        provider="openai",
        model=model,
        business_context=business_context,
    )


def create_spend_aware_openai_client(
    client: Any,
    wallet: Any,
    *,
    max_spend_usd: float,
    purpose: str,
    destination: str | None = None,
    budget_tags: dict[str, str] | None = None,
    model: str | None = None,
    fallback_estimate_usd: float | None = None,
    default_max_completion_tokens: int | None = 512,
    business_context: Mapping[str, Any] | Callable[..., Mapping[str, Any] | None] | None = None,
) -> Any:
    return create_spend_aware_client(
        client,
        wallet,
        max_spend_usd=max_spend_usd,
        counterparty="openai",
        purpose=purpose,
        destination=destination,
        budget_tags=budget_tags,
        provider="openai",
        model=model,
        fallback_estimate_usd=fallback_estimate_usd,
        default_max_completion_tokens=default_max_completion_tokens,
        business_context=business_context,
    )


def wrap_anthropic_client(
    client: Any,
    wallet: Any,
    *,
    amount: float,
    purpose: str,
    destination: str | None = None,
    budget_tags: dict[str, str] | None = None,
    model: str | None = None,
    business_context: Mapping[str, Any] | Callable[..., Mapping[str, Any] | None] | None = None,
) -> Any:
    return wrap_async(
        client,
        wallet,
        amount=amount,
        counterparty="anthropic",
        purpose=purpose,
        destination=destination,
        budget_tags=budget_tags,
        provider="anthropic",
        model=model,
        business_context=business_context,
    )


def create_spend_aware_anthropic_client(
    client: Any,
    wallet: Any,
    *,
    max_spend_usd: float,
    purpose: str,
    destination: str | None = None,
    budget_tags: dict[str, str] | None = None,
    model: str | None = None,
    fallback_estimate_usd: float | None = None,
    default_max_completion_tokens: int | None = 512,
    business_context: Mapping[str, Any] | Callable[..., Mapping[str, Any] | None] | None = None,
) -> Any:
    return create_spend_aware_client(
        client,
        wallet,
        max_spend_usd=max_spend_usd,
        counterparty="anthropic",
        purpose=purpose,
        destination=destination,
        budget_tags=budget_tags,
        provider="anthropic",
        model=model,
        fallback_estimate_usd=fallback_estimate_usd,
        default_max_completion_tokens=default_max_completion_tokens,
        business_context=business_context,
    )
