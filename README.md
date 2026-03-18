# agentpay

Python SDK for [NORNR](https://nornr.com), the control layer before agent spend happens.

NORNR sits before provider spend, vendor actions, or paid tool calls. It decides whether spend is `approved`, `queued`, or `rejected`, then leaves behind an audit trail your operators and finance team can actually use.

The published package name remains `agentpay` and the lower-level client remains `AgentPayClient` for backward compatibility. For new Python code, start with `NornrWallet` or `Wallet`.

## Default backend URL

The SDK defaults to the hosted NORNR control plane at `https://nornr.com`.

Override it in either of these ways:

- pass `base_url="http://127.0.0.1:3000"` directly to `AgentPayClient`, `NornrWallet`, or `AsyncWallet`
- set `NORNR_BASE_URL=http://127.0.0.1:3000` in your shell or `.env`

That keeps production usage friction low while still making localhost testing explicit and easy.

## Why use this instead of provider caps alone?

Provider-side limits on Modal, OpenAI, Replicate, or cloud infra are still a good idea. Keep them on.

NORNR adds a different layer:

- decide before the expensive run starts
- route larger or unusual spend into approval
- keep a shared operator and finance trail
- replay policy changes over historical decisions

Recommended production pattern:

1. NORNR decides whether the run should start.
2. Provider-side spend caps stay enabled as a second defensive layer.
3. Your code uses checkpointing so interrupted or queued runs can resume safely.

## Install

Public package:

```bash
pip install agentpay
```

With async extras:

```bash
pip install "agentpay[async]"
```

With Pydantic validation helpers:

```bash
pip install "agentpay[pydantic]"
```

With framework adapters:

```bash
pip install "agentpay[openai-agents]"
pip install "agentpay[langchain]"
pip install "agentpay[crewai]"
```

From this repo during local development:

```bash
pip install -e packages/sdk-py
```

To build and publish the package to PyPI when you're ready:

```bash
python -m pip install -U build twine
python -m build
python -m twine upload dist/*
```

Minimal copy-pasteable examples live under [`examples/`](./examples):

- [`01_basic_guard.py`](./examples/01_basic_guard.py)
- [`02_async_wallet.py`](./examples/02_async_wallet.py)
- [`03_pydantic_ai_agent.py`](./examples/03_pydantic_ai_agent.py)

## License

`agentpay` is published under the MIT license. See [LICENSE](./LICENSE).

## Start here in 60 seconds

```python
from agentpay import NornrWallet

wallet = NornrWallet.create(
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

if decision.status == "approved":
    print("Continue with the paid API call")
elif decision.requires_approval:
    print("Queued for review:", decision.to_summary_dict())
else:
    print("Blocked:", decision.to_summary_dict())
```

## ML / compute quickstart

```python
from agentpay import NornrWallet

wallet = NornrWallet.connect(
    api_key="replace-with-nornr-api-key",
    base_url="https://nornr.com",
)

decision = wallet.pay(
    amount=18.0,
    to="modal",
    purpose="Launch one A100 batch run for embedding refresh",
    budget_tags={
        "team": "ml-platform",
        "project": "embedding-refresh",
        "customer": "internal",
        "costCenter": "inference",
    },
)

if decision.status != "approved":
    raise SystemExit(f"Do not launch the GPU run yet. NORNR returned {decision.status}.")

# Keep provider-side caps enabled even after NORNR clears the run.
```

## Pythonic high-level API

The SDK now exposes typed high-level records for the most common operator flows.

```python
from agentpay import NornrWallet

wallet = NornrWallet.connect(api_key="replace-with-nornr-api-key", base_url="https://nornr.com")

decision = wallet.pay(amount=4.5, to="openai", purpose="tool call")
print(decision.status)
print(decision.payment_intent.counterparty)

balance = wallet.balance()
print(balance.available_usd)

review = wallet.audit_review()
print(review.finance_packet.score)
```

Useful high-level methods:

- `wallet.pay(...)`
- `wallet.pending_approvals()`
- `wallet.approve_if_needed(...)`
- `wallet.balance()`
- `wallet.simulate_policy(...)`
- `wallet.list_policy_packs()`
- `wallet.replay_policy_pack(...)`
- `wallet.apply_policy_pack(...)`
- `wallet.audit_review()`
- `wallet.finance_packet()`
- `wallet.timeline()`
- `wallet.weekly_review()`

## Actionable approval errors

Queued decisions surface a direct control-room URL when one exists:

```python
from agentpay import ApprovalRequiredError, NornrWallet

wallet = NornrWallet.connect(api_key="replace-with-nornr-api-key", base_url="https://nornr.com")

try:
    wallet.pay(amount=40.0, to="modal", purpose="Large GPU run")
except ApprovalRequiredError as exc:
    print(exc)  # ... Approve it here: https://nornr.com/app/approvals/...
```

## Drop NORNR into existing Python code

If you want NORNR to feel native inside existing ML or agent code, start here.
These are the three highest-signal patterns:

- `@nornr_guard(...)` around an async function
- `with wallet.guard(...)` around a local expensive block
- `wrap(OpenAI(), wallet, ...)` to secure an existing client in one line

```python
from agentpay import NornrWallet, nornr_guard

wallet = NornrWallet.connect(
    api_key="replace-with-nornr-api-key",
    base_url="https://nornr.com",
)

@nornr_guard(
    wallet,
    amount=5.0,
    counterparty="openai",
    purpose="One completion run",
)
async def get_completion(prompt: str) -> str:
    return f"ran for {prompt}"
```

You can also gate code blocks with a context manager:

```python
from agentpay import NornrWallet

wallet = NornrWallet.connect(
    api_key="replace-with-nornr-api-key",
    base_url="https://nornr.com",
)

with wallet.guard(amount=18.0, counterparty="modal", purpose="Launch one GPU run"):
    print("Start the expensive run only after NORNR approves it.")
```

The decorator preserves the original function metadata for IDEs and static analysis.

Wrap an existing OpenAI- or Anthropic-style client in one line:

```python
from openai import OpenAI
from agentpay import NornrWallet, wrap

wallet = NornrWallet.connect(api_key="replace-with-nornr-api-key", base_url="https://nornr.com")
client = wrap(OpenAI(), wallet, amount=2.5, counterparty="openai", purpose="chat completion")
```

## Dry-run previews and local budget scopes

If you want a live policy decision without reserving funds or creating ledger entries, use `dry_run=True`.

```python
decision = wallet.pay(
    amount=18.0,
    to="modal",
    purpose="Preview one GPU run",
    dry_run=True,
)
print(decision.to_summary_dict())
```

For function- or block-level control, use a temporary local budget scope:

```python
from agentpay import budget

with budget(5, purpose_prefix="research", dry_run=True):
    wallet.pay(amount=3.0, to="openai", purpose="probe")
```

## Async usage

```python
import asyncio

from agentpay import AsyncWallet


async def main() -> None:
    wallet = await AsyncWallet.connect(
        api_key="replace-with-nornr-api-key",
        base_url="https://nornr.com",
    )
    decision = await wallet.pay(
        amount=6.0,
        to="openai",
        purpose="async inference run",
    )
    print(decision.status)


asyncio.run(main())
```

If `httpx` is installed, the async client uses it directly. Otherwise it falls back to a thread-backed sync transport so you can still integrate it without extra runtime dependencies.

## Wrapped clients and streaming

For explicit streaming flows, use `guarded_stream(...)` or `guarded_async_stream(...)` so the decision happens before the first chunk leaves the generator.

## Cost estimation and circuit breaking

Use the built-in estimator for cheap pre-flight checks before you even call the model provider:

```python
from agentpay import estimate_cost

estimate = estimate_cost(model="gpt-4.1-mini", prompt="Summarize the anomalies", completion_tokens=400)
print(estimate.estimated_total_usd)
```

If you want an extra local safety net against runaway loops, enable the wallet circuit breaker:

```python
wallet.enable_circuit_breaker(max_requests=10, window_seconds=1, max_spend_usd=5)
```

## Context-aware spending

If you want NORNR to understand why the agent is spending, add business context once and let it flow into the decision:

```python
from agentpay import business_context

with business_context(
    reason="Production incident response",
    ticket_id="INC-402",
    customer_segment="enterprise",
    priority="critical",
    tags={"workflow": "incident"},
):
    decision = wallet.pay(amount=6.0, to="openai", purpose="Summarize outage logs")
```

That metadata is attached to the payment intent as structured context instead of only living in local code.

## Policy-driven execution

Use `wallet.check(...)` when the agent wants to ask for permission before it chooses a plan:

```python
check = wallet.check(
    intent="Analyze 1TB of support transcripts",
    cost=18.0,
    counterparty="openai",
    business_context={"reason": "VIP escalation", "ticketId": "SUP-9201", "priority": "high"},
)

if not check.allowed:
    print(check.recommended_action)
```

This keeps the agent adaptive: it can scale the plan down or route for approval before it starts spending.

## Proof-of-work and dispute-ready escrow

Agreements can now carry simple proof requirements so escrow only releases after the work product is attached and verified:

```python
agreement = client.create_agreement(
    {
        "buyerAgentId": "agent_123",
        "title": "Dataset labeling engagement",
        "counterpartyName": "labeling-agent",
        "counterpartyDestination": "0xlabelingagent",
        "milestones": [
            {
                "title": "Deliver verified dataset",
                "amountUsd": 15,
                "proofRequirements": {
                    "requireSummary": True,
                    "requireUrl": True,
                    "requireArtifactHash": True,
                    "acceptedResultTypes": ["dataset"],
                },
            }
        ],
    }
)

client.submit_milestone_proof(
    agreement_id="agreement_123",
    milestone_id="milestone_123",
    payload={
        "summary": "Uploaded labeled dataset",
        "url": "https://example.com/labeled-dataset",
        "artifactHash": "sha256:dataset-bundle",
        "resultType": "dataset",
    },
)
```

If a proof bundle fails the mandate check, NORNR blocks release until the operator reviews, disputes, or resubmits the milestone package.

Use `client.get_trust_profile()` when you want the workspace-level trust posture and counterparty signals in one payload.

## NORNR Verified trust manifests

Use the trust manifest helpers when you want a machine-readable verification layer for a workspace:

```python
manifest = client.get_trust_manifest()
signed_manifest = client.get_signed_trust_manifest()
validation = client.verify_trust_manifest(signed_manifest)

print(manifest["verification"]["tier"])
print(validation["ok"])
```

For counterparty checks:

```python
handshake = client.handshake_trust_manifest(
    {
        "envelope": signed_counterparty_manifest,
        "minTier": "verified",
        "minScore": 70,
    }
)

print(handshake["decision"])
print(handshake["reasons"])
```

## Policy replay

```python
from agentpay import NornrWallet

wallet = NornrWallet.connect(api_key="replace-with-nornr-api-key", base_url="https://nornr.com")
simulation = wallet.simulate_policy(
    template_id="research-safe",
    rollout_mode="shadow",
)

print(simulation.rollout_mode)
print(simulation.summary)
print(simulation.delta)
```

Replay is especially useful when you want to answer:

- would this new policy reduce operator load?
- how much spend would it have prevented?
- how many false positives would it introduce?

## Curated Policy Packs

Official governance packs let you install a proven control posture instead of hand-tuning every field from scratch.

```python
from agentpay import NornrWallet

wallet = NornrWallet.connect(api_key="replace-with-nornr-api-key", base_url="https://nornr.com")
catalog = wallet.list_policy_packs()

print(catalog["recommendedPackId"])
print(catalog["packs"][0]["title"])

replay = wallet.replay_policy_pack("research-safe", mode="shadow")
print(replay["replay"]["candidate"]["summary"])

applied = wallet.apply_policy_pack("research-safe", mode="shadow")
print(applied["install"]["mode"])
```

Current official packs focus on:

- research / model spend
- GPU + compute bursts
- vendor / procurement workflows
- browser ops
- finance review lanes

## Audit and finance handoff

```python
from agentpay import NornrWallet

wallet = NornrWallet.connect(api_key="replace-with-nornr-api-key", base_url="https://nornr.com")
review = wallet.audit_review()

print(review.executive_summary)
print(review.finance_packet.open_actions)
print(review.finance_packet.packet_history)
```

This is useful for:

- weekly operator review
- finance packet automation
- compliance exports
- internal approvals and handoffs

## Optional Pydantic integration

If `pydantic` is installed, typed records can be converted into validated Pydantic models:

```python
from agentpay import NornrWallet, PYDANTIC_AVAILABLE

wallet = NornrWallet.connect(api_key="replace-with-nornr-api-key", base_url="https://nornr.com")
decision = wallet.pay(amount=3.0, to="openai", purpose="validation demo")

if PYDANTIC_AVAILABLE:
    validated = decision.to_pydantic()
    print(validated.model_dump())
```

You also get a lightweight PydanticAI integration surface:

```python
from agentpay import NornrDeps, NornrWallet, create_pydanticai_tools

wallet = NornrWallet.connect(api_key="replace-with-nornr-api-key", base_url="https://nornr.com")
deps = NornrDeps(wallet=wallet)
tools = create_pydanticai_tools(wallet)
```

## FastAPI and LangGraph helpers

FastAPI dependency injection:

```python
from fastapi import Depends, FastAPI
from agentpay import wallet_dependency

app = FastAPI()
get_wallet = wallet_dependency(base_url="https://nornr.com")
```

LangGraph state integration:

```python
from agentpay import record_decision

state = record_decision(state, decision)
```

## Policy as code

If your team wants policy definitions in Git instead of hand-edited JSON:

```python
from agentpay import Policy, apply_policy

class ResearchPolicy(Policy):
    daily_limit = 50
    require_approval_above = 15
    allowlist = ["openai", "anthropic"]

apply_policy(wallet, ResearchPolicy)
```

## Safe audit replay context

NORNR now captures a redacted execution context for guarded calls, including the calling function, file, line, and sanitized inputs. Sensitive fields such as tokens, passwords, and auth headers are redacted by default.

## Framework adapters

### OpenAI Agents SDK

```python
from agents import Agent

from agentpay import NornrWallet, create_openai_agents_tools

wallet = NornrWallet.create(
    owner="openai-agents-researcher",
    daily_limit=100,
    require_approval_above=25,
    whitelist=["openai"],
    base_url="https://nornr.com",
)

agent = Agent(
    name="Research agent",
    instructions="Use NORNR before any tool or vendor purchase. If NORNR queues a spend, ask for review instead of continuing.",
    tools=create_openai_agents_tools(wallet),
)
```

### LangChain

```python
from agentpay import NornrWallet, create_langchain_tools

wallet = NornrWallet.create(
    owner="langchain-ops-agent",
    daily_limit=100,
    require_approval_above=25,
    whitelist=["openai", "anthropic"],
    base_url="https://nornr.com",
)

tools = create_langchain_tools(wallet)
```

## Lower-level client

Use `AgentPayClient` when you want direct API access.

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
client.create_budget_cap(
    {
        "dimension": "team",
        "value": "growth",
        "limitUsd": 500,
        "action": "queue",
    }
)
```

## Errors

The SDK raises typed errors for the most common failure classes:

- `AuthenticationError`
- `ValidationError`
- `RateLimitError`
- `TransportError`
- `AgentPayError`

```python
from agentpay import AuthenticationError, RateLimitError, TransportError
```

## Common mistakes

- relying on provider caps alone without a pre-run decision layer
- treating `queued` the same as `approved`
- forgetting checkpointing for long ML or compute runs
- skipping budget tags, which makes finance review much weaker later

## Examples

See [examples/python/README.md](/Users/alexanderohlsson/gemin/Projekt/AIAGENTSCRYPTO/examples/python/README.md) for the curated list.

Strong starting points:

- [wallet_quickstart.py](/Users/alexanderohlsson/gemin/Projekt/AIAGENTSCRYPTO/examples/python/wallet_quickstart.py)
- [modal_gpu_budget.py](/Users/alexanderohlsson/gemin/Projekt/AIAGENTSCRYPTO/examples/python/modal_gpu_budget.py)
- [batch_inference_with_approval.py](/Users/alexanderohlsson/gemin/Projekt/AIAGENTSCRYPTO/examples/python/batch_inference_with_approval.py)
- [checkpoint_safe_run.py](/Users/alexanderohlsson/gemin/Projekt/AIAGENTSCRYPTO/examples/python/checkpoint_safe_run.py)
- [weekly_finance_review.py](/Users/alexanderohlsson/gemin/Projekt/AIAGENTSCRYPTO/examples/python/weekly_finance_review.py)
- [dry_run_preview.py](/Users/alexanderohlsson/gemin/Projekt/AIAGENTSCRYPTO/examples/python/dry_run_preview.py)
- [fastapi_dependency.py](/Users/alexanderohlsson/gemin/Projekt/AIAGENTSCRYPTO/examples/python/fastapi_dependency.py)
- [langgraph_state.py](/Users/alexanderohlsson/gemin/Projekt/AIAGENTSCRYPTO/examples/python/langgraph_state.py)
- [context_aware_spend.py](/Users/alexanderohlsson/gemin/Projekt/AIAGENTSCRYPTO/examples/python/context_aware_spend.py)
- [policy_check.py](/Users/alexanderohlsson/gemin/Projekt/AIAGENTSCRYPTO/examples/python/policy_check.py)
- [wrap_openai_client.py](/Users/alexanderohlsson/gemin/Projekt/AIAGENTSCRYPTO/examples/python/wrap_openai_client.py)
- [pydanticai_agent.py](/Users/alexanderohlsson/gemin/Projekt/AIAGENTSCRYPTO/examples/python/pydanticai_agent.py)
- [openai_agents_sdk_wallet.py](/Users/alexanderohlsson/gemin/Projekt/AIAGENTSCRYPTO/examples/python/openai_agents_sdk_wallet.py)
- [langchain_wallet_tools.py](/Users/alexanderohlsson/gemin/Projekt/AIAGENTSCRYPTO/examples/python/langchain_wallet_tools.py)

## CLI helper

The package now exposes a tiny `nornr` CLI for bootstrapping local env files:

```bash
nornr login --api-key agpk_live_123 --path .env
nornr init --owner research-agent --path .env.nornr
nornr estimate-cost --model gpt-4.1-mini --prompt "hello"
```

## Observability hooks

NORNR can attach spend metadata to your logs or current OpenTelemetry span:

```python
import logging

from agentpay import NornrWallet, annotate_current_span, bind_logger

wallet = NornrWallet.connect(api_key="replace-with-nornr-api-key", base_url="https://nornr.com")
decision = wallet.pay(amount=3.5, to="openai", purpose="traceable completion")

logger = bind_logger(logging.getLogger("agent"), decision)
logger.info("Completion approved")

annotate_current_span(decision)
```

## Links

- [nornr.com](https://nornr.com)
- [Quickstart](https://nornr.com/quickstart)
- [Control room](https://nornr.com/app)
- [TypeScript SDK](https://github.com/NORNR/sdk-ts)

## License

MIT
