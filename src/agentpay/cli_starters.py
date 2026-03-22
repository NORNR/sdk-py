from __future__ import annotations

import json
from pathlib import Path
import textwrap
from typing import Any


def write_env_file(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def normalized_surface(surface: str) -> str:
    if surface == "generic":
        return "runtime"
    return surface


def starter_path_for(surface: str) -> str:
    surface = normalized_surface(surface)
    if surface == "provider-wrapper":
        return "nornr.provider_wrapper.py"
    if surface == "mcp":
        return "nornr.mcp.json"
    if surface == "langgraph":
        return "nornr.langgraph.py"
    if surface == "openai-agents":
        return "nornr.openai_agents.py"
    if surface == "browser-guard":
        return "nornr.browser_guard.py"
    return "nornr.runtime.py"


def recommended_pack_id(surface: str) -> str:
    surface = normalized_surface(surface)
    if surface == "provider-wrapper":
        return "research-safe"
    if surface == "openai-agents":
        return "research-safe"
    if surface == "langgraph":
        return "research-safe"
    if surface == "browser-guard":
        return "browser-ops-guarded"
    if surface == "mcp":
        return "mcp-local-tools-guarded"
    return "research-safe"


def starter_readme(
    surface: str,
    *,
    owner: str,
    env_path: str,
    starter_path: str,
    recommended_pack: str,
    base_url: str,
) -> str:
    surface = normalized_surface(surface)
    lane_label = {
        "runtime": "Governed runtime lane",
        "provider-wrapper": "Spend-aware provider wrapper",
        "openai-agents": "OpenAI Agents governed tool lane",
        "langgraph": "LangGraph approval branch",
        "mcp": "MCP control server",
        "browser-guard": "Browser checkout governance",
    }.get(surface, "Governed runtime lane")
    next_steps = {
        "runtime": [
            "Set NORNR_API_KEY in .env.nornr.",
            f"Run the starter file in {starter_path}.",
            f"Replay {recommended_pack} in shadow mode first.",
            "Prove one approved, queued or blocked lane before widening.",
        ],
        "provider-wrapper": [
            "Set NORNR_API_KEY in .env.nornr.",
            f"Wrap one existing provider client from {starter_path}.",
            "Use one max-spend cap as the ingress, not the final control model.",
            "Upgrade the first consequential lane into governed runtime, MCP or browser control once the wrapper proves useful.",
        ],
        "openai-agents": [
            "Set NORNR_API_KEY in .env.nornr.",
            f"Attach the generated tools from {starter_path} to one consequential tool lane.",
            f"Replay {recommended_pack} in shadow mode first.",
            "Export the proof packet once the lane clears one real decision.",
        ],
        "langgraph": [
            "Set NORNR_API_KEY in .env.nornr.",
            f"Wire the stateful action from {starter_path} into one graph edge that can spend or call a paid tool.",
            f"Replay {recommended_pack} in shadow mode first.",
            "Keep the first rollout to one owner and one branch.",
        ],
        "mcp": [
            "Set NORNR_API_KEY in .env.nornr or run `nornr login` first.",
            f"Paste the generated config from {starter_path} into one MCP client.",
            f"Replay {recommended_pack} in shadow mode first.",
            "Keep MCP authority to one consequential local tool lane first.",
        ],
        "browser-guard": [
            "Set NORNR_API_KEY in .env.nornr.",
            f"Wire the checkout guard from {starter_path} into one paid browser step.",
            f"Replay {recommended_pack} in shadow mode first.",
            "Use one merchant and one review owner before widening.",
        ],
    }.get(surface, [])
    verification_steps = {
        "runtime": [
            "Run `nornr doctor` and confirm bootstrap, policy packs and close bundle all load.",
            f"Run `nornr replay-pack {recommended_pack} --mode shadow` before you enforce the lane.",
            "Confirm one proof packet and one review bundle exist before widening.",
        ],
        "provider-wrapper": [
            "Keep the wrapper on one provider lane first.",
            "Use `nornr doctor` before assuming credentials or proof are correct.",
            "Upgrade into a governed runtime, MCP or browser lane once one real decision survives.",
        ],
        "openai-agents": [
            "Confirm one tool call queues, approves or blocks before attaching more tools.",
            "Run `nornr doctor` after credentials are set.",
            "Export the first proof packet before you widen the tool surface.",
        ],
        "langgraph": [
            "Confirm the first governed edge replays cleanly before widening the graph.",
            "Use `nornr authoring-replay <draft-id>` once you save the first candidate pack.",
            "Keep one owner on the branch until the packet path is boring.",
        ],
        "mcp": [
            "Generate client config from the helper command instead of editing JSON blind.",
            "Run `nornr doctor` after the server is wired into Claude or Cursor.",
            "Confirm one local tool returns queued review before granting more MCP reach.",
        ],
        "browser-guard": [
            "Keep one merchant and one checkout step under control first.",
            "Run `nornr doctor` before widening beyond the first merchant path.",
            "Confirm the receipt trail survives after the first governed checkout settles.",
        ],
    }.get(surface, [])
    failure_recovery = {
        "runtime": "If proof does not appear, replay the lane before widening runtime autonomy.",
        "provider-wrapper": "If the wrapper is useful but thin, upgrade the first consequential lane into governed runtime, MCP or browser control.",
        "openai-agents": "If tool calls feel noisy, keep only one consequential tool attached and replay in shadow mode.",
        "langgraph": "If review feels vague, move the governed edge closer to the final paid action and keep one branch only.",
        "mcp": "If the client cannot connect, rerun the helper config command and confirm NORNR_API_KEY or `nornr login` first.",
        "browser-guard": "If merchant posture is weak, stop and review the counterparty before adding more checkout volume.",
    }.get(surface, "If the lane is thin, narrow it before you widen it.")

    bullet_lines = "\n".join(f"1. {step}" if index == 0 else f"{index + 1}. {step}" for index, step in enumerate(next_steps))
    verification_lines = "\n".join(f"1. {step}" if index == 0 else f"{index + 1}. {step}" for index, step in enumerate(verification_steps))
    return textwrap.dedent(
        f"""\
        # NORNR Starter Bundle

        Lane: {lane_label}
        Owner: {owner}
        Base URL: {base_url}

        Files in this bundle:
        - `{env_path}` for NORNR credentials and owner defaults
        - `{starter_path}` for the first governed lane scaffold
        - `nornr.starter.json` for starter metadata and recommended pack posture

        Recommended pack:
        - `{recommended_pack}`

        Next steps:
        {bullet_lines}

        Verification before widening:
        {verification_lines}

        If the starter still fails:
        - {failure_recovery}
        """
    ).strip() + "\n"


def starter_manifest(surface: str, *, owner: str, base_url: str, recommended_pack: str, env_path: str, starter_path: str) -> dict[str, object]:
    verify_commands = {
        "runtime": ["nornr doctor", f"nornr replay-pack {recommended_pack} --mode shadow", "nornr verify --artifact close-manifest"],
        "provider-wrapper": ["nornr doctor", "nornr estimate-cost --model gpt-5-mini --prompt-tokens 1000 --completion-tokens 300"],
        "openai-agents": ["nornr doctor", f"nornr replay-pack {recommended_pack} --mode shadow", "nornr verify --artifact trust-manifest"],
        "langgraph": ["nornr doctor", "nornr authoring-replay <draft-id>", "nornr packet-diff --left 2026-03 --right 2026-02"],
        "mcp": ["nornr doctor", "nornr mcp claude-config --server-name nornr", f"nornr replay-pack {recommended_pack} --mode shadow"],
        "browser-guard": ["nornr doctor", f"nornr replay-pack {recommended_pack} --mode shadow", "nornr counterparty-inspect <merchant>"],
    }.get(normalized_surface(surface), ["nornr doctor"])
    failure_recovery = {
        "runtime": "Replay the lane and keep one counterparty, one threshold and one owner.",
        "provider-wrapper": "Keep the wrapper thin and promote the first consequential lane into a governed control path.",
        "openai-agents": "Reduce to one consequential tool lane and verify one defended record lands.",
        "langgraph": "Move the governed edge closer to the final paid action and keep one branch only.",
        "mcp": "Regenerate config with the helper command and verify credentials before editing client JSON manually.",
        "browser-guard": "Keep one merchant path only until review and receipt survival are both boring.",
    }.get(normalized_surface(surface), "Narrow the lane before widening it.")
    return {
        "surface": normalized_surface(surface),
        "owner": owner,
        "baseUrl": base_url,
        "recommendedPolicyPack": recommended_pack,
        "envFile": env_path,
        "starterFile": starter_path,
        "verifyCommands": verify_commands,
        "failureRecovery": failure_recovery,
        "nextMove": "Prove one governed lane and one defended packet before widening autonomy.",
    }


def starter_blueprint(surface: str, *, owner: str, base_url: str, daily_limit: str, server_name: str, mcp_client: str) -> tuple[dict[str, str], str]:
    surface = normalized_surface(surface)
    env_values = {
        "NORNR_BASE_URL": base_url,
        "NORNR_OWNER": owner,
        "NORNR_DAILY_LIMIT_USD": str(daily_limit),
        "NORNR_API_KEY": "replace-me",
    }

    if surface == "openai-agents":
        return (
            env_values,
            f"""from agentpay import Wallet, create_openai_agents_tools

wallet = Wallet.create(
    owner="{owner}",
    daily_limit={daily_limit},
    require_approval_above=20,
    base_url="{base_url}",
)

tools = create_openai_agents_tools(wallet)

print("Attach these NORNR tools to one consequential OpenAI Agents lane:")
for name in sorted(tools):
    print("-", name)
""",
        )

    if surface == "provider-wrapper":
        return (
            env_values,
            f"""from openai import OpenAI
from agentpay import NornrWallet, create_spend_aware_openai_client

wallet = NornrWallet.connect(
    api_key="replace-me",
    base_url="{base_url}",
)

client = create_spend_aware_openai_client(
    OpenAI(),
    wallet=wallet,
    max_spend_usd={daily_limit},
)

print("Use the wrapped client for the first paid provider lane only.")
""",
        )

    if surface == "langgraph":
        return (
            env_values,
            f"""from agentpay import Wallet

wallet = Wallet.connect(
    api_key="replace-me",
    base_url="{base_url}",
)

simulation = wallet.simulate_policy(template_id="mcp-local-tool", rollout_mode="shadow")
print(simulation.to_dict())
""",
        )

    if surface == "mcp":
        return (
            env_values,
            json.dumps(
                {
                    "mcpServers": {
                        server_name: {
                            "command": "nornr",
                            "args": [
                                "mcp",
                                "serve",
                                "--server-name",
                                server_name,
                            ],
                            "env": {
                                "NORNR_BASE_URL": base_url,
                                "NORNR_API_KEY": "replace-me",
                            },
                            "client": mcp_client,
                        }
                    }
                },
                indent=2,
            )
            + "\n",
        )

    if surface == "browser-guard":
        return (
            env_values,
            f"""from agentpay import BrowserCheckoutGuard, Wallet

wallet = Wallet.connect(
    api_key="replace-me",
    base_url="{base_url}",
)

guard = BrowserCheckoutGuard(wallet)
print("Keep the first browser-governed lane to one merchant:", guard)
""",
        )

    return (
        env_values,
        f"""from agentpay import Wallet

wallet = Wallet.create(
    owner="{owner}",
    daily_limit={daily_limit},
    require_approval_above=20,
    base_url="{base_url}",
)

decision = wallet.pay(amount=5, to="demo-vendor", purpose="one governed lane")
print(decision.to_dict())
""",
    )


def handle_init_command(args: Any) -> int:
    surface = normalized_surface(args.surface)
    owner = args.owner or input("Default NORNR owner/agent name: ").strip() or "research-agent"
    requested_output_dir = Path(args.output_dir) if args.output_dir else None
    path = (requested_output_dir / Path(args.path).name) if requested_output_dir else Path(args.path)
    env_values, starter = starter_blueprint(
        surface,
        owner=owner,
        base_url=args.base_url,
        daily_limit=str(args.daily_limit),
        server_name=args.server_name,
        mcp_client=args.mcp_client,
    )
    starter_path = (requested_output_dir / Path(args.starter_path or starter_path_for(surface)).name) if requested_output_dir else Path(args.starter_path or starter_path_for(surface))
    recommended_pack = recommended_pack_id(surface)
    if requested_output_dir:
        requested_output_dir.mkdir(parents=True, exist_ok=True)
    else:
        requested_output_dir = Path.cwd()
    write_env_file(path, env_values)
    starter_path.parent.mkdir(parents=True, exist_ok=True)
    starter_path.write_text(starter, encoding="utf-8")
    manifest_path = requested_output_dir / "nornr.starter.json"
    manifest_path.write_text(
        json.dumps(
            starter_manifest(
                surface,
                owner=owner,
                base_url=args.base_url,
                recommended_pack=recommended_pack,
                env_path=path.name if args.output_dir else str(path),
                starter_path=starter_path.name if args.output_dir else str(starter_path),
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    readme_path = requested_output_dir / "README.nornr.md"
    readme_path.write_text(
        starter_readme(
            surface,
            owner=owner,
            env_path=path.name if args.output_dir else str(path),
            starter_path=starter_path.name if args.output_dir else str(starter_path),
            recommended_pack=recommended_pack,
            base_url=args.base_url,
        ),
        encoding="utf-8",
    )
    print(f"Wrote NORNR starter env to {path}")
    print(f"Wrote {surface} starter to {starter_path}")
    print(f"Wrote starter manifest to {manifest_path}")
    print(f"Wrote starter README to {readme_path}")
    if surface == "mcp":
        print("Recommended policy pack: mcp-local-tools-guarded")
        print("Recommended rollout: shadow mode first, then one consequential local tools lane.")
    if args.print:
        print("\n---\n")
        print(starter)
    return 0
