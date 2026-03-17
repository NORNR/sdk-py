# agentpay

Python SDK for [NORNR](https://nornr.com) - mandates, approvals, and evidence for autonomous agents.

NORNR gives your agents a mandate before they spend. Policy decides `approved`, `queued`, or `blocked`. Every decision gets a signed receipt. Your agent then acts on the decision using its own payment rails.

The published Python package name remains `agentpay`, and the lower-level client remains `AgentPayClient` for backward compatibility. `Wallet` is the recommended starting point.

---

## Install

Public package:

```bash
pip install agentpay
```

From this repo during local development:

```bash
pip install -e packages/sdk-py
```

---

## Quickstart

```python
from agentpay import Wallet

wallet = Wallet.create(
    owner="research-agent",
    daily_limit=100,
    require_approval_above=25,
    base_url="https://nornr.com",
)

decision = wallet.pay(
    amount=12.50,
    to="openai",
    purpose="model inference",
)

if decision.get("status") == "approved":
    response = openai_client.chat.completions.create(model="gpt-4o", messages=messages)
elif decision.get("requiresApproval"):
    wallet.approve_if_needed(decision)
else:
    print("Spend blocked:", decision.get("reasons"))
```

If the decision is approved and you are using a configured settlement adapter:

```python
wallet.settle()
```

---

## Connect an existing workspace

```python
import os
from agentpay import Wallet

wallet = Wallet.connect(
    api_key=os.environ["NORNR_API_KEY"],
    agent_id="agent_abc123",
    base_url="https://nornr.com",
)
```

---

## OpenAI Agents SDK adapter

```python
from agents import Agent
from agentpay import Wallet, create_openai_agents_tools

wallet = Wallet.create(
    owner="research-agent",
    daily_limit=100,
    require_approval_above=25,
    base_url="https://nornr.com",
)

agent = Agent(
    name="Research agent",
    tools=create_openai_agents_tools(wallet),
)
```

---

## LangChain adapter

```python
from agentpay import Wallet, create_langchain_tools

wallet = Wallet.create(
    owner="ops-agent",
    daily_limit=100,
    require_approval_above=25,
    base_url="https://nornr.com",
)

tools = create_langchain_tools(wallet)
```

---

## Full client

```python
from agentpay import AgentPayClient

public_client = AgentPayClient(base_url="https://nornr.com")
onboarding = public_client.onboard(
    {
        "workspaceName": "Atlas Agents",
        "agentName": "research-agent",
        "dailyLimitUsd": 50,
        "requireApprovalOverUsd": 20,
    }
)

client = public_client.with_api_key(onboarding["apiKey"]["key"])

client.create_payment_intent(
    {
        "agentId": onboarding["agent"]["id"],
        "amountUsd": 5,
        "counterparty": "openai",
        "purpose": "model inference",
    }
)

client.list_approvals()
client.create_budget_cap(
    {
        "dimension": "team",
        "value": "growth",
        "limitUsd": 500,
        "action": "queue",
    }
)
client.export_audit()
client.get_cost_report()
client.get_monthly_statement()
client.list_anomalies()
```

---

## Optional settlement

NORNR can optionally execute on-chain USDC settlement through a configured rail adapter. Most teams start by using NORNR as the control layer above their existing payment infrastructure.

---

## Links

- [nornr.com](https://nornr.com)
- [Control room](https://nornr.com/app)
- [TypeScript SDK](https://github.com/NORNR/sdk-ts)

---

## License

MIT
