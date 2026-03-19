import os

from agentpay import NornrWallet, create_framework_kits


wallet = NornrWallet.connect(
    api_key=os.environ["NORNR_API_KEY"],
    base_url=os.getenv("NORNR_BASE_URL", "https://nornr.com"),
)

for kit in create_framework_kits(wallet):
    print(kit.to_summary_dict())
