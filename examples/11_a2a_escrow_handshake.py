from agentpay import A2AEscrow, AgentAttestation, NornrWallet


wallet = NornrWallet.connect(
    api_key="replace-with-nornr-api-key",
    base_url="https://nornr.com",
    agent_id="replace-with-buyer-agent-id",
)
escrow = A2AEscrow(wallet)

handshake = escrow.create_three_way_handshake(
    buyer_agent_id=wallet.agent_id,
    worker_agent_id="worker-agent",
    worker_destination="0xworkeragent",
    title="Data cleanup engagement",
    milestone_title="Deliver signed dataset artifact",
    amount_usd=12,
)

outcome = escrow.settle_handshake(
    agreement_id=handshake.agreement_id,
    milestone_id=handshake.milestone_id,
    worker=AgentAttestation(
        agent_id="worker-agent",
        role="worker",
        summary="Submitted cleaned dataset package",
        artifact_hash="sha256:dataset-clean-v1",
    ),
    buyer=AgentAttestation(
        agent_id=wallet.agent_id,
        role="buyer",
        summary="Confirmed delivery and accepted the result",
        status="accepted",
        artifact_hash="sha256:dataset-clean-v1",
    ),
    artifact_hash="sha256:dataset-clean-v1",
    summary="Buyer and worker attestations align.",
)

print(handshake.to_summary_dict())
print(outcome.settlement_action)

