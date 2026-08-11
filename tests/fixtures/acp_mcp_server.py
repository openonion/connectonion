"""Small real MCP v2 stdio server used by ACP integration tests."""

import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer

server = MCPServer("connectonion-acp-test")

if pid_file := os.environ.get("ACP_MCP_PID_FILE"):
    Path(pid_file).write_text(str(os.getpid()), encoding="utf-8")


@server.tool()
def process_context(value: str) -> dict[str, object]:
    """Return non-secret launch context and the supplied value."""

    return {
        "value": value,
        "cwd": str(Path.cwd()),
        "explicit": os.environ.get("ACP_MCP_EXPLICIT"),
        "parent_secret_present": "ACP_MCP_PARENT_SECRET" in os.environ,
        "pid": os.getpid(),
    }


@server.tool()
def write_marker(path: str, content: str) -> str:
    """Write a marker used to prove approval happens before side effects."""

    Path(path).write_text(content, encoding="utf-8")
    return "written"


if __name__ == "__main__":
    server.run("stdio")
