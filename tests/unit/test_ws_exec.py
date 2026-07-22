"""Unit tests for direct tool execution (WS EXEC) — the terminal-style fast path.

Covers:
- exec_handler (connectonion/network/host/http_router.py): the gate + dispatch
- run_exec (connectonion/network/host/ws_router/exec.py): the WS frame handler
- ExecResult (connectonion/network/connect.py): the client-side result type
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


# ─────────────────────────── exec_handler: the gate ───────────────────────────

class TestExecHandlerGate:
    def test_disabled_by_default(self):
        """exec_tools=None → EXEC refused entirely."""
        out = exec_handler(make_factory(_echo), None, "_echo", {"text": "hi"})
        assert out["status"] == "error"
        assert "not enabled" in out["error"]

    def test_disabled_when_false(self):
        out = exec_handler(make_factory(_echo), False, "_echo", {"text": "hi"})
        assert out["status"] == "error"

    def test_tool_not_in_whitelist(self):
        """A tool outside the allow-list is refused even though it exists."""
        out = exec_handler(make_factory(_echo, _screenshot), ["_screenshot"], "_echo", {"text": "hi"})
        assert out["status"] == "error"
        assert "not exec-enabled" in out["error"]

    def test_whitelisted_tool_runs(self):
        out = exec_handler(make_factory(_echo, _screenshot), ["_echo"], "_echo", {"text": "hi"})
        assert out["status"] == "success"
        assert out["result"] == "echo: hi"

    def test_true_allows_any_registered_tool(self):
        out = exec_handler(make_factory(_echo), True, "_echo", {"text": "world"})
        assert out["status"] == "success"
        assert out["result"] == "echo: world"


# ─────────────────────────── exec_handler: execution ──────────────────────────

class TestExecHandlerExecution:
    def test_unknown_tool(self):
        out = exec_handler(make_factory(_echo), True, "_nope", {})
        assert out["status"] == "error"
        assert "unknown tool" in out["error"]

    def test_tool_error_returned_as_data(self):
        """Tool exceptions become error results, not raised — same as the LLM loop."""
        out = exec_handler(make_factory(_boom), True, "_boom", {})
        assert out["status"] == "error"
        assert "kaboom" in out["error"]
        assert "duration_ms" in out

    def test_success_carries_duration(self):
        out = exec_handler(make_factory(_echo), True, "_echo", {"text": "x"})
        assert out["status"] == "success"
        assert isinstance(out["duration_ms"], int)

    def test_screenshot_result_is_raw_base64(self):
        """Image tools flow through unchanged — the client extracts images."""
        out = exec_handler(make_factory(_screenshot), True, "_screenshot", {})
        assert out["status"] == "success"
        assert out["result"].startswith("data:image/png;base64,")


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
