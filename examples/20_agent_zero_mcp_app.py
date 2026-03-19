import os

from agentpay import NornrWallet, create_mcp_server


wallet = NornrWallet.connect(
    api_key=os.environ["NORNR_API_KEY"],
    base_url=os.getenv("NORNR_BASE_URL", "https://nornr.com"),
)
server = create_mcp_server(wallet, server_name="nornr-agent-zero")

queued = server.call_tool(
    "nornr.request_spend",
    {
        "amount": 32,
        "to": "northern-data",
        "counterparty": "northern-data",
        "purpose": "Buy one governed dataset from an Agent Zero task",
        "business_context": {
            "surface": "agent-zero",
            "runMode": "autonomous",
            "flow": "dataset-purchase",
            "source": "os-level-agent",
        },
    },
)
anomalies = server.read_resource("nornr://anomaly-inbox")
timeline = server.read_resource("nornr://intent-timeline")
bundle = server.call_tool("nornr.review_bundle", {})

print(
    {
        "queued": queued,
        "anomalies": anomalies,
        "timeline": timeline,
        "bundle": bundle,
    }
)
