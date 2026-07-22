"""Real end-to-end tests for the `codex` tool against the actual Codex CLI.

These drive the REAL `codex` binary as a subprocess — no mocks, no fakes.
Marked `real_api` so the default suite skips them; run explicitly:

    # integration only (real binary; works even without OpenAI credentials —
    # asserts the tool parses the real JSONL stream and reports failure cleanly):
    pytest -m real_api tests/e2e/real_api/test_real_codex.py

    # full model turn (needs Codex auth: OPENAI_API_KEY / CODEX_API_KEY / `codex login`):
    OPENAI_API_KEY=sk-... pytest -m real_api tests/e2e/real_api/test_real_codex.py

Install the CLI first: `npm install -g @openai/codex`.
"""

import json
import os
import shutil

import pytest

from connectonion.useful_tools import codex

pytestmark = pytest.mark.real_api

HAS_CODEX = shutil.which("codex") is not None
HAS_CODEX_ACP = bool(os.environ.get("CODEX_ACP_CMD") or shutil.which("codex-acp"))
HAS_AUTH = bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("CODEX_API_KEY")
                or os.path.exists(os.path.expanduser("~/.codex/auth.json")))

requires_codex = pytest.mark.skipif(not HAS_CODEX, reason="codex CLI not installed (npm i -g @openai/codex)")
requires_codex_acp = pytest.mark.skipif(not HAS_CODEX_ACP, reason="codex-acp not installed (npm i -g @zed-industries/codex-acp) / set $CODEX_ACP_CMD")


class _RecordingIO:
    """Minimal io that records streamed events and auto-approves writes."""
    def __init__(self):
        self.events = []

    def log(self, event_type, **data):
        self.events.append(data)

    def request_approval(self, tool, arguments):
        return True


class _Agent:
    def __init__(self):
        self.io = _RecordingIO()


@requires_codex
def test_real_codex_streams_and_reports_regardless_of_auth():
    """Drives the real binary end-to-end. Even unauthenticated, the tool must
    extract the real session_id from thread.started, stream events to io, and
    return a well-formed envelope."""
    agent = _Agent()
    result = json.loads(codex("Reply with exactly: pong", cwd=".",
                              approval="auto", agent=agent, timeout=90))

    assert result["provider"] == "codex"
    # real thread id was parsed out of the live JSONL stream
    assert result["session_id"]
    # events were streamed live to the frontend as Codex ran
    assert any(e.get("codex_type") == "thread.started" for e in agent.io.events)

    if HAS_AUTH and "error" not in result:
        # a real model turn completed
        assert result["exit_code"] == 0
        assert result["last_message"]
    else:
        # no credentials: the turn fails, and the tool surfaces it cleanly
        assert result["exit_code"] != 0
        assert "error" in result


@requires_codex
def test_real_codex_read_only_needs_no_approval():
    """read-only never triggers the approval gate against the real binary."""
    agent = _Agent()
    approvals = []
    agent.io.request_approval = lambda tool, args: approvals.append(tool) or True

    result = json.loads(codex("list files", cwd=".", sandbox="read-only",
                              agent=agent, timeout=90))

    assert approvals == []          # read-only asked for nothing
    assert result["session_id"]     # still ran the real binary


@requires_codex_acp
def test_real_codex_acp_backend_end_to_end():
    """Drives the real codex-acp adapter via backend='acp'. The initialize +
    session/new handshake runs against the real binary; a full turn needs auth."""
    agent = _Agent()
    result = json.loads(codex("Reply with exactly: pong", cwd=".",
                              backend="acp", approval="auto", agent=agent, timeout=90))

    assert result["provider"] == "codex"
    if HAS_AUTH and "error" not in result:
        assert result["exit_code"] == 0
        assert result["last_message"]
        assert any(e.get("codex_type") == "agent_message_chunk" for e in agent.io.events)
    else:
        # no credentials: session/new returns Authentication required, surfaced cleanly
        assert "error" in result
        assert "Authentication" in result["error"] or "auth" in result["error"].lower()


@pytest.mark.skipif(not HAS_AUTH, reason="needs Codex credentials for a successful multi-turn resume")
@requires_codex
def test_real_codex_session_resume():
    """With auth: a follow-up call resumes the same real Codex session."""
    first = json.loads(codex("Remember the number 7.", cwd=".", approval="auto", timeout=120))
    assert first["session_id"] and "error" not in first

    second = json.loads(codex("What number did I ask you to remember?",
                              session_id=first["session_id"], cwd=".", approval="auto", timeout=120))
    assert second["resumed"] is True
    assert "7" in second["last_message"]
