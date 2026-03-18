import os

from agentpay import NornrWallet, create_pydanticai_tools


def main() -> None:
    wallet = NornrWallet.connect(
        api_key=os.environ["NORNR_API_KEY"],
        base_url=os.environ.get("NORNR_BASE_URL", "https://nornr.com"),
    )

    tools = create_pydanticai_tools(
        wallet,
        business_context={
            "reason": "incident response",
            "priority": "high",
            "ticketId": "INC-402",
        },
    )

    print("Registered PydanticAI tool names:")
    for tool in tools:
        print("-", getattr(tool, "__name__", "nornr_tool"))

    print("Use these tools inside your PydanticAI agent to gate spend before provider calls start.")


if __name__ == "__main__":
    main()
