from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib import error, request


@dataclass(frozen=True)
class TransportConfig:
    timeout_seconds: float = 15.0
    default_headers: dict[str, str] = field(default_factory=dict)
    user_agent: str = "agentpay-py/0.1.0"


class SyncHttpTransport:
    def __init__(self, config: TransportConfig | None = None) -> None:
        self.config = config or TransportConfig()

    def request(
        self,
        *,
        url: str,
        method: str = "GET",
        headers: Mapping[str, str] | None = None,
        body: Any = None,
    ) -> tuple[int, str]:
        merged_headers = {
            "user-agent": self.config.user_agent,
            **self.config.default_headers,
            **dict(headers or {}),
        }
        try:
            import httpx
        except ImportError:
            data: bytes | None = None
            if body is not None:
                if "content-type" not in {key.lower(): value for key, value in merged_headers.items()}:
                    merged_headers["content-type"] = "application/json"
                data = json.dumps(body).encode("utf-8")

            req = request.Request(url, method=method, headers=merged_headers, data=data)
            try:
                with request.urlopen(req, timeout=self.config.timeout_seconds) as response:
                    return response.status, response.read().decode("utf-8")
            except error.HTTPError as exc:
                return exc.code, exc.read().decode("utf-8")

        with httpx.Client(timeout=self.config.timeout_seconds, headers=self.config.default_headers) as client:
            response = client.request(
                method=method,
                url=url,
                headers={"user-agent": self.config.user_agent, **dict(headers or {})},
                json=body,
            )
            return response.status_code, response.text


class AsyncHttpTransport:
    def __init__(self, config: TransportConfig | None = None, sync_transport: SyncHttpTransport | None = None) -> None:
        self.config = config or TransportConfig()
        self._sync_transport = sync_transport or SyncHttpTransport(self.config)

    async def request(
        self,
        *,
        url: str,
        method: str = "GET",
        headers: Mapping[str, str] | None = None,
        body: Any = None,
    ) -> tuple[int, str]:
        try:
            import httpx
        except ImportError:
            return await asyncio.to_thread(
                self._sync_transport.request,
                url=url,
                method=method,
                headers=headers,
                body=body,
            )

        async with httpx.AsyncClient(timeout=self.config.timeout_seconds, headers=self.config.default_headers) as client:
            response = await client.request(
                method=method,
                url=url,
                headers={"user-agent": self.config.user_agent, **dict(headers or {})},
                json=body,
            )
            return response.status_code, response.text
