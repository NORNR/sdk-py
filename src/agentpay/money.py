from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Mapping, TypeAlias

AmountLike: TypeAlias = Decimal | int | float | str

USD_QUANTUM = Decimal("0.01")
ZERO_USD = Decimal("0.00")


def usd_decimal(value: AmountLike | None, *, default: Decimal = ZERO_USD) -> Decimal:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value.quantize(USD_QUANTUM, rounding=ROUND_HALF_UP)
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return default
        try:
            return Decimal(normalized).quantize(USD_QUANTUM, rounding=ROUND_HALF_UP)
        except InvalidOperation as exc:
            raise ValueError(f"Invalid USD amount: {value}") from exc
    return Decimal(str(value)).quantize(USD_QUANTUM, rounding=ROUND_HALF_UP)


def usd_float(value: AmountLike | None, *, default: Decimal = ZERO_USD) -> float:
    return float(usd_decimal(value, default=default))


def usd_text(value: AmountLike | None, *, default: Decimal = ZERO_USD) -> str:
    return f"{usd_decimal(value, default=default):.2f}"


def usd_from_mapping(payload: Mapping[str, Any] | None, *keys: str) -> Decimal:
    if not payload:
        return ZERO_USD
    for key in keys:
        if payload.get(key) is not None:
            return usd_decimal(payload.get(key))
    return ZERO_USD
