import os

from agentpay import NornrWallet, run_weekly_finance_handoff


wallet = NornrWallet.connect(
    api_key=os.environ["NORNR_API_KEY"],
    base_url=os.getenv("NORNR_BASE_URL", "https://nornr.com"),
)

report = run_weekly_finance_handoff(wallet, provider="xero", workspace_label="NORNR weekly handoff")
print(report.to_summary_dict())
