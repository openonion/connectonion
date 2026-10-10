"""
Purpose: `co mcp` — list and call the MCP servers and account connectors the user already has in Codex
LLM-Note:
  Dependencies: imports from [typer, cli/style.py, cli/typer_groups.py, command_tips.py, useful_tools/codex.py] | imported by [cli/main.py] | tested by [tests/unit/test_mcp_commands.py]
  Data flow: argv → start `codex app-server` → initialize → ephemeral thread/start (no turn, no model) → mcpServerStatus/list or mcpServer/tool/call → print rows, or the tool's own data as JSON
  State/Effects: reads only, except `call` of a tool not marked read-only with --yes, which acts as the user's connected account (send mail, create an issue)
  Integration: mcp_app is added to the root app in main.py; Codex holds every credential, co never sees one
  Errors: no codex on PATH, an unknown server or tool, a tool error → `✗ <cause>` and `Next: <command>` on stderr, exit 1
"""

import json
from contextlib import contextmanager
from functools import wraps

import typer
from rich.markup import escape

from .. import style
from ..typer_groups import _OneSuggestion
from ...useful_tools.codex import CodexAppServer, _base_command
from .command_tips import mark_next_step_named, print_tip, selected_tip

mcp_app = typer.Typer(
    cls=_OneSuggestion,
    invoke_without_command=True,
    help="Experimental: the MCP servers and account connectors you already have in Codex (Gmail, Calendar, GitHub, "
         "your own servers), called straight from the terminal: no model turn, no second login. "
         "Read-only tools run at once; any other tool only previews until --yes.",
    epilog="Example:  co mcp ls  |  co mcp tools codex_apps  |  "
           "co mcp call codex_apps gmail.search_emails '{\"query\": \"newer_than:7d\"}'",
)

JSON_HELP = "Print the same fields as JSON"


class McpError(Exception):
    def __init__(self, message: str, next_step: str):
        super().__init__(message)
        self.next_step = next_step


@mcp_app.callback()
def _mcp(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        print(ctx.get_help())


def _reported(handler):
    """An McpError becomes its cause and the one command to run next, on stderr; exit 1."""
    @wraps(handler)
    def run(*args, **kwargs):
        try:
            return handler(*args, **kwargs)
        except McpError as error:
            out = style.console(stderr=True)
            out.print(f"{style.error('✗')} {escape(str(error))}")
            out.print(style.next_line(selected_tip(error.next_step)))
            mark_next_step_named()
            raise typer.Exit(1) from None
    return run


@contextmanager
def _codex():
    """A `codex app-server` with one ephemeral thread: the thread scopes MCP calls and starts no turn."""
    command = _base_command()
    if not command:
        raise McpError("Codex is not installed; co mcp calls the servers Codex has connected",
                       "npm install -g @openai/codex && codex login")
    client = CodexAppServer(command)
    client.start()
    try:
        client.initialize()
        thread = client.request("thread/start", {"cwd": ".", "ephemeral": True})
        yield client, thread["thread"]["id"]
    finally:
        client.close()


def _servers(client, thread_id) -> list:
    servers, cursor = [], None
    while True:
        page = client.request("mcpServerStatus/list", {"threadId": thread_id, "detail": "toolsAndAuthOnly",
                                                       "cursor": cursor})
        servers += page["data"]
        cursor = page.get("nextCursor")
        if not cursor:
            return servers


def _server(servers: list, name: str) -> dict:
    for server in servers:
        if server["name"] == name:
            return server
    raise McpError(f"Codex has no MCP server named {name}", "co mcp ls")


def _read_only(tool: dict) -> bool:
    return bool((tool.get("annotations") or {}).get("readOnlyHint"))


def _dump(data) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


@mcp_app.command("ls", epilog="Example:  co mcp ls  |  co mcp ls --json")
@_reported
def ls(as_json: bool = typer.Option(False, "--json", help=JSON_HELP)):
    """Every MCP server Codex has: its auth state and how many tools it offers."""
    with _codex() as (client, thread_id):
        rows = [{"name": s["name"], "auth": s.get("authStatus"), "tools": len(s.get("tools") or {})}
                for s in _servers(client, thread_id)]
    if as_json:
        _dump(rows)
        return
    for row in rows:
        print(f"{row['name']:<28} {row['tools']:>4} tools  {row['auth']}")
    print_tip("Next: co mcp tools <server>")


@mcp_app.command("tools", epilog="Example:  co mcp tools codex_apps  |  co mcp tools codex_apps --json")
@_reported
def tools(server: str = typer.Argument(..., help="A server name from co mcp ls"),
          as_json: bool = typer.Option(False, "--json", help=JSON_HELP)):
    """One server's tools, one line each; read-only ones are marked."""
    with _codex() as (client, thread_id):
        found = _server(_servers(client, thread_id), server).get("tools") or {}
    if as_json:
        _dump(list(found.values()))
        return
    for name, tool in sorted(found.items()):
        mark = "read-only" if _read_only(tool) else "acts     "
        summary = (tool.get("description") or "").split("\n")[0][:90]
        print(f"{name:<44} {mark}  {summary}")
    print_tip(f"Next: co mcp call {server} <tool> '<json arguments>'")


@mcp_app.command("call", epilog="Example:  co mcp call codex_apps gmail.search_emails '{\"query\": \"newer_than:7d\"}'")
@_reported
def call(server: str = typer.Argument(..., help="A server name from co mcp ls"),
         tool: str = typer.Argument(..., help="A tool name from co mcp tools <server>"),
         arguments: str = typer.Argument("{}", help="The tool's arguments as a JSON object"),
         yes: bool = typer.Option(False, "--yes", help="Run a tool that is not read-only; without it this previews")):
    """Call one tool and print its own data as JSON."""
    args = json.loads(arguments)
    with _codex() as (client, thread_id):
        found = _server(_servers(client, thread_id), server).get("tools") or {}
        if tool not in found:
            raise McpError(f"{server} has no tool named {tool}", f"co mcp tools {server}")
        if not _read_only(found[tool]) and not yes:
            print(f"Would call {server} {tool} as your connected account, with:")
            _dump(args)
            print_tip(f"Next: co mcp call {server} {tool} '{arguments}' --yes")
            return
        result = client.request("mcpServer/tool/call", {"threadId": thread_id, "server": server,
                                                        "tool": tool, "arguments": args}, timeout=120)
    if result.get("isError"):
        raise McpError(" ".join(c.get("text", "") for c in result["content"]), f"co mcp tools {server} --json")
    if result.get("structuredContent") is not None:
        _dump(result["structuredContent"])
        return
    print("\n".join(c.get("text", json.dumps(c)) for c in result["content"]))
