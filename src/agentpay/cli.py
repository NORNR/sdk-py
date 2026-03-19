from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence
import webbrowser

from .auth import DEFAULT_BASE_URL, clear_login, load_login, login_url, save_login
from .client import AgentPayClient, AuthenticationError
from .mcp import create_mcp_server
from .pricing import estimate_cost
from .client import Wallet


def _write_env_file(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nornr", description="NORNR Python SDK helper CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    login = subparsers.add_parser("login", help="Store NORNR credentials locally and optionally write an env file")
    login.add_argument("--api-key", dest="api_key")
    login.add_argument("--base-url", default=DEFAULT_BASE_URL)
    login.add_argument("--path")
    login.add_argument("--auth-path")
    login.add_argument("--open-browser", action="store_true")

    init_cmd = subparsers.add_parser("init", help="Create a starter NORNR env file")
    init_cmd.add_argument("--owner")
    init_cmd.add_argument("--daily-limit", default="50")
    init_cmd.add_argument("--base-url", default=DEFAULT_BASE_URL)
    init_cmd.add_argument("--path", default=".env.nornr")

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

    mcp = subparsers.add_parser("mcp", help="Expose NORNR as an MCP-friendly local tool server")
    mcp_subparsers = mcp.add_subparsers(dest="mcp_command", required=True)

    mcp_serve = mcp_subparsers.add_parser("serve", help="Run the NORNR MCP stdio server")
    mcp_serve.add_argument("--base-url", default=DEFAULT_BASE_URL)
    mcp_serve.add_argument("--api-key")
    mcp_serve.add_argument("--auth-path")
    mcp_serve.add_argument("--agent-id")
    mcp_serve.add_argument("--server-name", default="nornr")

    mcp_manifest = mcp_subparsers.add_parser("manifest", help="Print the NORNR MCP tool manifest")
    mcp_manifest.add_argument("--base-url", default=DEFAULT_BASE_URL)
    mcp_manifest.add_argument("--api-key")
    mcp_manifest.add_argument("--auth-path")
    mcp_manifest.add_argument("--agent-id")
    mcp_manifest.add_argument("--server-name", default="nornr")

    mcp_config = mcp_subparsers.add_parser("claude-config", help="Print a Claude Desktop config snippet for the NORNR MCP server")
    mcp_config.add_argument("--base-url", default=DEFAULT_BASE_URL)
    mcp_config.add_argument("--api-key")
    mcp_config.add_argument("--auth-path")
    mcp_config.add_argument("--agent-id")
    mcp_config.add_argument("--server-name", default="nornr")
    return parser


def _resolve_base_url(base_url: str | None) -> str:
    env_base_url = os.getenv("NORNR_BASE_URL")
    if base_url and base_url != DEFAULT_BASE_URL:
        return base_url
    return env_base_url or base_url or DEFAULT_BASE_URL


def _resolve_api_key(api_key: str | None, base_url: str, auth_path: str | None) -> str:
    if api_key:
        return api_key
    env_api_key = os.getenv("NORNR_API_KEY")
    if env_api_key:
        return env_api_key
    resolved_auth_path = auth_path or os.getenv("NORNR_AUTH_PATH")
    profile = load_login(base_url=base_url, path=Path(resolved_auth_path) if resolved_auth_path else None)
    if not profile:
        raise AuthenticationError("Missing NORNR api key. Run `nornr login` first or pass --api-key.")
    return profile.api_key


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _resolve_wallet(api_key: str | None, base_url: str, auth_path: str | None, agent_id: str | None = None) -> Wallet:
    resolved_base_url = _resolve_base_url(base_url)
    resolved_key = _resolve_api_key(api_key, resolved_base_url, auth_path)
    resolved_agent_id = agent_id or os.getenv("NORNR_AGENT_ID")
    return Wallet.connect(api_key=resolved_key, base_url=resolved_base_url, agent_id=resolved_agent_id)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "login":
        api_key = args.api_key or input("NORNR API key: ").strip()
        auth_path = save_login(api_key, base_url=args.base_url, path=Path(args.auth_path) if args.auth_path else None)
        if args.path:
            path = Path(args.path)
            _write_env_file(path, {"NORNR_API_KEY": api_key, "NORNR_BASE_URL": args.base_url})
            print(f"Wrote NORNR credentials to {path}")
        print(f"Stored NORNR login at {auth_path}")
        if args.open_browser:
            url = login_url(args.base_url)
            webbrowser.open(url)
            print(f"Opened {url}")
        return 0

    if args.command == "init":
        owner = args.owner or input("Default NORNR owner/agent name: ").strip() or "research-agent"
        path = Path(args.path)
        _write_env_file(
            path,
            {
                "NORNR_BASE_URL": args.base_url,
                "NORNR_OWNER": owner,
                "NORNR_DAILY_LIMIT_USD": str(args.daily_limit),
                "NORNR_API_KEY": "replace-me",
            },
        )
        print(f"Wrote NORNR starter env to {path}")
        return 0

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
        _print_json(estimate.__dict__)
        return 0

    if args.command == "debug":
        resolved_base_url = _resolve_base_url(args.base_url)
        api_key = _resolve_api_key(args.api_key, resolved_base_url, args.auth_path)
        client = AgentPayClient(base_url=resolved_base_url, api_key=api_key)
        bootstrap = client.get_bootstrap()
        approvals = bootstrap.get("approvals", []) or []
        approval = next((item for item in approvals if item.get("id") == args.resource_id or item.get("paymentIntentId") == args.resource_id), None)
        timeline = client.get_intent_timeline()
        timeline_entry = next((item for item in timeline.get("items", []) if item.get("id") == args.resource_id), None)
        payload = {
            "approval": approval,
            "timeline": timeline_entry,
            "resourceId": args.resource_id,
            "debugHint": "Use the control room URL in ApprovalRequiredError for the full UI flow.",
        }
        _print_json(payload)
        return 0

    if args.command == "rescue":
        resolved_base_url = _resolve_base_url(args.base_url)
        api_key = _resolve_api_key(args.api_key, resolved_base_url, args.auth_path)
        client = AgentPayClient(base_url=resolved_base_url, api_key=api_key)
        action = args.action or input("Action [approve/reject]: ").strip().lower()
        if action == "approve":
            _print_json(client.approve_intent(args.approval_id, {"comment": "Approved from NORNR rescue CLI"}))
            return 0
        if action == "reject":
            _print_json(client.reject_intent(args.approval_id, {"comment": "Rejected from NORNR rescue CLI"}))
            return 0
        raise SystemExit("Unknown action")

    if args.command == "mcp":
        if args.mcp_command == "serve":
            wallet = _resolve_wallet(args.api_key, args.base_url, args.auth_path, getattr(args, "agent_id", None))
            server = create_mcp_server(wallet, server_name=args.server_name)
            server.run_stdio()
            return 0
        server = create_mcp_server(None, server_name=args.server_name)
        if args.mcp_command == "manifest":
            _print_json(server.build_manifest())
            return 0
        if args.mcp_command == "claude-config":
            command_args = ["mcp", "serve", "--server-name", args.server_name]
            if args.agent_id or os.getenv("NORNR_AGENT_ID"):
                command_args.extend(["--agent-id", args.agent_id or os.getenv("NORNR_AGENT_ID", "")])
            if args.auth_path or os.getenv("NORNR_AUTH_PATH"):
                command_args.extend(["--auth-path", args.auth_path or os.getenv("NORNR_AUTH_PATH", "")])
            resolved_base_url = _resolve_base_url(args.base_url)
            env = {
                "NORNR_BASE_URL": resolved_base_url,
            }
            resolved_api_key = args.api_key or os.getenv("NORNR_API_KEY")
            if resolved_api_key:
                env["NORNR_API_KEY"] = resolved_api_key
            _print_json(
                server.build_claude_desktop_config(
                    args=command_args,
                    env=env,
                )
            )
            return 0

    parser.error("Unknown command")
    return 1


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
