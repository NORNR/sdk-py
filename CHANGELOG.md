# Changelog

## Unreleased

- added provider-specific wrapper entrypoints for OpenAI-style and Anthropic-style clients
- added reference mini apps for governed runtime, browser checkout governance, and MCP review flow
- expanded realistic golden-path fixtures for provider and browser flows
- moved reusable provider/browser test doubles into a shared fixture library
- added a repeatable Python SDK release-check path for build, tests, and `twine check`
- added a dedicated GitHub Actions workflow for Python SDK release-check automation
- expanded realistic provider/browser fixtures with Stripe checkout, mixed-cart totals, invoice-reference noise, and tool-call streaming shapes
- added an Agent Zero MCP-first reference app and tightened public Python quickstart docs
- tightened package docs around install/import naming and golden-path onboarding

## 0.1.0

- first public PyPI release as `nornr-agentpay`
- full sync/async parity for the core wallet/client surface
- governed execution runtime with explicit handoff, resume, and evidence APIs
- MCP server, browser governance helpers, framework kits, A2A escrow, OpenClaw adapter
- typed operator, finance, trust, and policy records
- provider wrappers now attach richer normalized business context
- FastAPI helpers include a canonical `governed_execute(...)` path
- LangGraph helpers include run metadata, handoff, and resume state helpers
