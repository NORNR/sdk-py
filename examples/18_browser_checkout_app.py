import os

from agentpay import BrowserCheckoutGuard, NornrWallet


class DemoCheckoutPage:
    def title(self) -> str:
        return "Acme AI Pro checkout"

    def locator(self, selector: str):
        self._selector = selector
        return self

    def inner_text(self) -> str:
        fixtures = {
            "body": "Acme AI Pro checkout. Order summary: Pro plan $129.00 due today. Merchant: Acme AI.",
            "[data-order-total]": "$129.00 due today",
            "[data-order-summary]": "Order summary: Pro plan $129.00 due today.",
            "[data-merchant]": "Acme AI",
        }
        return fixtures.get(getattr(self, "_selector", "body"), "")

    def screenshot(self, *, path: str) -> None:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("checkout screenshot")


wallet = NornrWallet.connect(
    api_key=os.environ["NORNR_API_KEY"],
    base_url=os.getenv("NORNR_BASE_URL", "https://nornr.com"),
)
guard = BrowserCheckoutGuard(wallet, blocked_domains=["checkout.acme.ai"])
page = DemoCheckoutPage()

result = guard.guard_playwright_click(
    page,
    url="https://checkout.acme.ai/session/pro-plan",
    selector="button.confirm-payment",
    amount=None,
    text="Confirm payment",
    amount_selector="[data-order-total]",
    cart_selector="[data-order-summary]",
    merchant_selector="[data-merchant]",
    dry_run=True,
)

print(result.to_summary_dict())
