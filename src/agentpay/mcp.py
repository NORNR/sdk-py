from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, BinaryIO, Callable, Mapping

from .client import AgentPayError, Wallet, _find_pending_approval

JSONRPC_VERSION = "2.0"
DEFAULT_MCP_PROTOCOL_VERSION = "2024-11-05"
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602


def _json_default(value: Any) -> Any:
    if hasattr(value, "to_summary_dict"):
        return value.to_summary_dict()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return value


def _json_text(payload: Any) -> str:
    return json.dumps(payload, default=_json_default, sort_keys=True)


def _json_bytes(payload: Any) -> bytes:
    return _json_text(payload).encode("utf-8")


def _build_result(message_id: Any, result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": message_id,
        "result": dict(result),
    }


def _build_error(message_id: Any, code: int, message: str, *, data: Any | None = None) -> dict[str, Any]:
    error = {
        "code": code,
        "message": message,
    }
    if data is not None:
        error["data"] = data
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": message_id,
        "error": error,
    }


class McpProtocolError(Exception):
    def __init__(self, code: int, message: str, *, data: Any | None = None, message_id: Any | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.data = data
        self.message_id = message_id

    def to_response(self, *, message_id: Any | None = None) -> dict[str, Any]:
        return _build_error(message_id if message_id is not None else self.message_id, self.code, str(self), data=self.data)


@dataclass(frozen=True)
class McpToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class McpTool:
    """Small MCP-friendly tool description."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Any]

    def call(self, arguments: Mapping[str, Any] | None = None) -> Any:
        return self.handler(dict(arguments or {}))


TOOL_DEFINITIONS: tuple[McpToolDefinition, ...] = (
    McpToolDefinition(
        name="nornr.check_spend",
        description="Dry-run a governed spend decision before the agent commits to a paid action.",
        input_schema={
            "type": "object",
            "properties": {
                "intent": {"type": "string"},
                "cost": {"type": "number"},
                "counterparty": {"type": "string"},
                "budget_tags": {"type": "object"},
                "business_context": {"type": "object"},
            },
            "required": ["intent", "cost", "counterparty"],
        },
    ),
    McpToolDefinition(
        name="nornr.request_spend",
        description="Request or preview governed spend in NORNR before the downstream tool or provider is called.",
        input_schema={
            "type": "object",
            "properties": {
                "amount": {"type": "number"},
                "to": {"type": "string"},
                "counterparty": {"type": "string"},
                "purpose": {"type": "string"},
                "dry_run": {"type": "boolean"},
                "budget_tags": {"type": "object"},
                "business_context": {"type": "object"},
            },
            "required": ["amount", "counterparty"],
        },
    ),
    McpToolDefinition(
        name="nornr.approve_spend",
        description="Approve a pending NORNR spend decision by approval id or payment intent id.",
        input_schema={
            "type": "object",
            "properties": {
                "approval_id": {"type": "string"},
                "payment_intent_id": {"type": "string"},
                "comment": {"type": "string"},
            },
        },
    ),
    McpToolDefinition(
        name="nornr.reject_spend",
        description="Reject a pending NORNR spend decision by approval id.",
        input_schema={
            "type": "object",
            "properties": {
                "approval_id": {"type": "string"},
                "comment": {"type": "string"},
            },
            "required": ["approval_id"],
        },
    ),
    McpToolDefinition(
        name="nornr.pending_approvals",
        description="List pending approvals for this NORNR workspace.",
        input_schema={"type": "object", "properties": {}},
    ),
    McpToolDefinition(
        name="nornr.balance",
        description="Return the current NORNR wallet balance and reserved funds.",
        input_schema={"type": "object", "properties": {}},
    ),
    McpToolDefinition(
        name="nornr.finance_packet",
        description="Return the current finance packet summary for the workspace.",
        input_schema={"type": "object", "properties": {}},
    ),
    McpToolDefinition(
        name="nornr.weekly_review",
        description="Return the weekly review summary for the governed workspace.",
        input_schema={"type": "object", "properties": {}},
    ),
    McpToolDefinition(
        name="nornr.intent_timeline",
        description="Return the recent governed intent timeline for the workspace.",
        input_schema={"type": "object", "properties": {}},
    ),
)


def list_mcp_tool_specs() -> list[dict[str, Any]]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.input_schema,
        }
        for tool in TOOL_DEFINITIONS
    ]


def list_mcp_resources() -> list[dict[str, Any]]:
    return [
        {
            "uri": "nornr://finance-packet",
            "name": "Finance Packet",
            "description": "Current finance packet attached to the governed workspace.",
            "mimeType": "application/json",
        },
        {
            "uri": "nornr://weekly-review",
            "name": "Weekly Review",
            "description": "Current weekly review summary for the workspace.",
            "mimeType": "application/json",
        },
        {
            "uri": "nornr://intent-timeline",
            "name": "Intent Timeline",
            "description": "Recent governed intent timeline for the workspace.",
            "mimeType": "application/json",
        },
        {
            "uri": "nornr://pending-approvals",
            "name": "Pending Approvals",
            "description": "Pending approval queue for the governed workspace.",
            "mimeType": "application/json",
        },
    ]


def create_mcp_tools(wallet: Wallet) -> list[McpTool]:
    """Expose NORNR spend controls as lightweight MCP tools."""

    def check_spend(arguments: dict[str, Any]) -> dict[str, Any]:
        intent = str(arguments.get("intent") or "Agent action")
        cost = float(arguments.get("cost") or 0)
        counterparty = str(arguments.get("counterparty") or "external")
        decision = wallet.check(
            intent=intent,
            cost=cost,
            counterparty=counterparty,
            budget_tags=arguments.get("budget_tags"),
            business_context=arguments.get("business_context"),
        )
        return decision.to_dict()

    def request_spend(arguments: dict[str, Any]) -> dict[str, Any]:
        amount = float(arguments.get("amount") or 0)
        counterparty = str(arguments.get("counterparty") or arguments.get("to") or "external")
        to = str(arguments.get("to") or counterparty)
        decision = wallet.pay(
            amount=amount,
            to=to,
            counterparty=counterparty,
            purpose=arguments.get("purpose"),
            budget_tags=arguments.get("budget_tags"),
            dry_run=bool(arguments.get("dry_run", False)),
            business_context=arguments.get("business_context"),
            replay_context={"source": "mcp.request_spend"},
        )
        return decision.to_dict()

    def approve_spend(arguments: dict[str, Any]) -> dict[str, Any]:
        approval_id = arguments.get("approval_id")
        payment_intent_id = arguments.get("payment_intent_id")
        comment = arguments.get("comment")
        if approval_id:
            return wallet.client.approve_intent(str(approval_id), {"comment": comment} if comment else {})
        if payment_intent_id:
            bootstrap = wallet.refresh()
            approval = _find_pending_approval(bootstrap, str(payment_intent_id))
            if not approval:
                raise AgentPayError("No pending approval found for payment intent")
            return wallet.client.approve_intent(approval["id"], {"comment": comment} if comment else {})
        raise ValueError("approve_spend requires approval_id or payment_intent_id")

    def reject_spend(arguments: dict[str, Any]) -> dict[str, Any]:
        approval_id = str(arguments.get("approval_id") or "")
        if not approval_id:
            raise ValueError("reject_spend requires approval_id")
        comment = arguments.get("comment")
        return wallet.reject(approval_id, comment=comment)

    def pending_approvals(arguments: dict[str, Any]) -> list[dict[str, Any]]:
        _ = arguments
        return [approval.to_dict() for approval in wallet.pending_approvals()]

    def balance(arguments: dict[str, Any]) -> dict[str, Any]:
        _ = arguments
        return wallet.balance().to_dict()

    def finance_packet(arguments: dict[str, Any]) -> dict[str, Any]:
        _ = arguments
        return wallet.finance_packet().to_dict()

    def weekly_review(arguments: dict[str, Any]) -> dict[str, Any]:
        _ = arguments
        return wallet.weekly_review().to_dict()

    def intent_timeline(arguments: dict[str, Any]) -> dict[str, Any]:
        _ = arguments
        return wallet.timeline().to_dict()

    handlers = {
        "nornr.check_spend": check_spend,
        "nornr.request_spend": request_spend,
        "nornr.approve_spend": approve_spend,
        "nornr.reject_spend": reject_spend,
        "nornr.pending_approvals": pending_approvals,
        "nornr.balance": balance,
        "nornr.finance_packet": finance_packet,
        "nornr.weekly_review": weekly_review,
        "nornr.intent_timeline": intent_timeline,
    }
    return [
        McpTool(
            name=tool.name,
            description=tool.description,
            input_schema=tool.input_schema,
            handler=handlers[tool.name],
        )
        for tool in TOOL_DEFINITIONS
    ]


def _read_framed_message(stream: BinaryIO) -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = stream.readline()
        if line == b"":
            if not headers:
                return None
            raise McpProtocolError(INVALID_REQUEST, "Unexpected EOF while reading MCP headers.")
        if line in (b"\r\n", b"\n"):
            break
        if b":" not in line:
            raise McpProtocolError(INVALID_REQUEST, "Malformed MCP header line.")
        raw_name, raw_value = line.decode("ascii", errors="strict").split(":", 1)
        headers[raw_name.strip().lower()] = raw_value.strip()

    if "content-length" not in headers:
        raise McpProtocolError(INVALID_REQUEST, "Missing Content-Length header.")
    try:
        content_length = int(headers["content-length"])
    except ValueError as exc:
        raise McpProtocolError(INVALID_REQUEST, "Invalid Content-Length header.") from exc
    if content_length < 0:
        raise McpProtocolError(INVALID_REQUEST, "Negative Content-Length header is invalid.")

    body = stream.read(content_length)
    if len(body) != content_length:
        raise McpProtocolError(INVALID_REQUEST, "Unexpected EOF while reading MCP body.")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise McpProtocolError(PARSE_ERROR, "Could not parse MCP JSON payload.") from exc
    if not isinstance(payload, Mapping):
        raise McpProtocolError(INVALID_REQUEST, "MCP payload must be a JSON object.")
    return dict(payload)


def _write_framed_message(stream: BinaryIO, payload: Mapping[str, Any]) -> None:
    body = _json_bytes(payload)
    stream.write(f"Content-Length: {len(body)}\r\nContent-Type: application/json\r\n\r\n".encode("ascii"))
    stream.write(body)
    stream.flush()


class NornrMcpServer:
    """Minimal stdio MCP-style server for local agent tooling."""

    def __init__(self, wallet: Wallet | None, *, server_name: str = "nornr-mcp", version: str = "0.1.0") -> None:
        self.wallet = wallet
        self.server_name = server_name
        self.version = version
        self._tools = {tool.name: tool for tool in create_mcp_tools(wallet)} if wallet is not None else {}

    def list_tools(self) -> list[dict[str, Any]]:
        return list_mcp_tool_specs()

    def list_resources(self) -> list[dict[str, Any]]:
        return list_mcp_resources()

    def build_manifest(self) -> dict[str, Any]:
        return {
            "server": {
                "name": self.server_name,
                "version": self.version,
            },
            "capabilities": {
                "tools": self.list_tools(),
                "resources": self.list_resources(),
            },
        }

    def build_claude_desktop_config(
        self,
        *,
        command: str = "nornr",
        args: list[str] | None = None,
        env: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        return {
            "mcpServers": {
                self.server_name: {
                    "command": command,
                    "args": list(args or ["mcp", "serve"]),
                    "env": dict(env or {}),
                }
            }
        }

    def call_tool(self, name: str, arguments: Mapping[str, Any] | None = None) -> Any:
        if self.wallet is None:
            raise RuntimeError("NORNR MCP tools require an authenticated wallet connection.")
        if name not in self._tools:
            raise KeyError(f"Unknown NORNR MCP tool: {name}")
        return self._tools[name].call(arguments)

    def read_resource(self, uri: str) -> Any:
        if self.wallet is None:
            raise RuntimeError("NORNR MCP resources require an authenticated wallet connection.")
        if uri == "nornr://finance-packet":
            return self.wallet.finance_packet().to_dict()
        if uri == "nornr://weekly-review":
            return self.wallet.weekly_review().to_dict()
        if uri == "nornr://intent-timeline":
            return self.wallet.timeline().to_dict()
        if uri == "nornr://pending-approvals":
            return [approval.to_dict() for approval in self.wallet.pending_approvals()]
        raise KeyError(f"Unknown NORNR MCP resource: {uri}")

    def handle_message(self, message: Mapping[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        msg_id = message.get("id")
        params = message.get("params") or {}
        if not isinstance(method, str) or not method:
            raise McpProtocolError(INVALID_REQUEST, "MCP message is missing a valid method.", message_id=msg_id)
        if not isinstance(params, Mapping):
            raise McpProtocolError(INVALID_PARAMS, "MCP params must be a JSON object.", message_id=msg_id)
        params = dict(params)
        if method == "initialize":
            protocol_version = params.get("protocolVersion") if isinstance(params.get("protocolVersion"), str) else DEFAULT_MCP_PROTOCOL_VERSION
            return _build_result(
                msg_id,
                {
                    "protocolVersion": protocol_version,
                    "serverInfo": {"name": self.server_name, "version": self.version},
                    "capabilities": {"tools": {"listChanged": False}},
                },
            )
        if method == "notifications/initialized":
            return None
        if method == "ping":
            return _build_result(msg_id, {})
        if method == "tools/list":
            return _build_result(msg_id, {"tools": self.list_tools()})
        if method == "resources/list":
            return _build_result(msg_id, {"resources": self.list_resources()})
        if method == "resources/read":
            uri = params.get("uri")
            if not isinstance(uri, str) or not uri:
                raise McpProtocolError(INVALID_PARAMS, "resources/read requires a string uri.", message_id=msg_id)
            try:
                resource_payload = self.read_resource(uri)
            except Exception as exc:
                return _build_result(
                    msg_id,
                    {
                        "contents": [{"uri": uri, "mimeType": "text/plain", "text": f"{type(exc).__name__}: {exc}"}],
                        "isError": True,
                    },
                )
            return _build_result(
                msg_id,
                {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "application/json",
                            "text": _json_text(resource_payload),
                        }
                    ]
                },
            )
        if method == "tools/call":
            tool_name = params.get("name")
            if not isinstance(tool_name, str) or not tool_name:
                raise McpProtocolError(INVALID_PARAMS, "tools/call requires a string tool name.", message_id=msg_id)
            arguments = params.get("arguments")
            if arguments is not None and not isinstance(arguments, Mapping):
                raise McpProtocolError(INVALID_PARAMS, "tools/call arguments must be a JSON object.", message_id=msg_id)
            try:
                result = self.call_tool(tool_name, arguments)
            except Exception as exc:
                return _build_result(
                    msg_id,
                    {
                        "content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}],
                        "isError": True,
                    },
                )
            return _build_result(
                msg_id,
                {"content": [{"type": "text", "text": _json_text(result)}]},
            )
        raise McpProtocolError(METHOD_NOT_FOUND, f"Unsupported method: {method}", message_id=msg_id)

    def run_stdio(self, *, stdin: BinaryIO | None = None, stdout: BinaryIO | None = None) -> None:
        stream_in = stdin or sys.stdin.buffer
        stream_out = stdout or sys.stdout.buffer
        while True:
            try:
                message = _read_framed_message(stream_in)
            except McpProtocolError as exc:
                _write_framed_message(stream_out, exc.to_response())
                continue
            if message is None:
                break
            try:
                response = self.handle_message(message)
            except McpProtocolError as exc:
                response = exc.to_response(message_id=message.get("id"))
            if response is not None:
                _write_framed_message(stream_out, response)


def create_mcp_server(wallet: Wallet | None, *, server_name: str = "nornr-mcp", version: str = "0.1.0") -> NornrMcpServer:
    """Create a minimal MCP-ready stdio server around a NORNR wallet."""

    return NornrMcpServer(wallet, server_name=server_name, version=version)
