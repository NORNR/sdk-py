import os
import json

from agentpay import NornrWallet, create_mcp_server


wallet = NornrWallet.connect(
    api_key=os.environ["NORNR_API_KEY"],
    base_url=os.getenv("NORNR_BASE_URL", "https://nornr.com"),
)

server = create_mcp_server(wallet)

# Wire this into an MCP stdio launcher or a small local bridge process.
print(json.dumps(server.build_manifest(), indent=2))
print(json.dumps(server.build_claude_desktop_config(env={"NORNR_API_KEY": os.environ["NORNR_API_KEY"]}), indent=2))
