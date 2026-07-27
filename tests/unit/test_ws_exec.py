"""Unit tests for direct tool execution (WS EXEC) — the terminal-style fast path.

Covers:
- exec_handler (connectonion/network/host/http_router.py): whitelist gate + dispatch
- run_exec (connectonion/network/host/ws_router/exec.py): the WS frame handler
- ExecResult (connectonion/network/connect.py): the client-side result type

EXEC is gated by the same .co/host.yaml permission whitelist the LLM approval
flow uses (is_tool_permitted); tests build permission dicts in that shape.
"""

import asyncio
import pytest

from connectonion import Agent, ExecResult
from connectonion.network.host.http_router import exec_handler
from connectonion.network.host.ws_router.exec import run_exec


def _echo(text: str) -> str:
    """Echo the input back."""
    return f"echo: {text}"


def _boom() -> str:
    """Always raises."""
    raise ValueError("kaboom")


def _screenshot() -> str:
    """Return a base64 image data URL like a real screenshot tool."""
    return "data:image/png;base64,iVBORw0KGgoAAAANS"


def make_factory(*tools):
    def create_agent():
        # Direct exec never touches the LLM; a fake key is enough to construct.
        return Agent("exec-test", tools=list(tools), api_key="fake_key", log=False)
    return create_agent


def allow(*tool_names):
    """Build a permission whitelist granting the given simple tool names."""
    return {name: {"allowed": True, "source": "config", "reason": "test"} for name in tool_names}


# ─────────────────────────── exec_handler: the gate ───────────────────────────

class TestExecHandlerGate:
    def test_empty_whitelist_blocks_everything(self):
        """No permissions → EXEC refused."""
        out = exec_handler(make_factory(_echo), {}, "_echo", {"text": "hi"})
        assert out["status"] == "error"
        assert "blocked" in out["error"]

    def test_tool_not_in_whitelist(self):
        """A tool outside the whitelist is refused even though it exists."""
        out = exec_handler(make_factory(_echo, _screenshot), allow("_screenshot"), "_echo", {"text": "hi"})
        assert out["status"] == "error"
        assert "not in the permission whitelist" in out["error"]

    def test_whitelisted_tool_runs(self):
        out = exec_handler(make_factory(_echo, _screenshot), allow("_echo"), "_echo", {"text": "hi"})
        assert out["status"] == "success"
        assert out["result"] == "echo: hi"

    def test_bash_command_gated_by_pattern(self):
        """A Bash(...) whitelist entry gates the actual command, not just the tool."""
        def bash(command: str) -> str:
            """Fake bash — echoes the command instead of running it."""
            return f"ran: {command}"

        perms = {"Bash(echo *)": {"allowed": True, "source": "config",
                                  "reason": "test", "when": {"command": "echo *"}}}
        ok = exec_handler(make_factory(bash), perms, "bash", {"command": "echo hi"})
        assert ok["status"] == "success"
        assert ok["result"] == "ran: echo hi"

        blocked = exec_handler(make_factory(bash), perms, "bash", {"command": "rm -rf /"})
        assert blocked["status"] == "error"
        assert "blocked" in blocked["error"]


# ─────────────────────────── exec_handler: execution ──────────────────────────

class TestExecHandlerExecution:
    def test_unknown_tool(self):
        """Whitelisted by name but not registered on the agent."""
        out = exec_handler(make_factory(_echo), allow("_nope"), "_nope", {})
        assert out["status"] == "error"
        assert "unknown tool" in out["error"]

    def test_tool_error_returned_as_data(self):
        """Tool exceptions become error results, not raised — same as the LLM loop."""
        out = exec_handler(make_factory(_boom), allow("_boom"), "_boom", {})
        assert out["status"] == "error"
        assert "kaboom" in out["error"]
        assert "duration_ms" in out

    def test_success_carries_duration(self):
        out = exec_handler(make_factory(_echo), allow("_echo"), "_echo", {"text": "x"})
        assert out["status"] == "success"
        assert isinstance(out["duration_ms"], int)

    def test_screenshot_result_is_raw_base64(self):
        """Image tools flow through unchanged — the client extracts images."""
        out = exec_handler(make_factory(_screenshot), allow("_screenshot"), "_screenshot", {})
        assert out["status"] == "success"
        assert out["result"].startswith("data:image/png;base64,")


# ────────────────────── the shared permission whitelist ───────────────────────

class TestPermissionWhitelist:
    """is_tool_permitted / load_permission_patterns — the single whitelist EXEC
    and the LLM approval flow both honor."""

    def test_simple_tool_name_allowed(self):
        from connectonion.useful_plugins.tool_approval.approval import is_tool_permitted
        ok, _ = is_tool_permitted("take_screenshot", {}, allow("take_screenshot"))
        assert ok is True

    def test_unlisted_tool_blocked(self):
        from connectonion.useful_plugins.tool_approval.approval import is_tool_permitted
        ok, reason = is_tool_permitted("delete", {}, allow("read"))
        assert ok is False
        assert "whitelist" in reason

    def test_empty_permissions_blocks(self):
        from connectonion.useful_plugins.tool_approval.approval import is_tool_permitted
        ok, reason = is_tool_permitted("read", {}, {})
        assert ok is False

    def test_co_command_allowed_by_wildcard(self):
        from connectonion.useful_plugins.tool_approval.approval import is_tool_permitted
        perms = {"Bash(co *)": {"allowed": True, "source": "config",
                                "reason": "co cli", "when": {"command": "co *"}}}
        assert is_tool_permitted("bash", {"command": "co status"}, perms)[0] is True
        assert is_tool_permitted("bash", {"command": "co auth login"}, perms)[0] is True
        # A different command that merely starts with the same letters is rejected.
        assert is_tool_permitted("bash", {"command": "cordump x"}, perms)[0] is False

    def test_bash_chain_requires_all_permitted(self):
        from connectonion.useful_plugins.tool_approval.approval import is_tool_permitted
        perms = {
            "Bash(co *)": {"allowed": True, "source": "config", "reason": "", "when": {"command": "co *"}},
            "Bash(ls *)": {"allowed": True, "source": "config", "reason": "", "when": {"command": "ls *"}},
        }
        assert is_tool_permitted("bash", {"command": "co status && ls -la"}, perms)[0] is True
        # rm is not whitelisted → whole chain rejected
        assert is_tool_permitted("bash", {"command": "co status && rm -rf /"}, perms)[0] is False

    def test_defaults_allow_co_cli_for_browser_control(self):
        """Browser remote-control goes through `co browser` (the daemon), so the
        shipped defaults whitelist the co CLI — NOT the in-process browser tool
        names, which would bypass the daemon's tab arbitration."""
        from connectonion.useful_plugins.tool_approval.approval import load_permission_patterns, is_tool_permitted
        # Point at a nonexistent .co so only the shipped template defaults load.
        perms = load_permission_patterns(co_dir="/nonexistent/.co")
        assert is_tool_permitted("bash", {"command": "co browser take_screenshot"}, perms)[0] is True
        assert is_tool_permitted("bash", {"command": "co status"}, perms)[0] is True
        # In-process browser tool names are deliberately NOT whitelisted.
        assert is_tool_permitted("take_screenshot", {}, perms)[0] is False
        assert is_tool_permitted("go_to", {"url": "https://x.com"}, perms)[0] is False
        # Still blocks something dangerous by default.
        assert is_tool_permitted("bash", {"command": "rm -rf /"}, perms)[0] is False


# ─────────────────────────── run_exec: the WS frame ───────────────────────────

class TestRunExec:
    @pytest.mark.asyncio
    async def test_dispatches_and_replies(self):
        sent = []

        async def send(msg):
            sent.append(msg)

        def ws_exec(tool, args):
            assert tool == "_echo"
            return {"status": "success", "result": "echo: hey", "duration_ms": 1}

        await run_exec({"type": "EXEC", "exec_id": "e1", "tool": "_echo", "args": {"text": "hey"}},
                       send, {"ws_exec": ws_exec})

        assert len(sent) == 1
        assert sent[0]["type"] == "EXEC_RESULT"
        assert sent[0]["exec_id"] == "e1"
        assert sent[0]["tool"] == "_echo"
        assert sent[0]["result"] == "echo: hey"

    @pytest.mark.asyncio
    async def test_missing_tool_name(self):
        sent = []

        async def send(msg):
            sent.append(msg)

        await run_exec({"type": "EXEC", "exec_id": "e2"}, send, {"ws_exec": lambda t, a: {}})
        assert sent[0]["status"] == "error"
        assert "tool required" in sent[0]["error"]

    @pytest.mark.asyncio
    async def test_handler_exception_becomes_error_frame(self):
        """A raising handler must still produce an EXEC_RESULT — a background task's
        raise would otherwise be invisible and hang the client until timeout."""
        sent = []

        async def send(msg):
            sent.append(msg)

        def ws_exec(tool, args):
            raise RuntimeError("handler blew up")

        await run_exec({"type": "EXEC", "exec_id": "e3", "tool": "_echo"},
                       send, {"ws_exec": ws_exec})
        assert sent[0]["type"] == "EXEC_RESULT"
        assert sent[0]["status"] == "error"
        assert "handler blew up" in sent[0]["error"]


# ─────────────────────────── ExecResult: the client type ──────────────────────

class TestExecResult:
    def test_ok_true_on_success(self):
        assert ExecResult(text="out", status="success").ok is True

    def test_ok_false_on_error(self):
        assert ExecResult(text="", status="error", error="boom").ok is False

    def test_images_extracted_from_text(self):
        r = ExecResult(text="prefix data:image/png;base64,ABC123 suffix", status="success")
        assert r.images == ["data:image/png;base64,ABC123"]

    def test_no_images_in_plain_text(self):
        assert ExecResult(text="just text", status="success").images == []

    def test_multiple_images(self):
        r = ExecResult(text="data:image/png;base64,AA data:image/jpeg;base64,BB", status="success")
        assert len(r.images) == 2
