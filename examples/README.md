# agentpay examples

Use these in this order.

Primary golden paths:

- `14_runtime_namespace.py` shows the canonical governed runtime
- `05_browser_checkout_guard.py` shows browser checkout governance with selector-based evidence
- `16_mcp_review_flow.py` shows queue -> review bundle -> finance-close operator flow

Fastest reference apps:

- `17_governed_runtime_app.py` is the shortest production-shaped governed runtime
- `18_browser_checkout_app.py` is the shortest production-shaped browser checkout review flow
- `19_mcp_review_app.py` is the shortest production-shaped MCP operator review flow
- `20_agent_zero_mcp_app.py` is the shortest Agent Zero MCP-first proof

Secondary examples:

- `01_basic_guard.py` shows `@nornr_guard(...)` around a real OpenAI call
- `02_async_wallet.py` shows the smallest `AsyncWallet` flow
- `04_mcp_server.py` shows the MCP-ready stdio tool surface
- `09_monthly_close.py` shows the hosted monthly close workflow
- `10_weekly_finance_handoff.py` shows the hosted weekly finance handoff workflow

Framework and operator surfaces:

- `03_pydantic_ai_agent.py` shows the PydanticAI adapter surface
- `06_controller_agent.py` shows the VP-of-Finance controller pattern with simple ROI inputs
- `07_accounting_bridge.py` shows how to turn NORNR activity into accounting payloads and worker exports
- `08_framework_kits.py` shows the productized framework kits for MCP, browser agents, OpenAI Agents, PydanticAI and LangGraph
- `11_a2a_escrow_handshake.py` shows a proof-backed dual-attestation A2A escrow release
- `12_agent_resume.py` shows how to generate a verified NORNR agent resume from trust + directory signals
- `13_openclaw_governance.py` shows how to put NORNR in front of autonomous OpenClaw paid actions
- `20_agent_zero_mcp_app.py` shows how to put NORNR in front of Agent Zero MCP-driven paid actions

Set these env vars before running them:

- `NORNR_API_KEY`
- `NORNR_BASE_URL` (optional, defaults to `https://nornr.com`)
- `OPENAI_API_KEY` for `01_basic_guard.py`

Install from PyPI with `pip install nornr-agentpay`.
Import in Python with `import agentpay` or `from agentpay import ...`.

If you only run three examples, use exactly the three primary golden paths above.
