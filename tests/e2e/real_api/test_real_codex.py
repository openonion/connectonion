"""Real end-to-end tests for the `codex` tool against the actual codex-acp adapter.

The tool is ACP-only: it drives the real codex-acp binary over JSON-RPC — no
mocks, no fakes. Marked `real_api` so the default suite skips them; run:

    # integration only (real binary; works even without Codex credentials —
    # asserts the initialize + session handshake and clean auth-error surfacing):
    CODEX_ACP_CMD=./node_modules/.bin/codex-acp \
        pytest -m real_api tests/e2e/real_api/test_real_codex.py

    # full model turn (needs Codex auth: OPENAI_API_KEY / CODEX_API_KEY / login):
    OPENAI_API_KEY=sk-... CODEX_ACP_CMD=./node_modules/.bin/codex-acp \
        pytest -m real_api tests/e2e/real_api/test_real_codex.py

Install the adapter: `npm install -g @zed-industries/codex-acp`.
"""

import json
import os
import shutil

import pytest

from connectonion.useful_tools import codex

pytestmark = pytest.mark.real_api

HAS_CODEX_ACP = bool(os.environ.get("CODEX_ACP_CMD") or shutil.which("codex-acp"))
HAS_AUTH = bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("CODEX_API_KEY")
                or os.path.exists(os.path.expanduser("~/.codex/auth.json")))

requires_codex_acp = pytest.mark.skipif(
    not HAS_CODEX_ACP,
    reason="codex-acp not installed (npm i -g @zed-industries/codex-acp) / set $CODEX_ACP_CMD")


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


@requires_codex_acp
def test_real_codex_acp_handshake_and_reporting():
    """Drives the real codex-acp binary end-to-end. The initialize + session
    handshake runs against the real adapter; without auth, session/new returns
    a real error the tool surfaces cleanly. With auth, a full turn streams
    native tool_call/tool_result events and returns the assistant message."""
    agent = _Agent()
    result = json.loads(codex("Reply with exactly: pong", cwd=".",
                              approval="auto", agent=agent, timeout=90))

    assert result["provider"] == "codex"

    if HAS_AUTH and "error" not in result:
        assert result["exit_code"] == 0
        assert result["session_id"]
        # inner steps stream in the frontend's native vocabulary
        forwarded = [et for et, _ in agent.io.events]
        assert all(et in ("tool_call", "tool_result") for et in forwarded)
    else:
        assert "error" in result
        assert "Authentication" in result["error"] or "auth" in result["error"].lower()


@pytest.mark.skipif(not HAS_AUTH, reason="needs Codex credentials for a successful multi-turn resume")
@requires_codex_acp
def test_real_codex_session_resume():
    """With auth: a follow-up call resumes the same real Codex session."""
    first = json.loads(codex("Remember the number 7.", cwd=".", approval="auto", timeout=120))
    assert first["session_id"] and "error" not in first

    second = json.loads(codex("What number did I ask you to remember?",
                              session_id=first["session_id"], cwd=".", approval="auto", timeout=120))
    assert second["resumed"] is True
    assert "7" in second["last_message"]
