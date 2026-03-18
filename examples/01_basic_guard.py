import asyncio
import os

from openai import OpenAI

from agentpay import NornrWallet, nornr_guard


wallet = NornrWallet.connect(
    api_key=os.environ["NORNR_API_KEY"],
    base_url=os.environ.get("NORNR_BASE_URL", "https://nornr.com"),
)
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


@nornr_guard(
    wallet,
    amount=2.5,
    counterparty="openai",
    purpose="Summarize one customer thread",
)
async def summarize(text: str) -> str:
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=f"Summarize this support thread in 3 bullets:\n\n{text}",
    )
    return getattr(response, "output_text", "")


async def main() -> None:
    result = await summarize("Customer reports a billing regression after an SDK upgrade.")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
