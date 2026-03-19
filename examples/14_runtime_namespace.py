from agentpay import NornrRuntime


runtime = NornrRuntime.connect(
    api_key="replace-with-nornr-api-key",
    base_url="https://nornr.com",
)

record = runtime.execute(
    action_name="runtime-example",
    amount=3,
    to="openai",
    counterparty="openai",
    purpose="Run one governed action from the runtime namespace",
    callback=lambda: {"ok": True},
    receipt_id="receipt_123",
)

print(record.to_summary_dict())
