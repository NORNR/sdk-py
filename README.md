# agentpay

Python SDK for [NORNR](https://nornr.com) — spend governance for AI agents.

NORNR sits between agent intent and real settlement. Policy decides approved / queued / blocked. Every decision leaves a signed audit trail.

---

## Install

```bash
pip install agentpay
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

if decision.get("requiresApproval"):
    wallet.approve_if_needed(decision)
```

---

## Connect an existing workspace

```python
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

## Links

- [nornr.com](https://nornr.com)
- [Control room](https://nornr.com/app)
- [TypeScript SDK](https://github.com/NORNR/sdk-ts)

---

## License

MIT
