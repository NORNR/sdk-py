# NORNR Python SDK

Teknisk not:
Python-paketet heter fortfarande `agentpay` och klienten `AgentPayClient` tills vidare for bakatkompatibilitet.

```python
from agentpay import AgentPayClient

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
```

Install locally:

```bash
pip install -e packages/sdk-py
```
