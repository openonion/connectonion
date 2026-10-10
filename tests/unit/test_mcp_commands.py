"""co mcp against a fake `codex app-server`: list servers, list tools, call one.

LLM-Note: Tests for connectonion/cli/commands/mcp_commands.py. The fake replaces CodexAppServer
and answers the three methods co mcp sends (thread/start, mcpServerStatus/list,
mcpServer/tool/call), recording each request so a test can assert what was sent, and that a
preview of a tool that is not read-only sent no call.
"""

import json

import pytest
from typer.testing import CliRunner

import importlib
from connectonion.cli.main import app

codex = importlib.import_module("connectonion.useful_tools.codex")

SEARCH = {"name": "gmail.search_emails", "description": "Search Gmail for emails matching a query.",
          "annotations": {"readOnlyHint": True}}
SEND = {"name": "gmail.send_email", "description": "Send an email.",
        "annotations": {"readOnlyHint": False, "openWorldHint": True}}
SERVERS = [
    {"name": "codex_apps", "authStatus": "bearerToken",
     "tools": {"gmail.search_emails": SEARCH, "gmail.send_email": SEND}},
    {"name": "vercel", "authStatus": "notLoggedIn", "tools": {}},
]
FOUND = {"emails": [{"id": "m1", "thread_id": "t1", "subject": "Deck"}]}


class FakeServer:
    def __init__(self, command, **kwargs):
        self.sent = SENT

    def start(self):
        pass

    def initialize(self, timeout=60):
        pass

    def close(self, force=False):
        pass

    def request(self, method, params, timeout=60):
        self.sent.append((method, params))
        if method == "thread/start":
            return {"thread": {"id": "th1"}}
        if method == "mcpServerStatus/list":
            return {"data": SERVERS, "nextCursor": None}
        if method == "mcpServer/tool/call":
            return {"content": [{"type": "text", "text": "Action completed."}],
                    "structuredContent": FOUND, "isError": False}
        raise AssertionError(method)


SENT = []


@pytest.fixture(autouse=True)
def fake_codex(monkeypatch):
    SENT.clear()
    monkeypatch.setattr(codex, "CodexAppServer", FakeServer)
    monkeypatch.setattr(codex, "_base_command", lambda: ["codex", "app-server"])


def run(*args):
    return CliRunner().invoke(app, ["mcp", *args])


def test_ls_names_each_server_its_tool_count_and_auth():
    result = run("ls")
    assert result.exit_code == 0, result.output
    assert "codex_apps" in result.output and "2 tools" in result.output
    assert "vercel" in result.output and "notLoggedIn" in result.output


def test_the_session_is_ephemeral_so_codex_history_stays_clean():
    run("ls")
    start = dict(SENT)["thread/start"]
    assert start["ephemeral"] is True


def test_tools_lists_each_tool_and_marks_what_only_reads():
    result = run("tools", "codex_apps")
    assert result.exit_code == 0, result.output
    lines = {line.split()[0]: line for line in result.output.splitlines() if line.startswith("gmail.")}
    assert "read-only" in lines["gmail.search_emails"] and "read-only" not in lines["gmail.send_email"]


def test_a_read_only_tool_is_called_and_its_data_printed_as_is():
    result = run("call", "codex_apps", "gmail.search_emails", '{"query": "newer_than:7d"}')
    assert result.exit_code == 0, result.output
    assert ("mcpServer/tool/call", {"threadId": "th1", "server": "codex_apps", "tool": "gmail.search_emails",
                                    "arguments": {"query": "newer_than:7d"}}) in SENT
    assert json.loads(result.stdout) == FOUND


def test_a_tool_that_can_change_something_only_previews_until_yes():
    preview = run("call", "codex_apps", "gmail.send_email", '{"to": "bo@x.y"}')
    assert preview.exit_code == 0, preview.output
    assert "--yes" in preview.output
    assert not [m for m, _ in SENT if m == "mcpServer/tool/call"]
    done = run("call", "codex_apps", "gmail.send_email", '{"to": "bo@x.y"}', "--yes")
    assert done.exit_code == 0, done.output
    assert [m for m, _ in SENT if m == "mcpServer/tool/call"] == ["mcpServer/tool/call"]


def test_an_unknown_tool_names_the_command_that_lists_them():
    result = run("call", "codex_apps", "gmail.nope")
    assert result.exit_code == 1
    assert "co mcp tools codex_apps" in result.output


def test_an_unknown_server_names_the_command_that_lists_them():
    result = run("tools", "linear")
    assert result.exit_code == 1
    assert "co mcp ls" in result.output


def test_without_codex_it_says_so(monkeypatch):
    monkeypatch.setattr(codex, "_base_command", lambda: None)
    result = run("ls")
    assert result.exit_code == 1
    assert "Codex" in result.output
