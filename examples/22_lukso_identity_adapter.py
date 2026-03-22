from agentpay import LuksoIdentityAdapter, NornrClient


client = NornrClient(base_url="https://nornr.com", api_key="replace-with-nornr-api-key")
adapter = LuksoIdentityAdapter(client)

identity = adapter.normalize_identity(
    {
        "universalProfileAddress": "0x1111111111111111111111111111111111111111",
        "keyManagerAddress": "0x2222222222222222222222222222222222222222",
        "chainId": "42",
        "network": "lukso",
        "profileMetadata": {
            "name": "NORNR Research Worker",
            "description": "Universal Profile used as root of trust for one governed agent lane.",
        },
        "controllers": [
            {
                "address": "0x3333333333333333333333333333333333333333",
                "label": "research-agent-controller",
                "permissions": ["CALL", "SUPER_CALL"],
                "allowedCalls": ["execute(bytes)"],
            }
        ],
    }
)

binding = adapter.build_binding(
    identity,
    mandate={
        "scopeLabel": "research procurement lane",
        "ownerMandate": "vendor-side changes above threshold require review",
    },
    policy_decision={
        "policyId": "research-safe",
        "decisionMode": "review_required",
    },
    counterparty_scope={
        "allowedCounterparties": ["openai", "anthropic"],
        "reviewRequiredAboveUsd": 25,
    },
    audit_export={
        "artifactKind": "trust_manifest_binding",
        "proofNote": "LUKSO holds authority context; NORNR still owns release, review and export.",
    },
)

print(binding.to_dict())
