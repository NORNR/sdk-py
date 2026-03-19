from __future__ import annotations

from typing import Any, Awaitable, Callable

from .auth import DEFAULT_BASE_URL
from .client import AuthenticationError, Wallet


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
