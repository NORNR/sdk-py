import os

from agentpay import AccountingBridge, AccountingWorker, NornrWallet


wallet = NornrWallet.connect(
    api_key=os.environ["NORNR_API_KEY"],
    base_url=os.getenv("NORNR_BASE_URL", "https://nornr.com"),
)

batch = AccountingBridge(wallet, workspace_label="NORNR demo workspace").build_batch()
print(batch.to_quickbooks_payload())

worker = AccountingWorker(wallet, workspace_label="NORNR demo workspace")
print(worker.export(provider="fortnox").exported_payload)
