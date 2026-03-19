import os

from agentpay import BrowserCheckoutGuard, NornrWallet


wallet = NornrWallet.connect(
    api_key=os.environ["NORNR_API_KEY"],
    base_url=os.getenv("NORNR_BASE_URL", "https://nornr.com"),
)

guard = BrowserCheckoutGuard(wallet, blocked_domains=["stripe.com", "openai.com"])

decision = guard.guard_click(
    url="https://platform.openai.com/checkout",
    selector="button.buy-now",
    text="Buy now",
    amount=20.0,
    purpose="Browser agent checkout guard",
)

print(decision.to_summary_dict() if decision else "No checkout risk detected")


class MockPage:
    def click(self, selector: str) -> None:
        print(f"Clicked {selector}")


page = MockPage()
result = guard.guard_playwright_click(
    page,
    url="https://platform.openai.com/checkout",
    selector="button.buy-now",
    text="Buy now",
    amount=20.0,
)
print(result.blocked)
