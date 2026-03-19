from agentpay import OpenClawGovernanceAdapter, build_mock_wallet


wallet = build_mock_wallet(
    {
        ("POST", "/api/payments/intents"): {
            "paymentIntent": {
                "id": "pi_openclaw_1",
                "status": "queued",
                "amountUsd": 12,
                "counterparty": "openai",
                "purpose": "OpenClaw paid action",
            },
            "requiresApproval": True,
        },
        "/api/anomalies": {
            "items": [{"id": "anomaly_openclaw_1", "status": "open", "severity": "medium", "reason": "OpenClaw autonomy triggered anomaly review.", "counterparty": "openai", "amountUsd": 12}]
        },
        "/api/workspace/intent-timeline": {
            "summary": {"count": 1},
            "items": [{"paymentIntentId": "pi_openclaw_1", "status": "queued"}],
        },
        "/api/audit/review": {
            "financePacket": {
                "score": 92,
                "headline": "Finance packet ready",
                "openActions": [],
                "packetHistory": [],
                "lastHandoff": None,
            }
        },
        "/api/workspace/weekly-review": {
            "summary": {"queuedIntents": 1},
            "highlights": ["Queue the risky action before execution."],
            "finance": {"readiness": "ready"},
        },
    },
    bootstrap={
        "workspace": {"id": "ws_openclaw", "label": "OpenClaw Workspace"},
        "agents": [{"id": "agent_openclaw", "label": "Autonomous inbox agent"}],
        "wallet": {"balanceSummary": {"availableUsd": 100, "reservedUsd": 0, "pendingSettlementUsd": 0, "totalFeesUsd": 0}},
        "apiKey": {"key": "nornr_test_key"},
        "approvals": [{"id": "approval_openclaw_1", "paymentIntentId": "pi_openclaw_1", "status": "pending"}],
    },
)

adapter = OpenClawGovernanceAdapter(wallet)
print(
    adapter.preflight_paid_action(
        action="purchase",
        amount_usd=12,
        counterparty="openai",
        purpose="OpenClaw paid action",
        context={"skillName": "nornr-governance", "runId": "run_openclaw_1", "autonomous": True},
    ).to_dict()
)
print(adapter.review_bundle(counterparty="openai"))
