import os

from agentpay import NornrRuntime


runtime = NornrRuntime.connect(
    api_key=os.environ["NORNR_API_KEY"],
    base_url=os.getenv("NORNR_BASE_URL", "https://nornr.com"),
)

record = runtime.execute(
    action_name="runtime-mini-app",
    amount=9.5,
    to="openai",
    counterparty="openai",
    purpose="Run one governed provider action from a reference mini app",
    callback=lambda: {"jobId": "job_123", "status": "completed"},
    receipt_id="receipt_runtime_mini_app",
    evidence={"surface": "mini-app", "workflow": "runtime"},
)

print(record.to_summary_dict())
