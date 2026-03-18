from __future__ import annotations

from typing import Any

from .guards import nornr_guard


class _MethodWrapper:
    def __init__(self, target: Any, func) -> None:
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


def wrap(
    client: Any,
    wallet: Any,
    *,
    amount: float,
    counterparty: str,
    purpose: str,
    destination: str | None = None,
    budget_tags: dict[str, str] | None = None,
) -> Any:
    """Wrap an OpenAI- or Anthropic-style client with a NORNR preflight guard."""

    root = _Proxy(client)
    if hasattr(client, "chat") and hasattr(client.chat, "completions") and hasattr(client.chat.completions, "create"):
        chat_proxy = _Proxy(client.chat)
        completions_proxy = _Proxy(client.chat.completions)
        completions_proxy.create = nornr_guard(
            wallet,
            amount=amount,
            counterparty=counterparty,
            purpose=purpose,
            destination=destination,
            budget_tags=budget_tags,
        )(client.chat.completions.create)
        chat_proxy.completions = completions_proxy
        root.chat = chat_proxy
    if hasattr(client, "messages") and hasattr(client.messages, "create"):
        messages_proxy = _Proxy(client.messages)
        messages_proxy.create = nornr_guard(
            wallet,
            amount=amount,
            counterparty=counterparty,
            purpose=purpose,
            destination=destination,
            budget_tags=budget_tags,
        )(client.messages.create)
        root.messages = messages_proxy
    return root
