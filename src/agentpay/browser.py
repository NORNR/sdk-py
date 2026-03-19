from __future__ import annotations

import inspect
import re
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
AMOUNT_RE = re.compile(r"(?P<currency>\$|usd|eur|sek)?\s*(?P<amount>\d{1,6}(?:[.,]\d{2})?)", re.IGNORECASE)
ACTION_HINTS: dict[str, tuple[str, ...]] = {
    "checkout": ("checkout", "place order", "confirm payment", "pay now"),
    "subscription_upgrade": ("subscribe", "upgrade", "start plan", "upgrade plan"),
    "vendor_purchase": ("buy", "purchase", "order"),
    "card_entry": ("card", "credit", "cvv", "security code"),
    "invoice_payment": ("invoice", "pay invoice", "settle invoice"),
}
STRICT_AMOUNT_TAXONOMIES = {"checkout", "subscription_upgrade", "vendor_purchase", "invoice_payment"}


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
    amount_source: str | None = None
    amount_confidence: float | None = None
    currency: str | None = None
    merchant_label: str | None = None
    action_taxonomy: str | None = None
    destination_summary: str | None = None
    cart_summary: str | None = None
    product_summary: str | None = None
    page_title: str | None = None
    dom_excerpt: str | None = None
    screenshot_path: str | None = None
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
                "amountSource": self.signal.amount_source,
                "amountConfidence": self.signal.amount_confidence,
                "currency": self.signal.currency,
                "merchantLabel": self.signal.merchant_label,
                "actionTaxonomy": self.signal.action_taxonomy,
                "destinationSummary": self.signal.destination_summary,
                "cartSummary": self.signal.cart_summary,
                "productSummary": self.signal.product_summary,
                "pageTitle": self.signal.page_title,
                "domExcerpt": self.signal.dom_excerpt,
                "screenshotPath": self.signal.screenshot_path,
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

    def _extract_amount_candidate(
        self,
        value: str | None,
        *,
        source: str,
        confidence: float,
        preferred_terms: tuple[str, ...] = (),
    ) -> tuple[float, str, float] | None:
        if not value:
            return None
        normalized = _normalize(value)
        match = AMOUNT_RE.search(str(value))
        if not match:
            return None
        currency_marker = match.group("currency")
        context_window = str(value)[max(0, match.start() - 12) : min(len(str(value)), match.end() + 12)].lower()
        if not currency_marker and any(marker in context_window for marker in ("invoice", "inv-", " id ", " ref ", "ticket")):
            return None
        raw_amount = match.group("amount").replace(",", ".")
        try:
            amount = float(raw_amount)
        except ValueError:
            return None
        adjusted_confidence = confidence
        if preferred_terms and any(term in normalized for term in preferred_terms):
            adjusted_confidence = min(1.0, confidence + 0.1)
        return amount, source, adjusted_confidence

    def classify_action(
        self,
        *,
        url: str,
        text: str | None = None,
        selector: str | None = None,
        field_name: str | None = None,
        field_label: str | None = None,
        input_type: str | None = None,
    ) -> str:
        normalized = " ".join(
            filter(
                None,
                [
                    _normalize(text),
                    _normalize(selector),
                    _normalize(field_name),
                    _normalize(field_label),
                    _normalize(input_type),
                    _normalize(urlparse(url).path),
                ],
            )
        )
        for taxonomy, hints in ACTION_HINTS.items():
            if any(hint in normalized for hint in hints):
                return taxonomy
        return "browser_action"

    def extract_amount_hint(
        self,
        *,
        text: str | None = None,
        dom_excerpt: str | None = None,
        page_title: str | None = None,
        cart_summary: str | None = None,
        amount_text: str | None = None,
        currency: str | None = None,
    ) -> tuple[float | None, str | None, float]:
        candidates = [
            self._extract_amount_candidate(amount_text, source="amount-selector", confidence=0.98),
            self._extract_amount_candidate(
                cart_summary,
                source="cart-summary",
                confidence=0.9,
                preferred_terms=("total", "order summary", "due today", "subtotal"),
            ),
            self._extract_amount_candidate(
                dom_excerpt,
                source="dom-excerpt",
                confidence=0.72,
                preferred_terms=("total", "order summary", "due today", "subtotal"),
            ),
            self._extract_amount_candidate(text, source="button-text", confidence=0.55),
            self._extract_amount_candidate(page_title, source="page-title", confidence=0.35),
        ]
        for candidate in candidates:
            if candidate is not None:
                return candidate
        _ = currency
        return None, None, 0.0

    def resolve_amount(
        self,
        *,
        amount: float | None,
        action_taxonomy: str | None = None,
        text: str | None = None,
        dom_excerpt: str | None = None,
        page_title: str | None = None,
        cart_summary: str | None = None,
        amount_text: str | None = None,
        currency: str | None = None,
    ) -> tuple[float, str, float]:
        if amount is not None:
            return amount, "explicit", 1.0
        extracted, source, confidence = self.extract_amount_hint(
            text=text,
            dom_excerpt=dom_excerpt,
            page_title=page_title,
            cart_summary=cart_summary,
            amount_text=amount_text,
            currency=currency,
        )
        if extracted is None:
            raise ValueError("Browser guard could not infer an amount; pass amount explicitly or capture richer page evidence.")
        if action_taxonomy in STRICT_AMOUNT_TAXONOMIES and confidence < 0.8:
            raise ValueError(
                f"Browser guard inferred amount with low confidence ({confidence:.2f}) for high-risk `{action_taxonomy}` action. "
                "Pass amount explicitly or provide amount/cart selectors."
            )
        return extracted, source or "inferred", confidence

    def inspect_click(
        self,
        *,
        url: str,
        selector: str | None = None,
        text: str | None = None,
        amount: float | None = None,
        currency: str | None = None,
        merchant_label: str | None = None,
        cart_summary: str | None = None,
        amount_source: str | None = None,
        amount_confidence: float | None = None,
        page_title: str | None = None,
        dom_excerpt: str | None = None,
        screenshot_path: str | None = None,
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
                amount_source=amount_source,
                amount_confidence=amount_confidence,
                currency=currency,
                merchant_label=merchant_label,
                action_taxonomy=self.classify_action(url=url, text=text, selector=selector),
                destination_summary=f"{domain}{parsed.path or '/'}",
                cart_summary=(cart_summary or dom_excerpt or text or "")[:160] or None,
                product_summary=(text or merchant_label or page_title),
                page_title=page_title,
                dom_excerpt=dom_excerpt,
                screenshot_path=screenshot_path,
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
                amount_source=amount_source,
                amount_confidence=amount_confidence,
                currency=currency,
                merchant_label=merchant_label,
                action_taxonomy=self.classify_action(url=url, text=text, selector=selector),
                destination_summary=f"{domain}{parsed.path or '/'}",
                cart_summary=(cart_summary or dom_excerpt or text or "")[:160] or None,
                product_summary=(text or merchant_label or page_title),
                page_title=page_title,
                dom_excerpt=dom_excerpt,
                screenshot_path=screenshot_path,
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
        cart_summary: str | None = None,
        amount_source: str | None = None,
        amount_confidence: float | None = None,
        page_title: str | None = None,
        dom_excerpt: str | None = None,
        screenshot_path: str | None = None,
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
                amount_source=amount_source,
                amount_confidence=amount_confidence,
                currency=currency,
                merchant_label=merchant_label,
                action_taxonomy=self.classify_action(
                    url=url,
                    field_name=field_name,
                    field_label=field_label,
                    input_type=input_type,
                ),
                destination_summary=f"{domain}{parsed.path or '/'}",
                cart_summary=(cart_summary or dom_excerpt or "")[:160] or None,
                product_summary=(merchant_label or page_title or field_label or field_name),
                page_title=page_title,
                dom_excerpt=dom_excerpt,
                screenshot_path=screenshot_path,
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
            "actionTaxonomy": signal.action_taxonomy,
            "destinationSummary": signal.destination_summary,
            "cartSummary": signal.cart_summary,
            "productSummary": signal.product_summary,
            "pageTitle": signal.page_title,
            "domExcerpt": signal.dom_excerpt,
            "screenshotPath": signal.screenshot_path,
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
        amount: float | None,
        selector: str | None = None,
        text: str | None = None,
        field_name: str | None = None,
        field_label: str | None = None,
        input_type: str | None = None,
        currency: str | None = None,
        merchant_label: str | None = None,
        page_title: str | None = None,
        dom_excerpt: str | None = None,
        screenshot_path: str | None = None,
        cart_summary: str | None = None,
        amount_text: str | None = None,
        purpose: str | None = None,
        budget_tags: dict[str, str] | None = None,
        business_context: Mapping[str, Any] | None = None,
        dry_run: bool = True,
    ) -> BrowserGuardResult:
        action_taxonomy = self.classify_action(
            url=url,
            text=text,
            selector=selector,
            field_name=field_name,
            field_label=field_label,
            input_type=input_type,
        )
        resolved_amount, amount_source, amount_confidence = self.resolve_amount(
            amount=amount,
            action_taxonomy=action_taxonomy,
            text=text,
            dom_excerpt=dom_excerpt,
            page_title=page_title,
            cart_summary=cart_summary,
            amount_text=amount_text,
            currency=currency,
        )
        if _normalize(action) == "fill":
            signal = self.inspect_fill(
                url=url,
                field_name=field_name,
                field_label=field_label,
                input_type=input_type,
                amount=resolved_amount,
                currency=currency,
                merchant_label=merchant_label,
                cart_summary=cart_summary,
                amount_source=amount_source,
                amount_confidence=amount_confidence,
                page_title=page_title,
                dom_excerpt=dom_excerpt,
                screenshot_path=screenshot_path,
            )
        else:
            signal = self.inspect_click(
                url=url,
                selector=selector,
                text=text,
                amount=resolved_amount,
                currency=currency,
                merchant_label=merchant_label,
                cart_summary=cart_summary,
                amount_source=amount_source,
                amount_confidence=amount_confidence,
                page_title=page_title,
                dom_excerpt=dom_excerpt,
                screenshot_path=screenshot_path,
            )
        decision = self.guard_signal(
            signal,
            amount=resolved_amount,
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
        amount: float | None,
        selector: str | None = None,
        text: str | None = None,
        currency: str | None = None,
        merchant_label: str | None = None,
        page_title: str | None = None,
        dom_excerpt: str | None = None,
        screenshot_path: str | None = None,
        cart_summary: str | None = None,
        amount_text: str | None = None,
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
            page_title=page_title,
            dom_excerpt=dom_excerpt,
            screenshot_path=screenshot_path,
            cart_summary=cart_summary,
            amount_text=amount_text,
            purpose=purpose,
            budget_tags=budget_tags,
            business_context=business_context,
            dry_run=dry_run,
        ).decision

    def guard_form_fill(
        self,
        *,
        url: str,
        amount: float | None,
        field_name: str | None = None,
        field_label: str | None = None,
        input_type: str | None = None,
        currency: str | None = None,
        merchant_label: str | None = None,
        page_title: str | None = None,
        dom_excerpt: str | None = None,
        screenshot_path: str | None = None,
        cart_summary: str | None = None,
        amount_text: str | None = None,
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
            page_title=page_title,
            dom_excerpt=dom_excerpt,
            screenshot_path=screenshot_path,
            cart_summary=cart_summary,
            amount_text=amount_text,
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
        amount: float | None,
        callback: Callable[[], Any],
        selector: str | None = None,
        text: str | None = None,
        field_name: str | None = None,
        field_label: str | None = None,
        input_type: str | None = None,
        currency: str | None = None,
        merchant_label: str | None = None,
        page_title: str | None = None,
        dom_excerpt: str | None = None,
        screenshot_path: str | None = None,
        cart_summary: str | None = None,
        amount_text: str | None = None,
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
            page_title=page_title,
            dom_excerpt=dom_excerpt,
            screenshot_path=screenshot_path,
            cart_summary=cart_summary,
            amount_text=amount_text,
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
        amount: float | None,
        callback: Callable[[], Any | Awaitable[Any]],
        selector: str | None = None,
        text: str | None = None,
        field_name: str | None = None,
        field_label: str | None = None,
        input_type: str | None = None,
        currency: str | None = None,
        merchant_label: str | None = None,
        page_title: str | None = None,
        dom_excerpt: str | None = None,
        screenshot_path: str | None = None,
        cart_summary: str | None = None,
        amount_text: str | None = None,
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
            page_title=page_title,
            dom_excerpt=dom_excerpt,
            screenshot_path=screenshot_path,
            cart_summary=cart_summary,
            amount_text=amount_text,
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
        amount: float | None,
        text: str | None = None,
        currency: str | None = None,
        merchant_label: str | None = None,
        purpose: str | None = None,
        budget_tags: dict[str, str] | None = None,
        business_context: Mapping[str, Any] | None = None,
        capture_evidence: bool = False,
        screenshot_path: str | None = None,
        amount_selector: str | None = None,
        cart_selector: str | None = None,
        merchant_selector: str | None = None,
        dry_run: bool = False,
    ) -> BrowserGuardResult:
        evidence = (
            build_playwright_evidence(
                page,
                screenshot_path=screenshot_path,
                amount_selector=amount_selector,
                cart_selector=cart_selector,
                merchant_selector=merchant_selector,
            )
            if capture_evidence
            else {}
        )
        return self.guard_callback(
            action="click",
            url=url,
            amount=amount,
            selector=selector,
            text=text,
            currency=currency,
            merchant_label=merchant_label or evidence.get("merchantLabel"),
            page_title=evidence.get("pageTitle"),
            dom_excerpt=evidence.get("domExcerpt"),
            screenshot_path=evidence.get("screenshotPath"),
            cart_summary=evidence.get("cartSummary"),
            amount_text=evidence.get("amountText"),
            purpose=purpose,
            budget_tags=budget_tags,
            business_context={**evidence, **dict(business_context or {})},
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
        amount: float | None,
        field_name: str | None = None,
        field_label: str | None = None,
        input_type: str | None = None,
        currency: str | None = None,
        merchant_label: str | None = None,
        purpose: str | None = None,
        budget_tags: dict[str, str] | None = None,
        business_context: Mapping[str, Any] | None = None,
        capture_evidence: bool = False,
        screenshot_path: str | None = None,
        amount_selector: str | None = None,
        cart_selector: str | None = None,
        merchant_selector: str | None = None,
        dry_run: bool = False,
    ) -> BrowserGuardResult:
        evidence = (
            build_playwright_evidence(
                page,
                screenshot_path=screenshot_path,
                amount_selector=amount_selector,
                cart_selector=cart_selector,
                merchant_selector=merchant_selector,
            )
            if capture_evidence
            else {}
        )
        return self.guard_callback(
            action="fill",
            url=url,
            amount=amount,
            field_name=field_name or selector,
            field_label=field_label,
            input_type=input_type,
            currency=currency,
            merchant_label=merchant_label or evidence.get("merchantLabel"),
            page_title=evidence.get("pageTitle"),
            dom_excerpt=evidence.get("domExcerpt"),
            screenshot_path=evidence.get("screenshotPath"),
            cart_summary=evidence.get("cartSummary"),
            amount_text=evidence.get("amountText"),
            purpose=purpose,
            budget_tags=budget_tags,
            business_context={**evidence, **dict(business_context or {})},
            dry_run=dry_run,
            callback=lambda: page.fill(selector, value),
        )

    async def guard_playwright_click_async(
        self,
        page: Any,
        *,
        url: str,
        selector: str,
        amount: float | None,
        text: str | None = None,
        currency: str | None = None,
        merchant_label: str | None = None,
        purpose: str | None = None,
        budget_tags: dict[str, str] | None = None,
        business_context: Mapping[str, Any] | None = None,
        capture_evidence: bool = False,
        screenshot_path: str | None = None,
        amount_selector: str | None = None,
        cart_selector: str | None = None,
        merchant_selector: str | None = None,
        dry_run: bool = False,
    ) -> BrowserGuardResult:
        evidence = (
            await build_playwright_evidence_async(
                page,
                screenshot_path=screenshot_path,
                amount_selector=amount_selector,
                cart_selector=cart_selector,
                merchant_selector=merchant_selector,
            )
            if capture_evidence
            else {}
        )
        return await self.guard_async_callback(
            action="click",
            url=url,
            amount=amount,
            selector=selector,
            text=text,
            currency=currency,
            merchant_label=merchant_label or evidence.get("merchantLabel"),
            page_title=evidence.get("pageTitle"),
            dom_excerpt=evidence.get("domExcerpt"),
            screenshot_path=evidence.get("screenshotPath"),
            cart_summary=evidence.get("cartSummary"),
            amount_text=evidence.get("amountText"),
            purpose=purpose,
            budget_tags=budget_tags,
            business_context={**evidence, **dict(business_context or {})},
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
        amount: float | None,
        field_name: str | None = None,
        field_label: str | None = None,
        input_type: str | None = None,
        currency: str | None = None,
        merchant_label: str | None = None,
        purpose: str | None = None,
        budget_tags: dict[str, str] | None = None,
        business_context: Mapping[str, Any] | None = None,
        capture_evidence: bool = False,
        screenshot_path: str | None = None,
        amount_selector: str | None = None,
        cart_selector: str | None = None,
        merchant_selector: str | None = None,
        dry_run: bool = False,
    ) -> BrowserGuardResult:
        evidence = (
            await build_playwright_evidence_async(
                page,
                screenshot_path=screenshot_path,
                amount_selector=amount_selector,
                cart_selector=cart_selector,
                merchant_selector=merchant_selector,
            )
            if capture_evidence
            else {}
        )
        return await self.guard_async_callback(
            action="fill",
            url=url,
            amount=amount,
            field_name=field_name or selector,
            field_label=field_label,
            input_type=input_type,
            currency=currency,
            merchant_label=merchant_label or evidence.get("merchantLabel"),
            page_title=evidence.get("pageTitle"),
            dom_excerpt=evidence.get("domExcerpt"),
            screenshot_path=evidence.get("screenshotPath"),
            cart_summary=evidence.get("cartSummary"),
            amount_text=evidence.get("amountText"),
            purpose=purpose,
            budget_tags=budget_tags,
            business_context={**evidence, **dict(business_context or {})},
            dry_run=dry_run,
            callback=lambda: page.fill(selector, value),
        )


def guard_browser_action(
    wallet: Wallet,
    *,
    url: str,
    amount: float | None,
    action: str,
    selector: str | None = None,
    text: str | None = None,
    field_name: str | None = None,
    field_label: str | None = None,
    input_type: str | None = None,
    currency: str | None = None,
    merchant_label: str | None = None,
    page_title: str | None = None,
    dom_excerpt: str | None = None,
    screenshot_path: str | None = None,
    cart_summary: str | None = None,
    amount_text: str | None = None,
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
            page_title=page_title,
            dom_excerpt=dom_excerpt,
            screenshot_path=screenshot_path,
            cart_summary=cart_summary,
            amount_text=amount_text,
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
        page_title=page_title,
        dom_excerpt=dom_excerpt,
        screenshot_path=screenshot_path,
        cart_summary=cart_summary,
        amount_text=amount_text,
        purpose=purpose,
        budget_tags=budget_tags,
        business_context=business_context,
        dry_run=dry_run,
    )


def _safe_locator_text(page: Any, selector: str | None) -> str | None:
    if not selector or not hasattr(page, "locator"):
        return None
    try:
        text = page.locator(selector).inner_text()
    except Exception:
        return None
    return str(text) if text else None


def build_playwright_evidence(
    page: Any,
    *,
    screenshot_path: str | None = None,
    amount_selector: str | None = None,
    cart_selector: str | None = None,
    merchant_selector: str | None = None,
    max_dom_chars: int = 500,
) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    try:
        title = page.title()
        if title:
            evidence["pageTitle"] = str(title)
    except Exception:
        pass
    try:
        if hasattr(page, "locator"):
            text = page.locator("body").inner_text()
            if text:
                evidence["domExcerpt"] = str(text)[:max_dom_chars]
                amount_match = AMOUNT_RE.search(str(text))
                if amount_match:
                    evidence["amountHintUsd"] = float(amount_match.group("amount").replace(",", "."))
                lowered = str(text).lower()
                if "cart" in lowered or "order summary" in lowered:
                    evidence["cartSummary"] = str(text)[:200]
    except Exception:
        pass
    amount_text = _safe_locator_text(page, amount_selector)
    if amount_text:
        evidence["amountText"] = amount_text
    cart_text = _safe_locator_text(page, cart_selector)
    if cart_text:
        evidence["cartSummary"] = cart_text[:200]
    merchant_text = _safe_locator_text(page, merchant_selector)
    if merchant_text:
        evidence["merchantLabel"] = merchant_text[:120]
    if screenshot_path:
        try:
            page.screenshot(path=screenshot_path)
            evidence["screenshotPath"] = screenshot_path
        except Exception:
            pass
    if evidence.get("pageTitle"):
        evidence["productSummary"] = evidence.get("pageTitle")
    return evidence


async def _safe_locator_text_async(page: Any, selector: str | None) -> str | None:
    if not selector or not hasattr(page, "locator"):
        return None
    try:
        text = await page.locator(selector).inner_text()
    except Exception:
        return None
    return str(text) if text else None


async def build_playwright_evidence_async(
    page: Any,
    *,
    screenshot_path: str | None = None,
    amount_selector: str | None = None,
    cart_selector: str | None = None,
    merchant_selector: str | None = None,
    max_dom_chars: int = 500,
) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    try:
        title = await page.title()
        if title:
            evidence["pageTitle"] = str(title)
    except Exception:
        pass
    try:
        if hasattr(page, "locator"):
            text = await page.locator("body").inner_text()
            if text:
                evidence["domExcerpt"] = str(text)[:max_dom_chars]
                amount_match = AMOUNT_RE.search(str(text))
                if amount_match:
                    evidence["amountHintUsd"] = float(amount_match.group("amount").replace(",", "."))
                lowered = str(text).lower()
                if "cart" in lowered or "order summary" in lowered:
                    evidence["cartSummary"] = str(text)[:200]
    except Exception:
        pass
    amount_text = await _safe_locator_text_async(page, amount_selector)
    if amount_text:
        evidence["amountText"] = amount_text
    cart_text = await _safe_locator_text_async(page, cart_selector)
    if cart_text:
        evidence["cartSummary"] = cart_text[:200]
    merchant_text = await _safe_locator_text_async(page, merchant_selector)
    if merchant_text:
        evidence["merchantLabel"] = merchant_text[:120]
    if screenshot_path:
        try:
            await page.screenshot(path=screenshot_path)
            evidence["screenshotPath"] = screenshot_path
        except Exception:
            pass
    if evidence.get("pageTitle"):
        evidence["productSummary"] = evidence.get("pageTitle")
    return evidence
