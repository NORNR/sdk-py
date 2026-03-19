# Releasing

## Default release cadence

- cut a release when the public README, examples, and PyPI package are all in sync
- keep `CHANGELOG.md` updated before tagging
- keep `UPGRADING.md` updated when install, import, or preferred public helpers change

## Pre-release checklist

From the repo root:

```bash
python3 scripts/python-sdk-setup-dev.py
python3 scripts/python-sdk-release-check.py
```

That runs:

- mypy over `src/agentpay`
- Python example compilation
- full `npm run test:python-sdk`
- wheel/sdist build
- `twine check dist/*`

GitHub Actions also runs the same release-check path in:

- [python-sdk-release-check.yml](/Users/alexanderohlsson/gemin/Projekt/AIAGENTSCRYPTO/.github/workflows/python-sdk-release-check.yml)

## Versioning

- patch: fixture breadth, docs polish, wrapper ergonomics, non-breaking helper additions
- minor: new public records, new integrations, new golden-path helpers
- major: removals or breaking API changes

## Public package rules

- always spell both names when publishing install docs:
  - distribution: `nornr-agentpay`
  - import: `agentpay`
- keep PyPI metadata, `README.md`, `CHANGELOG.md`, and `UPGRADING.md` aligned before upload
