from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence
import webbrowser

from .auth import DEFAULT_BASE_URL, clear_login, login_url, save_login
from .client import AgentPayClient
from .cli_mcp import handle_mcp_command
from .cli_product import (
    handle_authoring_publish_command,
    handle_authoring_replay_command,
    handle_counterparty_inspect_command,
    handle_doctor_command,
    handle_packet_diff_command,
    handle_verify_command,
    handle_verify_manifest_command,
)
from .cli_starters import handle_init_command, write_env_file
from .cli_support import current_month, previous_month, print_json, resolve_api_key, resolve_base_url, resolve_client, resolve_wallet
from .generated_contract import ROLLOUT_MODES
from .pricing import estimate_cost
from .scopes import credential_posture, recommended_scopes, review_scopes
from .templates import scenario_templates

_resolve_wallet = resolve_wallet


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nornr", description="NORNR Python SDK helper CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    login = subparsers.add_parser("login", help="Store NORNR credentials locally and optionally write an env file")
    login.add_argument("--api-key", dest="api_key")
    login.add_argument("--base-url", default=DEFAULT_BASE_URL)
    login.add_argument("--path")
    login.add_argument("--auth-path")
    login.add_argument("--open-browser", action="store_true")

    init_cmd = subparsers.add_parser("init", help="Create a starter NORNR env file and one installable lane scaffold")
    init_cmd.add_argument(
        "surface",
        nargs="?",
        default="runtime",
        choices=["runtime", "generic", "provider-wrapper", "openai-agents", "langgraph", "mcp", "browser-guard"],
    )
    init_cmd.add_argument("--owner")
    init_cmd.add_argument("--daily-limit", default="50")
    init_cmd.add_argument("--base-url", default=DEFAULT_BASE_URL)
    init_cmd.add_argument("--path", default=".env.nornr")
    init_cmd.add_argument("--starter-path")
    init_cmd.add_argument("--output-dir")
    init_cmd.add_argument("--server-name", default="nornr")
    init_cmd.add_argument("--mcp-client", choices=["claude", "cursor", "agent-zero", "generic"], default="claude")
    init_cmd.add_argument("--print", action="store_true")

    logout = subparsers.add_parser("logout", help="Remove locally stored NORNR credentials")
    logout.add_argument("--auth-path")

    estimate = subparsers.add_parser("estimate-cost", help="Estimate model spend before a provider call")
    estimate.add_argument("--model", required=True)
    estimate.add_argument("--prompt")
    estimate.add_argument("--prompt-tokens", type=int)
    estimate.add_argument("--completion-tokens", type=int, default=0)

    debug = subparsers.add_parser("debug", help="Inspect a queued approval or recent decision from the terminal")
    debug.add_argument("resource_id")
    debug.add_argument("--base-url", default=DEFAULT_BASE_URL)
    debug.add_argument("--api-key")
    debug.add_argument("--auth-path")

    rescue = subparsers.add_parser("rescue", help="Approve or reject a queued approval from the terminal")
    rescue.add_argument("approval_id")
    rescue.add_argument("--base-url", default=DEFAULT_BASE_URL)
    rescue.add_argument("--api-key")
    rescue.add_argument("--auth-path")
    rescue.add_argument("--action", choices=["approve", "reject"])

    mcp = subparsers.add_parser("mcp", help="Expose NORNR as the control layer for consequential MCP tool execution")
    mcp_subparsers = mcp.add_subparsers(dest="mcp_command", required=True)

    mcp_serve = mcp_subparsers.add_parser("serve", help="Run the NORNR MCP control server over stdio")
    mcp_serve.add_argument("--base-url", default=DEFAULT_BASE_URL)
    mcp_serve.add_argument("--api-key")
    mcp_serve.add_argument("--auth-path")
    mcp_serve.add_argument("--agent-id")
    mcp_serve.add_argument("--server-name", default="nornr")

    mcp_manifest = mcp_subparsers.add_parser("manifest", help="Print the NORNR MCP control manifest with tools, resources and prompts")
    mcp_manifest.add_argument("--base-url", default=DEFAULT_BASE_URL)
    mcp_manifest.add_argument("--api-key")
    mcp_manifest.add_argument("--auth-path")
    mcp_manifest.add_argument("--agent-id")
    mcp_manifest.add_argument("--server-name", default="nornr")

    mcp_config = mcp_subparsers.add_parser("claude-config", help="Print a Claude Desktop config snippet for the NORNR MCP control server")
    mcp_config.add_argument("--base-url", default=DEFAULT_BASE_URL)
    mcp_config.add_argument("--api-key")
    mcp_config.add_argument("--auth-path")
    mcp_config.add_argument("--agent-id")
    mcp_config.add_argument("--server-name", default="nornr")

    mcp_cursor_config = mcp_subparsers.add_parser("cursor-config", help="Print a Cursor MCP config snippet for the NORNR control server")
    mcp_cursor_config.add_argument("--base-url", default=DEFAULT_BASE_URL)
    mcp_cursor_config.add_argument("--api-key")
    mcp_cursor_config.add_argument("--auth-path")
    mcp_cursor_config.add_argument("--agent-id")
    mcp_cursor_config.add_argument("--server-name", default="nornr")

    mcp_cursor_rules = mcp_subparsers.add_parser("cursor-rules", help="Print a .cursorrules block that keeps Cursor behind the NORNR MCP control layer")
    mcp_cursor_rules.add_argument("--base-url", default=DEFAULT_BASE_URL)
    mcp_cursor_rules.add_argument("--api-key")
    mcp_cursor_rules.add_argument("--auth-path")
    mcp_cursor_rules.add_argument("--agent-id")
    mcp_cursor_rules.add_argument("--server-name", default="nornr")

    mcp_generic_config = mcp_subparsers.add_parser("generic-config", help="Print a generic MCP client config snippet for the NORNR control server")
    mcp_generic_config.add_argument("--base-url", default=DEFAULT_BASE_URL)
    mcp_generic_config.add_argument("--api-key")
    mcp_generic_config.add_argument("--auth-path")
    mcp_generic_config.add_argument("--agent-id")
    mcp_generic_config.add_argument("--server-name", default="nornr")

    mcp_agent_zero_config = mcp_subparsers.add_parser("agent-zero-config", help="Print an Agent Zero-ready config snippet for the NORNR control server")
    mcp_agent_zero_config.add_argument("--base-url", default=DEFAULT_BASE_URL)
    mcp_agent_zero_config.add_argument("--api-key")
    mcp_agent_zero_config.add_argument("--auth-path")
    mcp_agent_zero_config.add_argument("--agent-id")
    mcp_agent_zero_config.add_argument("--server-name", default="nornr")

    scopes = subparsers.add_parser("scopes", help="Print least-privilege NORNR scope presets or review an existing key posture")
    scopes.add_argument("--surface", default="mcp")
    scopes.add_argument("--granted", nargs="*")

    scenarios = subparsers.add_parser("scenario-templates", help="Print reusable scenario templates for the SDK")
    scenarios.add_argument("--name")

    simulate = subparsers.add_parser("simulate-policy", help="Run a policy simulation from the CLI")
    simulate.add_argument("--template-id", required=True)
    simulate.add_argument("--rollout-mode", choices=ROLLOUT_MODES, default="shadow")
    simulate.add_argument("--base-url", default=DEFAULT_BASE_URL)
    simulate.add_argument("--api-key")
    simulate.add_argument("--auth-path")
    simulate.add_argument("--agent-id")

    doctor = subparsers.add_parser("doctor", help="Check whether NORNR can reach the core control, proof and finance surfaces")
    doctor.add_argument("--base-url", default=DEFAULT_BASE_URL)
    doctor.add_argument("--api-key")
    doctor.add_argument("--auth-path")
    doctor.add_argument("--month")

    replay_pack = subparsers.add_parser("replay-pack", help="Replay one named policy pack from the CLI")
    replay_pack.add_argument("pack_id")
    replay_pack.add_argument("--mode", default="shadow")
    replay_pack.add_argument("--base-url", default=DEFAULT_BASE_URL)
    replay_pack.add_argument("--api-key")
    replay_pack.add_argument("--auth-path")

    compare_close = subparsers.add_parser("compare-close", help="Compare two finance close packets by month")
    compare_close.add_argument("--left")
    compare_close.add_argument("--right")
    compare_close.add_argument("--base-url", default=DEFAULT_BASE_URL)
    compare_close.add_argument("--api-key")
    compare_close.add_argument("--auth-path")

    verify_manifest = subparsers.add_parser("verify-manifest", help="Verify one signed close-bundle manifest")
    verify_manifest.add_argument("--path")
    verify_manifest.add_argument("--month")
    verify_manifest.add_argument("--base-url", default=DEFAULT_BASE_URL)
    verify_manifest.add_argument("--api-key")
    verify_manifest.add_argument("--auth-path")

    verify = subparsers.add_parser("verify", help="Verify one trust or finance artifact from a local file or live NORNR route")
    verify.add_argument("--artifact", choices=["close-manifest", "audit-manifest", "trust-manifest"], default="close-manifest")
    verify.add_argument("--path")
    verify.add_argument("--month")
    verify.add_argument("--base-url", default=DEFAULT_BASE_URL)
    verify.add_argument("--api-key")
    verify.add_argument("--auth-path")

    packet_diff = subparsers.add_parser("packet-diff", help="Compare two monthly close packets with lineage and completeness context")
    packet_diff.add_argument("--left")
    packet_diff.add_argument("--right")
    packet_diff.add_argument("--base-url", default=DEFAULT_BASE_URL)
    packet_diff.add_argument("--api-key")
    packet_diff.add_argument("--auth-path")

    counterparty_inspect = subparsers.add_parser("counterparty-inspect", help="Inspect one counterparty profile from the registry")
    counterparty_inspect.add_argument("profile")
    counterparty_inspect.add_argument("--base-url", default=DEFAULT_BASE_URL)
    counterparty_inspect.add_argument("--api-key")
    counterparty_inspect.add_argument("--auth-path")

    authoring_replay = subparsers.add_parser("authoring-replay", help="Replay one saved policy authoring draft")
    authoring_replay.add_argument("draft_id")
    authoring_replay.add_argument("--base-url", default=DEFAULT_BASE_URL)
    authoring_replay.add_argument("--api-key")
    authoring_replay.add_argument("--auth-path")

    authoring_publish = subparsers.add_parser("authoring-publish", help="Publish one saved policy authoring draft into the current lane")
    authoring_publish.add_argument("draft_id")
    authoring_publish.add_argument("--rollout-mode", choices=ROLLOUT_MODES, default="suggested")
    authoring_publish.add_argument("--publish-note")
    authoring_publish.add_argument("--base-url", default=DEFAULT_BASE_URL)
    authoring_publish.add_argument("--api-key")
    authoring_publish.add_argument("--auth-path")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "login":
        api_key = args.api_key or input("NORNR API key: ").strip()
        auth_path = save_login(api_key, base_url=args.base_url, path=Path(args.auth_path) if args.auth_path else None)
        if args.path:
            path = Path(args.path)
            write_env_file(path, {"NORNR_API_KEY": api_key, "NORNR_BASE_URL": args.base_url})
            print(f"Wrote NORNR credentials to {path}")
        print(f"Stored NORNR login at {auth_path}")
        if args.open_browser:
            url = login_url(args.base_url)
            webbrowser.open(url)
            print(f"Opened {url}")
        return 0

    if args.command == "init":
        return handle_init_command(args)

    if args.command == "logout":
        clear_login(Path(args.auth_path) if args.auth_path else None)
        print("Cleared stored NORNR login")
        return 0

    if args.command == "estimate-cost":
        estimate = estimate_cost(
            model=args.model,
            prompt=args.prompt,
            prompt_tokens=args.prompt_tokens,
            completion_tokens=args.completion_tokens,
        )
        print_json(estimate.__dict__)
        return 0

    if args.command == "scopes":
        template = recommended_scopes(args.surface)
        scope_payload = {"template": template.to_dict()}
        if args.granted:
            scope_payload["review"] = review_scopes(args.granted, surface=args.surface).to_dict()
            scope_payload["credentialPosture"] = credential_posture(args.granted).to_dict()
        print_json(scope_payload)
        return 0

    if args.command == "scenario-templates":
        items = scenario_templates()
        if args.name:
            items = [item for item in items if item.name == args.name]
        print_json([item.to_dict() for item in items])
        return 0

    if args.command == "debug":
        resolved_base_url = resolve_base_url(args.base_url)
        api_key = resolve_api_key(args.api_key, resolved_base_url, args.auth_path)
        client = AgentPayClient(base_url=resolved_base_url, api_key=api_key)
        bootstrap = client.get_bootstrap()
        approvals = bootstrap.get("approvals", []) or []
        approval = next((item for item in approvals if item.get("id") == args.resource_id or item.get("paymentIntentId") == args.resource_id), None)
        timeline = client.get_intent_timeline()
        timeline_entry = next((item for item in timeline.get("items", []) if item.get("id") == args.resource_id), None)
        payload: dict[str, object] = {
            "approval": approval,
            "timeline": timeline_entry,
            "resourceId": args.resource_id,
            "debugHint": "Use the control room URL in ApprovalRequiredError for the full UI flow.",
        }
        print_json(payload)
        return 0

    if args.command == "rescue":
        resolved_base_url = resolve_base_url(args.base_url)
        api_key = resolve_api_key(args.api_key, resolved_base_url, args.auth_path)
        client = AgentPayClient(base_url=resolved_base_url, api_key=api_key)
        action = args.action or input("Action [approve/reject]: ").strip().lower()
        if action == "approve":
            print_json(client.approve_intent(args.approval_id, {"comment": "Approved from NORNR rescue CLI"}))
            return 0
        if action == "reject":
            print_json(client.reject_intent(args.approval_id, {"comment": "Rejected from NORNR rescue CLI"}))
            return 0
        raise SystemExit("Unknown action")

    if args.command == "simulate-policy":
        wallet = resolve_wallet(args.api_key, args.base_url, args.auth_path, getattr(args, "agent_id", None))
        print_json(wallet.simulate_policy(template_id=args.template_id, rollout_mode=args.rollout_mode).to_dict())
        return 0

    if args.command == "doctor":
        return handle_doctor_command(args)

    if args.command == "replay-pack":
        wallet = resolve_wallet(args.api_key, args.base_url, args.auth_path, None)
        print_json(wallet.replay_policy_pack(args.pack_id, mode=args.mode).to_dict())
        return 0

    if args.command == "compare-close":
        left = args.left or current_month()
        right = args.right or previous_month(left)
        client = resolve_client(args.api_key, args.base_url, args.auth_path)
        print_json(client.compare_close_bundles(left=left, right=right))
        return 0

    if args.command == "verify-manifest":
        return handle_verify_manifest_command(args)

    if args.command == "verify":
        return handle_verify_command(args)

    if args.command == "packet-diff":
        return handle_packet_diff_command(args)

    if args.command == "counterparty-inspect":
        return handle_counterparty_inspect_command(args)

    if args.command == "authoring-replay":
        return handle_authoring_replay_command(args)

    if args.command == "authoring-publish":
        return handle_authoring_publish_command(args)

    if args.command == "mcp":
        return handle_mcp_command(args, resolve_wallet_fn=_resolve_wallet)

    parser.error("Unknown command")
    return 1


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
