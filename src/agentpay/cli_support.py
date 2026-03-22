from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .auth import DEFAULT_BASE_URL, load_login
from .client import AgentPayClient, AuthenticationError, Wallet


def resolve_base_url(base_url: str | None) -> str:
    env_base_url = os.getenv("NORNR_BASE_URL")
    if base_url and base_url != DEFAULT_BASE_URL:
        return base_url
    return env_base_url or base_url or DEFAULT_BASE_URL


def resolve_api_key(api_key: str | None, base_url: str, auth_path: str | None) -> str:
    if api_key:
        return api_key
    env_api_key = os.getenv("NORNR_API_KEY")
    if env_api_key:
        return env_api_key
    resolved_auth_path = auth_path or os.getenv("NORNR_AUTH_PATH")
    profile = load_login(base_url=base_url, path=Path(resolved_auth_path) if resolved_auth_path else None)
    if not profile:
        raise AuthenticationError("Missing NORNR api key. Run `nornr login` first or pass --api-key.")
    return profile.api_key


def print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def resolve_wallet(api_key: str | None, base_url: str, auth_path: str | None, agent_id: str | None = None) -> Wallet:
    resolved_base_url = resolve_base_url(base_url)
    resolved_key = resolve_api_key(api_key, resolved_base_url, auth_path)
    resolved_agent_id = agent_id or os.getenv("NORNR_AGENT_ID")
    return Wallet.connect(api_key=resolved_key, base_url=resolved_base_url, agent_id=resolved_agent_id)


def resolve_client(api_key: str | None, base_url: str, auth_path: str | None) -> AgentPayClient:
    resolved_base_url = resolve_base_url(base_url)
    resolved_key = resolve_api_key(api_key, resolved_base_url, auth_path)
    return AgentPayClient(base_url=resolved_base_url, api_key=resolved_key)


def current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def previous_month(month: str) -> str:
    year, month_number = [int(part) for part in month.split("-", 1)]
    month_number -= 1
    if month_number < 1:
        year -= 1
        month_number = 12
    return f"{year:04d}-{month_number:02d}"


def load_json_payload(path: str) -> dict[str, object]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit("Expected a JSON object at --path.")
    return raw


def resolve_counterparty_profile(client: AgentPayClient, query: str) -> dict[str, object]:
    query_norm = query.strip().lower()
    profiles = client.list_counterparty_profiles()
    for profile in profiles:
        if str(profile.get("id", "")).strip().lower() == query_norm:
            return profile
    for profile in profiles:
        names = [str(profile.get("name", "")), str(profile.get("destination", ""))]
        names.extend(str(item) for item in profile.get("aliases", []) or [])
        if query_norm in [name.strip().lower() for name in names if name]:
            return profile
    raise SystemExit(f"Counterparty profile not found for {query!r}.")
