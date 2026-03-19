import os

from agentpay import NornrWallet, run_monthly_close


wallet = NornrWallet.connect(
    api_key=os.environ["NORNR_API_KEY"],
    base_url=os.getenv("NORNR_BASE_URL", "https://nornr.com"),
)

report = run_monthly_close(wallet, provider="fortnox", workspace_label="NORNR finance close")
print(report.to_summary_dict())
