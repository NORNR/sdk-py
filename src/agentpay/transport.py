from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib import error, request


@dataclass(frozen=True)
class TransportConfig:
    timeout_seconds: float = 15.0
    default_headers: dict[str, str] = field(default_factory=dict)
    user_agent: str = "agentpay-py/0.1.0"
    max_retries: int = 1
    retry_backoff_seconds: float = 0.25
    retry_status_codes: tuple[int, ...] = (429, 502, 503, 504)
    retry_methods: tuple[str, ...] = ("GET",)


def _merge_headers(config: TransportConfig, headers: Mapping[str, str] | None = None) -> dict[str, str]:
    return {
        "user-agent": config.user_agent,
        **config.default_headers,
        **dict(headers or {}),
    }


def _should_retry(
    config: TransportConfig,
    *,
    attempt: int,
    method: str,
    status_code: int | None = None,
) -> bool:
    normalized_method = method.upper()
    if attempt >= config.max_retries:
        return False
    if normalized_method not in {item.upper() for item in config.retry_methods}:
        return False
    return status_code is None or status_code in set(config.retry_status_codes)


def _retry_delay(config: TransportConfig, attempt: int) -> float:
    return config.retry_backoff_seconds * (2**attempt)


class SyncHttpTransport:
    def __init__(self, config: TransportConfig | None = None) -> None:
        self.config = config or TransportConfig()
        self._httpx_client: Any | None = None

    def _get_httpx_client(self) -> Any:
        if self._httpx_client is None:
            import httpx

            self._httpx_client = httpx.Client(
                timeout=self.config.timeout_seconds,
                headers=self.config.default_headers,
            )
        return self._httpx_client

    def close(self) -> None:
        if self._httpx_client is not None:
            self._httpx_client.close()
            self._httpx_client = None

    def __enter__(self) -> "SyncHttpTransport":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def request(
        self,
        *,
        url: str,
        method: str = "GET",
        headers: Mapping[str, str] | None = None,
        body: Any = None,
    ) -> tuple[int, str]:
        merged_headers = _merge_headers(self.config, headers)
        normalized_method = method.upper()
        try:
            import httpx
        except ImportError:
            return self._request_with_urllib(
                url=url,
                method=normalized_method,
                headers=merged_headers,
                body=body,
            )

        return self._request_with_httpx(
            url=url,
            method=normalized_method,
            headers=merged_headers,
            body=body,
        )

    def _request_with_urllib(
        self,
        *,
        url: str,
        method: str,
        headers: dict[str, str],
        body: Any,
    ) -> tuple[int, str]:
        for attempt in range(self.config.max_retries + 1):
            data: bytes | None = None
            if body is not None:
                if "content-type" not in {key.lower(): value for key, value in headers.items()}:
                    headers["content-type"] = "application/json"
                data = json.dumps(body).encode("utf-8")

            req = request.Request(url, method=method, headers=headers, data=data)
            try:
                with request.urlopen(req, timeout=self.config.timeout_seconds) as response:
                    return response.status, response.read().decode("utf-8")
            except error.HTTPError as exc:
                status_code = exc.code
                payload = exc.read().decode("utf-8")
                if not _should_retry(self.config, attempt=attempt, method=method, status_code=status_code):
                    return status_code, payload
            except error.URLError:
                if not _should_retry(self.config, attempt=attempt, method=method):
                    raise
            time.sleep(_retry_delay(self.config, attempt))

        raise RuntimeError("urllib retry loop exited without a response")

    def _request_with_httpx(
        self,
        *,
        url: str,
        method: str,
        headers: dict[str, str],
        body: Any,
    ) -> tuple[int, str]:
        client = self._get_httpx_client()
        for attempt in range(self.config.max_retries + 1):
            try:
                response = client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=body,
                )
            except Exception:
                if not _should_retry(self.config, attempt=attempt, method=method):
                    raise
            else:
                if not _should_retry(
                    self.config,
                    attempt=attempt,
                    method=method,
                    status_code=response.status_code,
                ):
                    return response.status_code, response.text
            time.sleep(_retry_delay(self.config, attempt))

        raise RuntimeError("httpx retry loop exited without a response")


class AsyncHttpTransport:
    def __init__(self, config: TransportConfig | None = None, sync_transport: SyncHttpTransport | None = None) -> None:
        self.config = config or TransportConfig()
        self._sync_transport = sync_transport or SyncHttpTransport(self.config)
        self._httpx_client: Any | None = None

    async def _get_httpx_client(self) -> Any:
        if self._httpx_client is None:
            import httpx

            self._httpx_client = httpx.AsyncClient(
                timeout=self.config.timeout_seconds,
                headers=self.config.default_headers,
            )
        return self._httpx_client

    async def close(self) -> None:
        if self._httpx_client is not None:
            await self._httpx_client.aclose()
            self._httpx_client = None

    async def __aenter__(self) -> "AsyncHttpTransport":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()

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

        client = await self._get_httpx_client()
        merged_headers = _merge_headers(self.config, headers)
        normalized_method = method.upper()
        for attempt in range(self.config.max_retries + 1):
            try:
                response = await client.request(
                    method=normalized_method,
                    url=url,
                    headers=merged_headers,
                    json=body,
                )
            except Exception:
                if not _should_retry(self.config, attempt=attempt, method=normalized_method):
                    raise
            else:
                if not _should_retry(
                    self.config,
                    attempt=attempt,
                    method=normalized_method,
                    status_code=response.status_code,
                ):
                    return response.status_code, response.text
            await asyncio.sleep(_retry_delay(self.config, attempt))

        raise RuntimeError("async httpx retry loop exited without a response")
