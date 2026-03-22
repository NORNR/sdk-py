from __future__ import annotations

import os
from typing import Any

from .cli_support import print_json, resolve_base_url, resolve_wallet
from .mcp import create_mcp_server


def build_cursor_rules(*, server_name: str, client_label: str = "Cursor") -> str:
    return "\n".join(
        [
            "Treat NORNR as the control layer before consequential execution.",
            "",
            f"If {client_label} can use MCP server \"{server_name}\" for a terminal command, file mutation, package install, browser step or external API call that can create spend, vendor consequence or policy drift, ask NORNR first and wait for the decision.",
            "",
            "Approved means the lane can proceed.",
            "Queued, blocked or anomalous means stop and keep the work inside review.",
            "",
            "Do not reroute around NORNR with a direct shell command, another tool path or a second attempt if the original request was queued or blocked.",
            "",
            f"The goal is not to reduce capability. It is to keep {client_label} useful while NORNR remains the decision, review and audit path for consequential execution.",
        ]
    )


def handle_mcp_command(args: Any, *, resolve_wallet_fn: Any | None = None) -> int:
    wallet_resolver = resolve_wallet_fn or resolve_wallet
    if args.mcp_command == "serve":
        wallet = wallet_resolver(args.api_key, args.base_url, args.auth_path, getattr(args, "agent_id", None))
        server = create_mcp_server(wallet, server_name=args.server_name)
        server.run_stdio()
        return 0

    server = create_mcp_server(None, server_name=args.server_name)
    if args.mcp_command == "manifest":
        print_json(server.build_manifest())
        return 0

    if args.mcp_command == "cursor-rules":
        print(build_cursor_rules(server_name=args.server_name))
        return 0

    if args.mcp_command in {"claude-config", "cursor-config", "generic-config", "agent-zero-config"}:
        command_args = ["mcp", "serve", "--server-name", args.server_name]
        if args.agent_id or os.getenv("NORNR_AGENT_ID"):
            command_args.extend(["--agent-id", args.agent_id or os.getenv("NORNR_AGENT_ID", "")])
        if args.auth_path or os.getenv("NORNR_AUTH_PATH"):
            command_args.extend(["--auth-path", args.auth_path or os.getenv("NORNR_AUTH_PATH", "")])
        resolved_base_url = resolve_base_url(args.base_url)
        env = {
            "NORNR_BASE_URL": resolved_base_url,
        }
        resolved_api_key = args.api_key or os.getenv("NORNR_API_KEY")
        if resolved_api_key:
            env["NORNR_API_KEY"] = resolved_api_key
        print_json(
            server.build_claude_desktop_config(
                args=command_args,
                env=env,
            )
        )
        return 0

    raise SystemExit("Unknown MCP command")
