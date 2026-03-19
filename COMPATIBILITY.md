# Compatibility Policy

- Python support starts at `3.9`
- public import path is `agentpay`
- public distribution name is `nornr-agentpay`
- docs and examples should always spell both names explicitly when install steps are shown
- minor releases may add new helpers, records, and integrations
- breaking API changes should be reserved for a major version bump
- deprecations should be documented in `README.md` and `UPGRADING.md` before removal
- the preferred public golden paths are governed runtime, browser checkout governance, and MCP review flow
- provider-specific convenience wrappers may be added in minor releases when they reduce ambiguity without changing the underlying generic wrappers
