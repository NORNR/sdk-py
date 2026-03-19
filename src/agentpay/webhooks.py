from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import hmac
import json
import time
from typing import Any, Callable, Mapping


def _header(headers: Mapping[str, str] | None, name: str) -> str | None:
    lowered = {str(key).lower(): value for key, value in (headers or {}).items()}
    value = lowered.get(name.lower())
    return str(value) if value is not None else None


def sign_webhook_payload(*, secret: str, payload: str, timestamp: str) -> str:
    return hmac.new(str(secret).encode("utf-8"), f"{timestamp}.{payload}".encode("utf-8"), sha256).hexdigest()


def verify_webhook_signature(
    *,
    secret: str,
    payload: str,
    timestamp: str,
    signature: str,
    tolerance_seconds: int = 300,
    now: float | None = None,
) -> tuple[bool, str | None]:
    if not secret or not payload or not timestamp or not signature:
        return False, "Missing secret, payload, timestamp or signature"
    current_time = time.time() if now is None else now
    try:
        parsed_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if parsed_timestamp.tzinfo is None:
            parsed_timestamp = parsed_timestamp.replace(tzinfo=timezone.utc)
        age_seconds = abs(current_time - parsed_timestamp.timestamp())
    except ValueError:
        return False, "Timestamp is not a valid ISO-8601 string"
    if age_seconds > tolerance_seconds:
        return False, "Timestamp is outside the allowed tolerance window"
    expected = sign_webhook_payload(secret=secret, payload=payload, timestamp=timestamp)
    if not hmac.compare_digest(expected, str(signature)):
        return False, "Signature mismatch"
    return True, None


@dataclass(frozen=True)
class VerifiedWebhookRequest:
    event_id: str | None
    event_type: str | None
    delivery_id: str | None
    timestamp: str
    payload_text: str
    payload: dict[str, Any]
    headers: dict[str, str]


def verify_webhook_request(
    *,
    secret: str,
    payload: str | bytes | Mapping[str, Any],
    headers: Mapping[str, str],
    tolerance_seconds: int = 300,
) -> VerifiedWebhookRequest:
    if isinstance(payload, bytes):
        payload_text = payload.decode("utf-8")
    elif isinstance(payload, Mapping):
        payload_text = json.dumps(dict(payload))
    else:
        payload_text = str(payload)
    timestamp = _header(headers, "x-nornr-timestamp")
    signature = _header(headers, "x-nornr-signature")
    ok, reason = verify_webhook_signature(
        secret=secret,
        payload=payload_text,
        timestamp=timestamp or "",
        signature=signature or "",
        tolerance_seconds=tolerance_seconds,
    )
    if not ok:
        raise ValueError(reason or "Webhook verification failed")
    return VerifiedWebhookRequest(
        event_id=_header(headers, "x-nornr-event-id"),
        event_type=_header(headers, "x-nornr-event-type"),
        delivery_id=_header(headers, "x-nornr-delivery-id"),
        timestamp=timestamp or "",
        payload_text=payload_text,
        payload=json.loads(payload_text),
        headers={str(key): str(value) for key, value in headers.items()},
    )


def dispatch_webhook_event(
    request: VerifiedWebhookRequest,
    handlers: Mapping[str, Callable[[VerifiedWebhookRequest], Any]],
    *,
    default_handler: Callable[[VerifiedWebhookRequest], Any] | None = None,
) -> Any:
    handler = handlers.get(request.event_type or "")
    if handler:
        return handler(request)
    if default_handler:
        return default_handler(request)
    raise KeyError(f"No NORNR webhook handler registered for {request.event_type}")
