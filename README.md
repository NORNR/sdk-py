# NORNR Python SDK

Teknisk not:
Python-paketet heter fortfarande `agentpay` och klienten `AgentPayClient` tills vidare for bakatkompatibilitet.

Install from this repo today:

```bash
pip install -e packages/sdk-py
```

When the package is published publicly, the install command will be:

```bash
pip install agentpay
```

Tre-raders quickstart:

```python
from agentpay import Wallet

wallet = Wallet.create(owner="research-agent", daily_limit=100, base_url="https://nornr.com")
decision = wallet.pay(amount=5, to="openai", purpose="model inference")
```

Om `decision["requiresApproval"]` ar `True` kan du godkanna i samma facade:

```python
wallet.approve_if_needed(decision)
wallet.settle()
```

OpenAI Agents SDK adapter:

```python
from agents import Agent
from agentpay import Wallet, create_openai_agents_tools

wallet = Wallet.create(owner="research-agent", daily_limit=100, base_url="https://nornr.com")
agent = Agent(name="Research agent", tools=create_openai_agents_tools(wallet))
```

LangChain adapter:

```python
from agentpay import Wallet, create_langchain_tools

wallet = Wallet.create(owner="ops-agent", daily_limit=100, base_url="https://nornr.com")
tools = create_langchain_tools(wallet)
```

```python
from agentpay import AgentPayClient, Wallet

public_client = AgentPayClient(base_url="http://127.0.0.1:3000")

onboarding = public_client.onboard(
    {
        "workspaceName": "Atlas Agents",
        "agentName": "research-agent",
        "dailyLimitUsd": 50,
    }
)

client = public_client.with_api_key(onboarding["apiKey"]["key"])
bootstrap = client.get_bootstrap()
policy_templates = client.list_policy_templates()
api_key_templates = client.list_api_key_templates()
caps = client.list_budget_caps()

client.update_identity(
    {
        "legalName": "Atlas Agents AB",
        "contactEmail": "owner@atlasagents.ai",
        "jurisdiction": "SE",
    }
)

client.create_deposit(
    {
        "amountUsd": 25,
        "source": "bank-transfer",
    }
)

client.create_payment_intent(
    {
        "agentId": bootstrap["agents"][0]["id"],
        "amountUsd": 5,
        "counterparty": "openai",
        "destination": "0x1111111111111111111111111111111111111111",
        "budgetTags": {
            "team": "growth",
            "project": "agent-wallet-rollout",
            "customer": "atlas-enterprise",
            "costCenter": "ai-rnd",
        },
        "purpose": "model inference",
    }
)

agreement = client.create_agreement(
    {
        "buyerAgentId": bootstrap["agents"][0]["id"],
        "title": "Dataset scrape engagement",
        "counterpartyName": "scraper-agent",
        "counterpartyDestination": "0x2222222222222222222222222222222222222222",
        "milestones": [
            {"title": "Collect URLs", "amountUsd": 12},
            {"title": "Normalize output", "amountUsd": 8},
        ],
    }
)

client.submit_milestone_proof(
    agreement["agreement"]["id"],
    agreement["agreement"]["milestones"][0]["id"],
    {"summary": "Output bundle uploaded"},
)

client.release_milestone(
    agreement["agreement"]["id"],
    agreement["agreement"]["milestones"][0]["id"],
)

client.run_settlement()
reputation = client.get_reputation()
cost_report = client.get_cost_report()
cost_report_csv = client.export_cost_report("csv")
scoped_key = client.create_api_key(
    {
        "label": "observer-key",
        "templateId": "observer",
    }
)
rotated_key = client.rotate_api_key(scoped_key["id"])
client.create_budget_cap(
    {
        "dimension": "team",
        "value": "growth",
        "limitUsd": 100,
        "action": "queue",
    }
)
simulation = client.simulate_policy(
    {
        "agentId": bootstrap["agents"][0]["id"],
        "templateId": "production_guarded",
    }
)
policy_diff = client.diff_policy(
    {
        "agentId": bootstrap["agents"][0]["id"],
        "templateId": "production_guarded",
        "mode": "shadow",
    }
)
anomalies = client.list_anomalies()
statement = client.get_monthly_statement()

client.create_webhook(
    {
        "label": "slack-approvals",
        "url": "simulate://slack-approvals",
        "deliveryMode": "slack",
        "publicBaseUrl": "http://127.0.0.1:3000",
        "events": ["approval.created"],
    }
)
```

Examples:

- `examples/python/wallet_quickstart.py`
- `examples/python/basic_workflow.py`
- `examples/python/openai_agents_sdk_wallet.py`
- `examples/python/langchain_agent_budget.py`
- `examples/python/langchain_wallet_tools.py`
- `examples/python/crewai_slack_approvals.py`
