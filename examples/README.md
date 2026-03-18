# agentpay examples

Three small entry examples live here on purpose:

- `01_basic_guard.py` shows `@nornr_guard(...)` around a real OpenAI call
- `02_async_wallet.py` shows the smallest `AsyncWallet` flow
- `03_pydantic_ai_agent.py` shows the PydanticAI adapter surface

Set these env vars before running them:

- `NORNR_API_KEY`
- `NORNR_BASE_URL` (optional, defaults to `https://nornr.com`)
- `OPENAI_API_KEY` for `01_basic_guard.py`
