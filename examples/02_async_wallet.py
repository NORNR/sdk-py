import asyncio
import os

from agentpay import AsyncWallet


async def main() -> None:
    wallet = await AsyncWallet.connect(
        api_key=os.environ["NORNR_API_KEY"],
        base_url=os.environ.get("NORNR_BASE_URL", "https://nornr.com"),
    )

    decision = await wallet.pay(
        amount=6.0,
        to="openai",
        purpose="Async inference batch",
        budget_tags={
            "team": "ml-platform",
            "project": "batch-refresh",
        },
    )

    print(decision.status)
    print(decision.to_summary_dict())


if __name__ == "__main__":
    asyncio.run(main())
