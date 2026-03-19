from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping
from urllib.parse import urlparse

from .client import DecisionRecord, Wallet

CHECKOUT_TERMS = (
    "buy",
    "checkout",
    "purchase",
    "pay now",
    "place order",
    "confirm payment",
    "subscribe",
    "upgrade",
)
CARD_FIELD_TERMS = (
    "card",
    "credit",
    "cvv",
    "security code",
    "expiry",
    "expiration",
)


def _normalize(value: str | None) -> str:
    return (value or "").strip().lower()


def _domain(url: str) -> str:
    hostname = urlparse(url).hostname or url
    return hostname.lower().removeprefix("www.")


def _counterparty_for(url: str) -> str:
    host = _domain(url)
    parts = host.split(".")
    return parts[-2] if len(parts) >= 2 else host


@dataclass(frozen=True)
class CheckoutSignal:
    """Description of a risky browser action before money moves."""

    url: str
    action: str
    reason: str
    domain: str
    counterparty: str
    path: str
    amount_usd: float | None = None
    currency: str | None = None
    merchant_label: str | None = None
    matched_terms: tuple[str, ...] = field(default_factory=tuple)

    @property
    def purpose(self) -> str:
        return f"Browser checkout guard for {self.domain}"


@dataclass(frozen=True)
class BrowserGuardResult:
    signal: CheckoutSignal | None
    decision: DecisionRecord | None

    @property
    def allowed(self) -> bool:
        return not self.signal or not self.blocked

    @property
    def blocked(self) -> bool:
        return bool(self.decision and self.decision.status not in {"approved", "settled"})

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "blocked": self.blocked,
            "signal": {
                "domain": self.signal.domain,
                "path": self.signal.path,
                "action": self.signal.action,
                "amountUsd": self.signal.amount_usd,
                "currency": self.signal.currency,
                "merchantLabel": self.signal.merchant_label,
                "matchedTerms": list(self.signal.matched_terms),
            }
            if self.signal
            else None,
            "decision": self.decision.to_summary_dict() if self.decision else None,
        }


class BrowserCheckoutGuard:
    """Framework-agnostic guard for browser-based purchase flows."""

    def __init__(
        self,
        wallet: Wallet,
        *,
        allow_domains: list[str] | None = None,
        blocked_domains: list[str] | None = None,
        checkout_terms: tuple[str, ...] = CHECKOUT_TERMS,
        card_field_terms: tuple[str, ...] = CARD_FIELD_TERMS,
    ) -> None:
        self.wallet = wallet
        self.allow_domains = {_normalize(item) for item in (allow_domains or [])}
        self.blocked_domains = {_normalize(item) for item in (blocked_domains or [])}
        self.checkout_terms = tuple(_normalize(item) for item in checkout_terms)
        self.card_field_terms = tuple(_normalize(item) for item in card_field_terms)

    def inspect_click(
        self,
        *,
        url: str,
        selector: str | None = None,
        text: str | None = None,
        amount: float | None = None,
        currency: str | None = None,
        merchant_label: str | None = None,
    ) -> CheckoutSignal | None:
        domain = _domain(url)
        parsed = urlparse(url)
        normalized_text = " ".join(filter(None, [_normalize(text), _normalize(selector)]))
        matched_terms = tuple(term for term in self.checkout_terms if term in normalized_text)
        if domain in self.blocked_domains and not matched_terms:
            matched_terms = ("blocked-domain",)
        if domain not in self.allow_domains and matched_terms:
            return CheckoutSignal(
                url=url,
                action="click",
                reason=f"Browser agent is about to trigger a purchase-like action on {domain}.",
                domain=domain,
                counterparty=_counterparty_for(url),
                path=parsed.path or "/",
                amount_usd=amount,
                currency=currency,
                merchant_label=merchant_label,
                matched_terms=matched_terms,
            )
        if domain in self.blocked_domains:
            return CheckoutSignal(
                url=url,
                action="click",
                reason=f"Domain {domain} is explicitly configured for NORNR checkout review.",
                domain=domain,
                counterparty=_counterparty_for(url),
                path=parsed.path or "/",
                amount_usd=amount,
                currency=currency,
                merchant_label=merchant_label,
                matched_terms=matched_terms,
            )
        return None

    def inspect_fill(
        self,
        *,
        url: str,
        field_name: str | None = None,
        field_label: str | None = None,
        input_type: str | None = None,
        amount: float | None = None,
        currency: str | None = None,
        merchant_label: str | None = None,
    ) -> CheckoutSignal | None:
        domain = _domain(url)
        parsed = urlparse(url)
        normalized = " ".join(
            filter(None, [_normalize(field_name), _normalize(field_label), _normalize(input_type)])
        )
        matched_terms = tuple(term for term in self.card_field_terms if term in normalized)
        if matched_terms:
            return CheckoutSignal(
                url=url,
                action="fill",
                reason=f"Browser agent is about to fill payment details on {domain}.",
                domain=domain,
                counterparty=_counterparty_for(url),
                path=parsed.path or "/",
                amount_usd=amount,
                currency=currency,
                merchant_label=merchant_label,
                matched_terms=matched_terms,
            )
        return None

    def guard_signal(
        self,
        signal: CheckoutSignal | None,
        *,
        amount: float,
        purpose: str | None = None,
        budget_tags: dict[str, str] | None = None,
        business_context: Mapping[str, Any] | None = None,
        dry_run: bool = True,
    ) -> DecisionRecord | None:
        if not signal:
            return None
        merged_context = {
            "surface": "browser",
            "domain": signal.domain,
            "path": signal.path,
            "action": signal.action,
            "reason": signal.reason,
            "amountUsd": signal.amount_usd,
            "currency": signal.currency,
            "merchantLabel": signal.merchant_label,
            "matchedTerms": list(signal.matched_terms),
            **dict(business_context or {}),
        }
        return self.wallet.pay(
            amount=amount,
            to=signal.domain,
            counterparty=signal.counterparty,
            purpose=purpose or signal.purpose,
            budget_tags=budget_tags,
            dry_run=dry_run,
            business_context=merged_context,
            replay_context={"source": "browser.guard", "url": signal.url},
        )

    def evaluate_action(
        self,
        *,
        action: str,
        url: str,
        amount: float,
        selector: str | None = None,
        text: str | None = None,
        field_name: str | None = None,
        field_label: str | None = None,
        input_type: str | None = None,
        currency: str | None = None,
        merchant_label: str | None = None,
        purpose: str | None = None,
        budget_tags: dict[str, str] | None = None,
        business_context: Mapping[str, Any] | None = None,
        dry_run: bool = True,
    ) -> BrowserGuardResult:
        if _normalize(action) == "fill":
            signal = self.inspect_fill(
                url=url,
                field_name=field_name,
                field_label=field_label,
                input_type=input_type,
                amount=amount,
                currency=currency,
                merchant_label=merchant_label,
            )
        else:
            signal = self.inspect_click(
                url=url,
                selector=selector,
                text=text,
                amount=amount,
                currency=currency,
                merchant_label=merchant_label,
            )
        decision = self.guard_signal(
            signal,
            amount=amount,
            purpose=purpose,
            budget_tags=budget_tags,
            business_context=business_context,
            dry_run=dry_run,
        )
        return BrowserGuardResult(signal=signal, decision=decision)

    def guard_click(
        self,
        *,
        url: str,
        amount: float,
        selector: str | None = None,
        text: str | None = None,
        currency: str | None = None,
        merchant_label: str | None = None,
        purpose: str | None = None,
        budget_tags: dict[str, str] | None = None,
        business_context: Mapping[str, Any] | None = None,
        dry_run: bool = True,
    ) -> DecisionRecord | None:
        return self.evaluate_action(
            action="click",
            url=url,
            amount=amount,
            selector=selector,
            text=text,
            currency=currency,
            merchant_label=merchant_label,
            purpose=purpose,
            budget_tags=budget_tags,
            business_context=business_context,
            dry_run=dry_run,
        ).decision

    def guard_form_fill(
        self,
        *,
        url: str,
        amount: float,
        field_name: str | None = None,
        field_label: str | None = None,
        input_type: str | None = None,
        currency: str | None = None,
        merchant_label: str | None = None,
        purpose: str | None = None,
        budget_tags: dict[str, str] | None = None,
        business_context: Mapping[str, Any] | None = None,
        dry_run: bool = True,
    ) -> DecisionRecord | None:
        return self.evaluate_action(
            action="fill",
            url=url,
            amount=amount,
            field_name=field_name,
            field_label=field_label,
            input_type=input_type,
            currency=currency,
            merchant_label=merchant_label,
            purpose=purpose,
            budget_tags=budget_tags,
            business_context=business_context,
            dry_run=dry_run,
        ).decision

    def guard_callback(
        self,
        *,
        action: str,
        url: str,
        amount: float,
        callback: Callable[[], Any],
        selector: str | None = None,
        text: str | None = None,
        field_name: str | None = None,
        field_label: str | None = None,
        input_type: str | None = None,
        currency: str | None = None,
        merchant_label: str | None = None,
        purpose: str | None = None,
        budget_tags: dict[str, str] | None = None,
        business_context: Mapping[str, Any] | None = None,
        dry_run: bool = False,
    ) -> BrowserGuardResult:
        result = self.evaluate_action(
            action=action,
            url=url,
            amount=amount,
            selector=selector,
            text=text,
            field_name=field_name,
            field_label=field_label,
            input_type=input_type,
            currency=currency,
            merchant_label=merchant_label,
            purpose=purpose,
            budget_tags=budget_tags,
            business_context=business_context,
            dry_run=dry_run,
        )
        if result.signal and result.blocked:
            return result
        callback()
        return result

    async def guard_async_callback(
        self,
        *,
        action: str,
        url: str,
        amount: float,
        callback: Callable[[], Any | Awaitable[Any]],
        selector: str | None = None,
        text: str | None = None,
        field_name: str | None = None,
        field_label: str | None = None,
        input_type: str | None = None,
        currency: str | None = None,
        merchant_label: str | None = None,
        purpose: str | None = None,
        budget_tags: dict[str, str] | None = None,
        business_context: Mapping[str, Any] | None = None,
        dry_run: bool = False,
    ) -> BrowserGuardResult:
        result = self.evaluate_action(
            action=action,
            url=url,
            amount=amount,
            selector=selector,
            text=text,
            field_name=field_name,
            field_label=field_label,
            input_type=input_type,
            currency=currency,
            merchant_label=merchant_label,
            purpose=purpose,
            budget_tags=budget_tags,
            business_context=business_context,
            dry_run=dry_run,
        )
        if result.signal and result.blocked:
            return result
        maybe_awaitable = callback()
        if inspect.isawaitable(maybe_awaitable):
            await maybe_awaitable
        return result

    def guard_playwright_click(
        self,
        page: Any,
        *,
        url: str,
        selector: str,
        amount: float,
        text: str | None = None,
        currency: str | None = None,
        merchant_label: str | None = None,
        purpose: str | None = None,
        budget_tags: dict[str, str] | None = None,
        business_context: Mapping[str, Any] | None = None,
        dry_run: bool = False,
    ) -> BrowserGuardResult:
        return self.guard_callback(
            action="click",
            url=url,
            amount=amount,
            selector=selector,
            text=text,
            currency=currency,
            merchant_label=merchant_label,
            purpose=purpose,
            budget_tags=budget_tags,
            business_context=business_context,
            dry_run=dry_run,
            callback=lambda: page.click(selector),
        )

    def guard_playwright_fill(
        self,
        page: Any,
        *,
        url: str,
        selector: str,
        value: str,
        amount: float,
        field_name: str | None = None,
        field_label: str | None = None,
        input_type: str | None = None,
        currency: str | None = None,
        merchant_label: str | None = None,
        purpose: str | None = None,
        budget_tags: dict[str, str] | None = None,
        business_context: Mapping[str, Any] | None = None,
        dry_run: bool = False,
    ) -> BrowserGuardResult:
        return self.guard_callback(
            action="fill",
            url=url,
            amount=amount,
            field_name=field_name or selector,
            field_label=field_label,
            input_type=input_type,
            currency=currency,
            merchant_label=merchant_label,
            purpose=purpose,
            budget_tags=budget_tags,
            business_context=business_context,
            dry_run=dry_run,
            callback=lambda: page.fill(selector, value),
        )

    async def guard_playwright_click_async(
        self,
        page: Any,
        *,
        url: str,
        selector: str,
        amount: float,
        text: str | None = None,
        currency: str | None = None,
        merchant_label: str | None = None,
        purpose: str | None = None,
        budget_tags: dict[str, str] | None = None,
        business_context: Mapping[str, Any] | None = None,
        dry_run: bool = False,
    ) -> BrowserGuardResult:
        return await self.guard_async_callback(
            action="click",
            url=url,
            amount=amount,
            selector=selector,
            text=text,
            currency=currency,
            merchant_label=merchant_label,
            purpose=purpose,
            budget_tags=budget_tags,
            business_context=business_context,
            dry_run=dry_run,
            callback=lambda: page.click(selector),
        )

    async def guard_playwright_fill_async(
        self,
        page: Any,
        *,
        url: str,
        selector: str,
        value: str,
        amount: float,
        field_name: str | None = None,
        field_label: str | None = None,
        input_type: str | None = None,
        currency: str | None = None,
        merchant_label: str | None = None,
        purpose: str | None = None,
        budget_tags: dict[str, str] | None = None,
        business_context: Mapping[str, Any] | None = None,
        dry_run: bool = False,
    ) -> BrowserGuardResult:
        return await self.guard_async_callback(
            action="fill",
            url=url,
            amount=amount,
            field_name=field_name or selector,
            field_label=field_label,
            input_type=input_type,
            currency=currency,
            merchant_label=merchant_label,
            purpose=purpose,
            budget_tags=budget_tags,
            business_context=business_context,
            dry_run=dry_run,
            callback=lambda: page.fill(selector, value),
        )


def guard_browser_action(
    wallet: Wallet,
    *,
    url: str,
    amount: float,
    action: str,
    selector: str | None = None,
    text: str | None = None,
    field_name: str | None = None,
    field_label: str | None = None,
    input_type: str | None = None,
    currency: str | None = None,
    merchant_label: str | None = None,
    purpose: str | None = None,
    budget_tags: dict[str, str] | None = None,
    business_context: Mapping[str, Any] | None = None,
    dry_run: bool = True,
) -> DecisionRecord | None:
    """Convenience wrapper for browser agents without building a guard instance."""

    guard = BrowserCheckoutGuard(wallet)
    if _normalize(action) == "fill":
        return guard.guard_form_fill(
            url=url,
            amount=amount,
            field_name=field_name,
            field_label=field_label,
            input_type=input_type,
            currency=currency,
            merchant_label=merchant_label,
            purpose=purpose,
            budget_tags=budget_tags,
            business_context=business_context,
            dry_run=dry_run,
        )
    return guard.guard_click(
        url=url,
        amount=amount,
        selector=selector,
        text=text,
        currency=currency,
        merchant_label=merchant_label,
        purpose=purpose,
        budget_tags=budget_tags,
        business_context=business_context,
        dry_run=dry_run,
    )
