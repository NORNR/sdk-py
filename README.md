# agentpay

Python SDK for [NORNR](https://nornr.com) — spend governance for AI agents.

NORNR gives your agents a mandate before they spend. Policy decides approved / queued / blocked. Every decision gets a signed receipt. Your agent acts on the decision using its own payment rails.

---

## Install

```bash
pip install agentpay
```

---

## How it works

```
agent calls wallet.pay()
        ↓
NORNR evaluates against policy
        ↓
decision: approved / queued / blocked
        ↓
agent acts on the decision
using its own API keys and payment methods
        ↓
signed receipt + audit trail recorded
```

NORNR does not move money. It governs whether money should move, records that it did, and proves it afterward.

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
    # Mandate granted — proceed with your actual API call
    response = openai_client.chat.completions.create(model="gpt-4o", messages=messages)
elif decision.get("requiresApproval"):
    # Above threshold — queued for human approval
    wallet.approve_if_needed(decision)
else:
    # Blocked by policy
    print("Spend blocked:", decision.get("reasons"))
```

---

## Connect an existing workspace

```python
import os
from agentpay import Wallet

wallet = Wallet.connect(
    api_key=os.environ["NORNR_API_KEY"],
    agent_id="agent_abc123",
)
```

---

## Works with your agent framework

```python
# OpenAI Agents SDK
from agents import Agent
from agentpay import Wallet, create_openai_agents_tools

wallet = Wallet.create(owner="research-agent", daily_limit=100, base_url="https://nornr.com")
agent = Agent(name="Research agent", tools=create_openai_agents_tools(wallet))

# LangChain
from agentpay import Wallet, create_langchain_tools

wallet = Wallet.create(owner="ops-agent", daily_limit=100, base_url="https://nornr.com")
tools = create_langchain_tools(wallet)

# CrewAI
from agentpay import Wallet, create_crewai_tools

wallet = Wallet.create(owner="crew-agent", daily_limit=100, base_url="https://nornr.com")
tools = create_crewai_tools(wallet)
```

---

## Full client

```python
from agentpay import AgentPayClient

client = AgentPayClient(base_url="https://nornr.com").with_api_key(os.environ["NORNR_API_KEY"])

# Intents
client.create_payment_intent({"agentId": agent_id, "amountUsd": 5, "counterparty": "openai", "purpose": "inference"})

# Budget controls
client.create_budget_cap({"dimension": "team", "value": "growth", "limitUsd": 500, "action": "queue"})

# Audit
client.export_audit()
client.get_cost_report()
client.get_monthly_statement()

# Anomalies
client.list_anomalies()
```

---

## On-chain settlement (optional)

NORNR supports optional on-chain USDC settlement via Base for teams that want
cryptographic proof of transfer in addition to the signed audit trail.
This is not required for governance to work — most teams use NORNR with
their existing payment infrastructure.

---

## Links

- [nornr.com](https://nornr.com)
- [Control room](https://nornr.com/app)
- [TypeScript SDK](https://github.com/NORNR/sdk-ts)

---

## License

MIT
