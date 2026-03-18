from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASE_URL = os.environ.get("NORNR_BASE_URL", "https://nornr.com").rstrip("/")


@dataclass(frozen=True)
class LoginProfile:
    api_key: str
    base_url: str


def _normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def default_auth_path() -> Path:
    override = os.environ.get("NORNR_AUTH_PATH")
    if override:
        return Path(override)
    return Path.home() / ".config" / "nornr" / "auth.json"


def save_login(api_key: str, *, base_url: str = DEFAULT_BASE_URL, path: Path | None = None) -> Path:
    auth_path = path or default_auth_path()
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "apiKey": api_key,
        "baseUrl": _normalize_base_url(base_url),
    }
    auth_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return auth_path


def load_login(*, base_url: str | None = None, path: Path | None = None) -> LoginProfile | None:
    auth_path = path or default_auth_path()
    if not auth_path.exists():
        return None
    payload = json.loads(auth_path.read_text(encoding="utf-8"))
    stored_base_url = _normalize_base_url(str(payload.get("baseUrl") or ""))
    requested_base_url = _normalize_base_url(base_url) if base_url else stored_base_url
    if requested_base_url and stored_base_url and requested_base_url != stored_base_url:
        return None
    api_key = payload.get("apiKey")
    if not api_key:
        return None
    return LoginProfile(api_key=str(api_key), base_url=stored_base_url or requested_base_url)


def clear_login(path: Path | None = None) -> None:
    auth_path = path or default_auth_path()
    if auth_path.exists():
        auth_path.unlink()


def login_url(base_url: str = DEFAULT_BASE_URL) -> str:
    return f"{_normalize_base_url(base_url)}/app?source=nornr-cli-login"
