from agentpay import NornrWallet, create_mcp_server


wallet = NornrWallet.connect(
    api_key="replace-with-nornr-api-key",
    base_url="https://nornr.com",
)
server = create_mcp_server(wallet, server_name="nornr-review")

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
print("Queued decision:", queued)

bundle = server.call_tool("nornr.review_bundle", {})
print("Review bundle:", bundle)

finance_close = server.read_resource("nornr://finance-close")
print("Finance close:", finance_close)
