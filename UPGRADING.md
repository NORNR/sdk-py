# Upgrading

## Install name vs import name

Install from PyPI with:

```bash
pip install nornr-agentpay
```

Import in Python with:

```python
import agentpay
```

The difference is intentional:

- `nornr-agentpay` is the public distribution name on PyPI
- `agentpay` is the stable Python import path used by the SDK and examples

## Runtime namespace

If you want a control-plane-first entrypoint instead of `Wallet`, prefer:

```python
from agentpay import NornrRuntime
```

This sits above the wallet and keeps the same governed action lifecycle.

## Preferred wrapper entrypoints

If you were calling the generic wrapper helpers directly, prefer these where they fit:

- `wrap_openai_client(...)` for OpenAI-style `responses` and `chat.completions`
- `wrap_anthropic_client(...)` for Anthropic-style `messages`
- `wrap(...)` and `wrap_async(...)` still work when you need a more generic provider surface

These helpers keep provider naming and replay context more consistent in logs and review trails.

## Preferred reference apps

For new integrations, start from these before adapting older examples:

- `17_governed_runtime_app.py`
- `18_browser_checkout_app.py`
- `19_mcp_review_app.py`
