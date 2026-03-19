# agentpay examples

Three small entry examples live here on purpose:

- `01_basic_guard.py` shows `@nornr_guard(...)` around a real OpenAI call
- `02_async_wallet.py` shows the smallest `AsyncWallet` flow
- `03_pydantic_ai_agent.py` shows the PydanticAI adapter surface
- `04_mcp_server.py` shows the MCP-ready stdio tool surface
- `05_browser_checkout_guard.py` shows how to guard browser checkout actions and Playwright-style callbacks
- `06_controller_agent.py` shows the VP-of-Finance controller pattern with simple ROI inputs
- `07_accounting_bridge.py` shows how to turn NORNR activity into accounting payloads and worker exports
- `08_framework_kits.py` shows the productized framework kits for MCP, browser agents, OpenAI Agents, PydanticAI and LangGraph
- `09_monthly_close.py` shows the hosted monthly close workflow
- `10_weekly_finance_handoff.py` shows the hosted weekly finance handoff workflow
- `11_a2a_escrow_handshake.py` shows a proof-backed dual-attestation A2A escrow release
- `12_agent_resume.py` shows how to generate a verified NORNR agent resume from trust + directory signals
- `13_openclaw_governance.py` shows how to put NORNR in front of autonomous OpenClaw paid actions

Set these env vars before running them:

- `NORNR_API_KEY`
- `NORNR_BASE_URL` (optional, defaults to `https://nornr.com`)
- `OPENAI_API_KEY` for `01_basic_guard.py`
