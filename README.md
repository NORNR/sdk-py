# agentpay

Python SDK for [NORNR](https://nornr.com), the control plane for AI agents operating with real budgets.

NORNR sits between agent intent and real-world execution. It evaluates whether an action should happen, routes larger or riskier actions into approval, surfaces anomaly posture before it hardens into normal behavior, and leaves behind a finance-ready audit trail after the action completes.

In practice, the SDK gives you four things in one surface:

- `Policy` - define what agents are allowed to do before money moves
- `Detection` - surface unusual spend, suspicious counterparties, or risky autonomous posture
- `Control` - route actions through approvals, queues, rejection, and operator review
- `Accounting` - keep receipt trail, finance packet, and export-ready records attached to the same decision

The published package name is `nornr-agentpay`, while the Python import remains `agentpay` and the lower-level client remains `AgentPayClient`. For new Python code, start with `NornrWallet` or `Wallet`.

For a control-plane-first namespace above `Wallet`, use `NornrRuntime`.

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

Fastest path:

```bash
pip install nornr-agentpay
```

Then start with exactly one of these:

1. `NornrRuntime.execute(...)` for one governed action
2. `BrowserCheckoutGuard` for browser-side paid actions
3. `create_mcp_server(...)` for operator review and autonomous-agent control

From this repo during local development:

```bash
pip install -e packages/sdk-py
```

Optional extras:

```bash
pip install nornr-agentpay
pip install "nornr-agentpay[async]"
pip install "nornr-agentpay[pydantic]"
pip install "nornr-agentpay[openai-agents]"
pip install "nornr-agentpay[langchain]"
pip install "nornr-agentpay[crewai]"
```

The PyPI distribution name is `nornr-agentpay`. The import path stays `agentpay`.

## PyPI release prep

Build a release locally:

```bash
python3 scripts/python-sdk-setup-dev.py
cd packages/sdk-py
python -m build
python -m twine check dist/*
```

To build and publish the package to PyPI when you're ready:

```bash
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=<your-pypi-token>
python -m twine upload dist/*
```

For a repeatable pre-release check without uploading, run:

```bash
npm run python-sdk:release-check
```

If you only run three examples, run these:

1. [`14_runtime_namespace.py`](./examples/14_runtime_namespace.py)
2. [`05_browser_checkout_guard.py`](./examples/05_browser_checkout_guard.py)
3. [`16_mcp_review_flow.py`](./examples/16_mcp_review_flow.py)

Everything else in [`examples/`](./examples) is secondary to those three golden paths.

If you want copy-pasteable reference apps instead of smaller snippets, start with:

- [`17_governed_runtime_app.py`](./examples/17_governed_runtime_app.py)
- [`18_browser_checkout_app.py`](./examples/18_browser_checkout_app.py)
- [`19_mcp_review_app.py`](./examples/19_mcp_review_app.py)
- [`20_agent_zero_mcp_app.py`](./examples/20_agent_zero_mcp_app.py)

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

## Golden path 1: governed execution runtime

The most important new SDK surface is the canonical governed action lifecycle.

```python
from agentpay import NornrWallet

wallet = NornrWallet.connect(api_key="replace-with-nornr-api-key", base_url="https://nornr.com")

record = wallet.execute_governed(
    action_name="gpu-refresh",
    amount=18,
    to="modal",
    counterparty="modal",
    purpose="Launch one governed GPU refresh job",
    callback=lambda: {"jobId": "job_123"},
    receipt_id="receipt_123",
    evidence={"surface": "worker", "jobType": "embedding-refresh"},
)

print(record.execution_status)
print(record.to_summary_dict())
```

Useful runtime helpers:

- `wallet.begin_governed_action(...)`
- `wallet.resume_governed_action(...)`
- `wallet.execute_governed(...)`
- `run.to_handoff_dict()`
- `run.attach_receipt_evidence(...)`
- `run.attach_evidence(...)`
- `run.attach_receipt(...)`
- `run.complete(...)`
- `run.fail(...)`
- `run.wait_for_approval(...)`

If you want the smallest drop-in version of this flow, start from [`17_governed_runtime_app.py`](./examples/17_governed_runtime_app.py).

Async parity exists on `AsyncWallet` as well.

## Control-plane-first runtime namespace

If you want a single entrypoint that reads like NORNR's product model instead of the older wallet-first model:

```python
from agentpay import NornrRuntime

runtime = NornrRuntime.connect(
    api_key="replace-with-nornr-api-key",
    base_url="https://nornr.com",
)

record = runtime.execute(
    action_name="provider-call",
    amount=5,
    to="openai",
    counterparty="openai",
    purpose="Run one governed provider call",
    callback=lambda: {"ok": True},
    receipt_id="receipt_123",
)
```

## Productized kits

The SDK now ships opinionated kits for the highest-signal operator outcomes.

```python
from agentpay import NornrWallet, create_framework_kits

wallet = NornrWallet.connect(api_key="replace-with-nornr-api-key", base_url="https://nornr.com")

for kit in create_framework_kits(wallet):
    print(kit.to_summary_dict())
```

The currently productized kits are:

- `create_openai_agents_kit(wallet)`
- `create_pydanticai_kit(wallet, business_context=...)`
- `create_langgraph_kit(wallet)`
- `create_browser_agent_kit(wallet, blocked_domains=[...])`
- `create_mcp_kit(wallet)`

Each kit bundles the right helpers plus a recommended official governance pack.

Kits can now validate and bootstrap themselves:

```python
from agentpay import NornrWallet, create_openai_agents_kit

wallet = NornrWallet.connect(api_key="replace-with-nornr-api-key", base_url="https://nornr.com")
kit = create_openai_agents_kit(wallet)

print(kit.validate_environment())
print(kit.bootstrap(mode="shadow"))
print(kit.scaffold_config())
```

## Scenario templates

The SDK now ships reusable scenario templates for the highest-signal integration lanes:

- `browser_checkout_template()`
- `paid_tool_call_template()`
- `mcp_local_tool_template()`
- `finance_close_template()`
- `delegated_sub_agent_budget_template()`
- `scenario_templates()`

These are intended as reusable onboarding assets, not just examples.

## Least-privilege key posture

```python
from agentpay import credential_posture, recommended_scopes

template = recommended_scopes("openclaw")
posture = credential_posture(template.scopes)

print(template.to_dict())
print(posture.to_dict())
```

## FastAPI middleware and governed routes

```python
from agentpay import governed_route, nornr_middleware

app.middleware("http")(nornr_middleware())

@app.post("/governed")
@governed_route(
    action_name="fastapi-governed-endpoint",
    amount=lambda *args, **kwargs: 9,
    counterparty=lambda *args, **kwargs: "openai",
    purpose=lambda *args, **kwargs: "Serve one governed endpoint call",
)
async def governed_endpoint(request):
    return {"ok": True, "traceId": request.state.nornr_trace_id}
```

## MCP: richer resources and prompts

The MCP server now exposes more than tools:

- resources:
  - `nornr://finance-packet`
  - `nornr://weekly-review`
  - `nornr://intent-timeline`
  - `nornr://pending-approvals`
  - `nornr://anomaly-inbox`
  - `nornr://policy-workbench`
  - `nornr://finance-close`
- prompts:
  - `nornr.operator-guide`
  - `nornr.policy-simulation`
  - `nornr.finance-close`

## Release discipline

See:

- [CHANGELOG](./CHANGELOG.md)
- [COMPATIBILITY](./COMPATIBILITY.md)
- [UPGRADING](./UPGRADING.md)

## Hosted finance workflows

Finance-close and weekly-handoff helpers now sit above the raw accounting bridge so teams can ship finance workflows, not just payload transforms.

```python
from agentpay import NornrWallet, run_monthly_close

wallet = NornrWallet.connect(api_key="replace-with-nornr-api-key", base_url="https://nornr.com")
report = run_monthly_close(wallet, provider="fortnox", workspace_label="NORNR finance close")
print(report.to_summary_dict())
```

Useful helpers:

- `build_finance_close_bundle(...)`
- `run_weekly_finance_handoff(...)`
- `run_monthly_close(...)`

## OpenClaw / ClawHub

OpenClaw is a distribution surface, not NORNR's product identity.
The fit is simple: put policy before paid actions, require approval for risky autonomous actions, and keep a finance-ready audit trail after execution.

```python
from agentpay import NornrWallet, OpenClawGovernanceAdapter

wallet = NornrWallet.connect(
    api_key="replace-with-nornr-api-key",
    base_url="https://nornr.com",
    agent_id="replace-with-agent-id",
)
adapter = OpenClawGovernanceAdapter(wallet)

result = adapter.preflight_paid_action(
    action="purchase",
    amount_usd=25,
    counterparty="openai",
    purpose="Run the paid OpenClaw research action",
)

print(result.to_dict())
```

The minimal official skill bundle lives in [`integrations/openclaw/nornr-governance`](../../integrations/openclaw/nornr-governance).

Useful OpenClaw review surfaces:

- `adapter.pending_approvals()`
- `adapter.approve(payment_intent_id, comment=...)`
- `adapter.reject(payment_intent_id, comment=...)`
- `adapter.anomalies(counterparty=...)`

## Least-privilege scopes

The SDK now exposes explicit least-privilege scope templates instead of leaving every integration to guess.

```python
from agentpay import recommended_scopes, review_scopes

template = recommended_scopes("openclaw")
print(template.to_dict())

review = review_scopes(["workspace:read", "audit:read"], surface="openclaw")
print(review.to_dict())
```

Useful named surfaces:

- `read-only`
- `finance-close`
- `browser-guard`
- `mcp`
- `openclaw`
- `worker`

## Webhook consumer verification

The SDK now ships a Python-side verifier for NORNR webhook payloads.

```python
from agentpay import verify_webhook_request

verified = verify_webhook_request(
    secret="replace-with-webhook-secret",
    payload=raw_body,
    headers=request.headers,
)

print(verified.event_type)
print(verified.payload["id"])
```

You can also route events through `dispatch_webhook_event(...)` after verification.

## Counterparty review and delegated mandates

Counterparty posture and sub-agent budget delegation now have first-class SDK helpers.

```python
from agentpay import NornrWallet

wallet = NornrWallet.connect(api_key="replace-with-nornr-api-key", base_url="https://nornr.com")

review = wallet.review_counterparty("openai")
print(review.to_dict())

mandate = wallet.delegate_mandate(
    target_agent_id="agent_child",
    daily_limit=15,
    counterparty="openai",
    purpose_prefix="delegated-research",
)
print(mandate.to_business_context())
```
- `adapter.intent_timeline()`
- `adapter.review_bundle(counterparty=...)`
- `adapter.audit_export()`
- `adapter.monthly_close(provider="quickbooks")`

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

## A2A escrow handshake

Use the higher-level A2A helper when both sides of an agent service need to attest before escrow is released:

```python
from agentpay import A2AEscrow, AgentAttestation, NornrClient

client = NornrClient(base_url="https://nornr.com", api_key="...")
escrow = A2AEscrow(client)

handshake = escrow.create_three_way_handshake(
    buyer_agent_id="manager-agent",
    worker_agent_id="research-worker",
    worker_destination="0xresearchworker",
    title="Research brief delivery",
    milestone_title="Submit signed executive brief",
    amount_usd=25,
)

outcome = escrow.settle_handshake(
    agreement_id=handshake.agreement_id,
    milestone_id=handshake.milestone_id,
    worker=AgentAttestation(
        agent_id="research-worker",
        role="worker",
        summary="Uploaded the signed brief package",
        artifact_hash="sha256:brief-bundle-v1",
    ),
    buyer=AgentAttestation(
        agent_id="manager-agent",
        role="buyer",
        summary="Reviewed and accepted the brief",
        status="accepted",
        artifact_hash="sha256:brief-bundle-v1",
    ),
    artifact_hash="sha256:brief-bundle-v1",
    summary="Dual attestation completed for milestone delivery.",
)

print(outcome.settlement_action)
```

This keeps NORNR in the handshake: create the agreement, attach both attestations, then either release or dispute from the same governed surface.

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

## Agent resume / verified profile

Use the resume generator when you want a public-ready summary of a workspace or agent lane:

```python
from agentpay import AgentResumeGenerator, NornrWallet

wallet = NornrWallet.connect(api_key="...", agent_id="research-worker")
resume = AgentResumeGenerator(wallet).build()

print(resume.public_profile_url)
print(resume.to_dict())
```

This pulls the signed trust manifest, trust profile and ecosystem directory into one portable summary:

- verification label and tier
- trust score
- verified proof / dispute / refund rates
- completed agreement count
- inferred capabilities
- public NORNR Verified profile URL

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
- customer support spend
- local MCP tools
- finance close / export-heavy workflows

## Golden path 2: MCP review flow

If you want NORNR to plug into MCP-native agent tooling, expose the wallet as a small stdio tool server:

```python
from agentpay import NornrWallet, create_mcp_server

wallet = NornrWallet.connect(api_key="replace-with-nornr-api-key", base_url="https://nornr.com")
server = create_mcp_server(wallet)

print(server.list_tools())
```

The built-in tool set includes:

- `nornr.check_spend`
- `nornr.request_spend`
- `nornr.pending_approvals`
- `nornr.balance`
- `nornr.finance_packet`

This is a good fit when you want NORNR to sit underneath Claude Desktop, Cursor, or another MCP-speaking local agent without teaching each app NORNR from scratch.

The CLI serves the tools over MCP-style stdio using `Content-Length` framing, so local MCP clients can talk to it directly:

```bash
export NORNR_API_KEY=replace-with-nornr-api-key
export NORNR_AGENT_ID=agent_123
nornr mcp manifest
nornr mcp claude-config
nornr mcp serve
```

The recommended official pack for local MCP clients is `mcp-local-tools-guarded`.

If you want a minimal operator review reference app instead of a lower-level snippet, start from [`19_mcp_review_app.py`](./examples/19_mcp_review_app.py).

## Golden path 3: browser checkout guard

For browser agents, add a purchase-aware guard before the agent clicks a checkout or fills payment details:

```python
from agentpay import BrowserCheckoutGuard, NornrWallet

wallet = NornrWallet.connect(api_key="replace-with-nornr-api-key", base_url="https://nornr.com")
guard = BrowserCheckoutGuard(wallet, blocked_domains=["stripe.com", "openai.com"])

decision = guard.guard_click(
    url="https://platform.openai.com/checkout",
    selector="button.buy-now",
    text="Buy now",
    amount=24.0,
    purpose="Renew team API credits through a browser agent",
)
```

This is intentionally framework-agnostic so you can wire it into Playwright, browser-use, or your own browser controller.

The recommended official pack for browser agents is `browser-ops-guarded`.

For checkout-like actions, passing `amount=` explicitly is still the preferred path. The browser guard can infer amount hints from DOM evidence, but high-risk taxonomies such as `checkout`, `vendor_purchase`, and `invoice_payment` now fail closed if the inferred amount is low-confidence.

For callback-style browser automation:

```python
result = guard.guard_playwright_click(
    page,
    url="https://platform.openai.com/checkout",
    selector="button.buy-now",
    text="Buy now",
    amount=24.0,
)
```

If you want stronger extraction without hard-coding the amount in your app, pass selectors for the checkout total and cart summary:

```python
result = guard.guard_playwright_click(
    page,
    url="https://platform.openai.com/checkout",
    selector="button.buy-now",
    amount=None,
    text="Buy now",
    capture_evidence=True,
    amount_selector="[data-order-total]",
    cart_selector="[data-order-summary]",
    merchant_selector="[data-merchant-name]",
)
```

If you want a minimal browser governance reference app instead of a small snippet, start from [`18_browser_checkout_app.py`](./examples/18_browser_checkout_app.py).

## Accounting bridge

NORNR already captures monthly statements, cost reports, finance packet state, and audit review context. The accounting bridge turns that into journal-friendly payloads:

```python
from agentpay import AccountingBridge, NornrWallet

wallet = NornrWallet.connect(api_key="replace-with-nornr-api-key", base_url="https://nornr.com")
batch = AccountingBridge(wallet, workspace_label="NORNR growth workspace").build_batch()

print(batch.to_quickbooks_payload())
```

Portable serializers are included for:

- QuickBooks journal payloads
- Xero manual journal payloads
- Fortnox voucher payloads

That makes it easier to build an accounting worker or webhook bridge without re-deriving NORNR activity into finance rows yourself.

If you want a webhook-aware export worker:

```python
from agentpay import AccountingWorker

worker = AccountingWorker(wallet, workspace_label="NORNR growth workspace")
result = worker.export(provider="fortnox")

print(result.exported_payload)
print(result.matched_deliveries)
```

If you want the workflow layer instead of just the export payload:

```python
from agentpay import run_weekly_finance_handoff

report = run_weekly_finance_handoff(wallet, provider="xero", workspace_label="NORNR weekly handoff")
print(report.to_summary_dict())
```

## VP of Finance controller agent

If you want a controller agent that manages other agents' budget posture, use the meta-governance helper:

```python
from agentpay import AgentOutcome, NornrWallet, VpOfFinanceController

wallet = NornrWallet.connect(api_key="replace-with-nornr-api-key", base_url="https://nornr.com")
controller = VpOfFinanceController(wallet)

review = controller.review_workspace(
    target_agent_id=wallet.agent_id,
    current_daily_limit=100.0,
    outcome=AgentOutcome(revenue_usd=900.0, leads=10, tasks_completed=31),
)

print(review.recommendations[0])
```

This lets you build a controller lane that raises, tightens, or holds budget caps based on finance packet quality, anomaly pressure, and open operator actions.

The recommended official pack for teams that want cleaner close posture around these decisions is `finance-close-export`.

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

Canonical governed execution from a request handler:

```python
from agentpay import governed_execute

record = await governed_execute(
    request,
    action_name="api-provider-call",
    amount=9,
    counterparty="openai",
    purpose="Serve one governed endpoint call",
    callback=lambda: {"ok": True},
    business_context={"routeName": "api-provider-call"},
)
```

LangGraph state integration:

```python
from agentpay import record_decision, record_handoff, record_resume

state = record_decision(state, decision)
state = record_handoff(state, run)
state = record_resume(state, approved_decision)
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

## Secondary surfaces: framework adapters

Wrapped provider calls now attach standardized NORNR business context including:

- `provider`
- `providerApi`
- `operationKind`
- `requestedModel`
- `stream`
- `toolCount`
- `toolNames`
- `messageCount`
- `inputCount`

All first-class agent tool adapters now expose the same governed operator surface:

- `nornr_spend`
- `nornr_approve`
- `nornr_balance`
- `nornr_pending_approvals`
- `nornr_finance_packet`
- `nornr_weekly_review`
- `nornr_anomaly_inbox`
- `nornr_review_bundle`

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

### PydanticAI

```python
from agentpay import NornrWallet, create_pydanticai_tools

wallet = NornrWallet.connect(api_key="replace-with-nornr-api-key", base_url="https://nornr.com")
tools = create_pydanticai_tools(
    wallet,
    agent_name="incident-copilot",
    model_name="gpt-4.1-mini",
    business_context={"workflow": "incident-response"},
)
```

If you already keep NORNR defaults in `NornrDeps`, use `create_pydanticai_tools_for(deps, ...)` instead of rebuilding the context each time.

### CrewAI

```python
from agentpay import NornrWallet, create_crewai_tools

wallet = NornrWallet.connect(api_key="replace-with-nornr-api-key", base_url="https://nornr.com")
tools = create_crewai_tools(
    wallet,
    crew_id="crew_1",
    task_id="task_7",
    role="researcher",
    business_context={"mission": "vendor-research"},
)
```

If your CrewAI integration already has a task config object, use `create_crewai_task_tools(wallet, CrewTaskConfig(...))`.

### Provider convenience wrappers

If you want provider-native entrypoints instead of the generic wrappers:

```python
from agentpay import wrap_anthropic_client, wrap_openai_client
```

- `wrap_openai_client(...)` is the shortest path for OpenAI-style `responses` and `chat.completions`
- `wrap_anthropic_client(...)` is the shortest path for Anthropic-style `messages`
- `wrap(...)` and `wrap_async(...)` still exist for mixed or custom provider SDKs

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
- [mcp_server.py](/Users/alexanderohlsson/gemin/Projekt/AIAGENTSCRYPTO/examples/python/mcp_server.py)
- [browser_checkout_guard.py](/Users/alexanderohlsson/gemin/Projekt/AIAGENTSCRYPTO/examples/python/browser_checkout_guard.py)
- [controller_agent.py](/Users/alexanderohlsson/gemin/Projekt/AIAGENTSCRYPTO/examples/python/controller_agent.py)
- [accounting_bridge.py](/Users/alexanderohlsson/gemin/Projekt/AIAGENTSCRYPTO/examples/python/accounting_bridge.py)

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
