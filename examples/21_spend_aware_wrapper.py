import os

from openai import OpenAI

from agentpay import NornrWallet, create_spend_aware_openai_client


wallet = NornrWallet.connect(
    api_key=os.environ["NORNR_API_KEY"],
    base_url=os.getenv("NORNR_BASE_URL", "https://nornr.com"),
)

client = create_spend_aware_openai_client(
    OpenAI(),
    wallet,
    max_spend_usd=2.5,
    purpose="one wrapped provider lane",
    model="gpt-5-mini",
)

response = client.responses.create(
    model="gpt-5-mini",
    input="Summarize the top three risky tool requests from today.",
    max_output_tokens=250,
)

print(response)
