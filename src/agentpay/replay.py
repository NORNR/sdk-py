from __future__ import annotations

import inspect
from typing import Any, Callable, Mapping


SENSITIVE_MARKERS = ("token", "secret", "password", "auth", "api_key", "apikey", "authorization", "cookie", "session")


def redact_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) > 120:
            return f"{value[:117]}..."
        return value
    if isinstance(value, Mapping):
        return {
            str(key): ("[redacted]" if any(marker in str(key).lower() for marker in SENSITIVE_MARKERS) else redact_value(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        preview = list(value)[:6]
        return [redact_value(item) for item in preview]
    return repr(value)


def current_callsite(skip_modules: tuple[str, ...] = ("agentpay.",)) -> dict[str, Any] | None:
    for frame in inspect.stack()[1:]:
        module = inspect.getmodule(frame.frame)
        module_name = module.__name__ if module else ""
        if any(module_name.startswith(prefix) for prefix in skip_modules):
            continue
        return {
            "module": module_name or None,
            "function": frame.function,
            "file": frame.filename,
            "line": frame.lineno,
        }
    return None


def build_replay_context(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    *,
    source: str,
) -> dict[str, Any]:
    signature = inspect.signature(func)
    bound = signature.bind_partial(*args, **kwargs)
    bound.apply_defaults()
    sanitized_inputs = {name: redact_value(value) for name, value in bound.arguments.items() if name not in {"self", "cls"}}
    code = getattr(func, "__code__", None)
    return {
        "source": source,
        "function": getattr(func, "__qualname__", getattr(func, "__name__", "callable")),
        "module": getattr(func, "__module__", None),
        "file": getattr(code, "co_filename", None),
        "line": getattr(code, "co_firstlineno", None),
        "inputs": sanitized_inputs,
    }


def merge_replay_context(explicit: Mapping[str, Any] | None = None, *, default_source: str = "sdk") -> dict[str, Any] | None:
    callsite = current_callsite() or {}
    payload = {
        "source": default_source,
        **callsite,
        **dict(explicit or {}),
    }
    return {key: value for key, value in payload.items() if value not in (None, "", {}, [])} or None
