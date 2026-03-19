import os

from agentpay import NornrWallet, create_mcp_server


wallet = NornrWallet.connect(
    api_key=os.environ["NORNR_API_KEY"],
    base_url=os.getenv("NORNR_BASE_URL", "https://nornr.com"),
)
server = create_mcp_server(wallet, server_name="nornr-review-mini-app")

queued = server.call_tool(
    "nornr.request_spend",
    {
        "amount": 25,
        "to": "stripe",
        "counterparty": "stripe",
        "purpose": "Governed browser checkout",
        "business_context": {"surface": "browser", "flow": "checkout"},
    },
)
bundle = server.call_tool("nornr.review_bundle", {})
finance_close = server.read_resource("nornr://finance-close")

print({"queued": queued, "bundle": bundle, "financeClose": finance_close})
