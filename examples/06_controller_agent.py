import os

from agentpay import AgentOutcome, NornrWallet, VpOfFinanceController


wallet = NornrWallet.connect(
    api_key=os.environ["NORNR_API_KEY"],
    base_url=os.getenv("NORNR_BASE_URL", "https://nornr.com"),
)

controller = VpOfFinanceController(wallet)
review = controller.review_workspace(
    target_agent_id=wallet.agent_id,
    current_daily_limit=100.0,
    outcome=AgentOutcome(revenue_usd=620.0, leads=12, tasks_completed=19),
)

print(review.recommendations[0])
