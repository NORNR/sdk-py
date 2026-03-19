from agentpay import AgentResumeGenerator, NornrWallet


wallet = NornrWallet.connect(
    api_key="replace-with-nornr-api-key",
    base_url="https://nornr.com",
    agent_id="replace-with-agent-id",
)
resume = AgentResumeGenerator(wallet).build()
print(resume.to_dict())

