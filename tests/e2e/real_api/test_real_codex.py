"""Real end-to-end tests for the `codex` tool against the actual codex CLI.

The tool drives Codex's native `codex app-server` protocol from Python — no
mocks, no fakes, no external adapter. Marked `real_api` so the default suite
skips them; run:

    # integration only (real binary; works even without Codex credentials —
    # asserts the initialize + thread handshake and clean auth-error surfacing):
    CODEX_CMD=./node_modules/.bin/codex \
        pytest -m real_api tests/e2e/real_api/test_real_codex.py

    # full model turn (needs Codex auth: OPENAI_API_KEY / CODEX_API_KEY / login):
    OPENAI_API_KEY=sk-... CODEX_CMD=./node_modules/.bin/codex \
        pytest -m real_api tests/e2e/real_api/test_real_codex.py

Install the CLI: `npm install -g @openai/codex`.
"""

import json
import os
import shutil

import pytest

from connectonion.useful_tools import codex

pytestmark = pytest.mark.real_api

HAS_CODEX = bool(os.environ.get("CODEX_CMD") or shutil.which("codex"))
HAS_AUTH = bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("CODEX_API_KEY")
                or os.path.exists(os.path.expanduser("~/.codex/auth.json")))

requires_codex = pytest.mark.skipif(
    not HAS_CODEX, reason="codex CLI not installed (npm i -g @openai/codex) / set $CODEX_CMD")


class _RecordingIO:
    """io that records the events the tool streams and auto-approves."""
    def __init__(self):
        self.events = []

    def log(self, event_type, **data):
        self.events.append((event_type, data))

    def request_approval(self, tool, arguments):
        return True


class _Agent:
    def __init__(self):
        self.io = _RecordingIO()


@requires_codex
def test_real_codex_app_server_handshake_and_reporting():
    """Drives the real `codex app-server` end-to-end. initialize + thread/start
    run against the real binary (no auth needed to get a thread id); without
    credentials the turn fails and the tool surfaces the error cleanly. With
    auth, a full turn streams native tool_call/tool_result events and returns
    the assistant message."""
    agent = _Agent()
    result = json.loads(codex("Reply with exactly: pong", cwd=".",
                              approval="auto", agent=agent, timeout=90))

    assert result["provider"] == "codex"
    # thread/start returns a real thread id even before the model call
    assert result["session_id"]

    if HAS_AUTH and "error" not in result:
        assert result["exit_code"] == 0
        forwarded = [et for et, _ in agent.io.events]
        assert all(et in ("tool_call", "tool_result") for et in forwarded)
    else:
        assert result["exit_code"] != 0
        assert "error" in result


@pytest.mark.skipif(not HAS_AUTH, reason="needs Codex credentials for a successful multi-turn resume")
@requires_codex
def test_real_codex_session_resume():
    """With auth: a follow-up call resumes the same real Codex thread."""
    first = json.loads(codex("Remember the number 7.", cwd=".", approval="auto", timeout=120))
    assert first["session_id"] and "error" not in first

    second = json.loads(codex("What number did I ask you to remember?",
                              session_id=first["session_id"], cwd=".", approval="auto", timeout=120))
    assert second["resumed"] is True
    assert "7" in second["last_message"]
