"""Unit tests for connectonion/useful_tools/codex.py

Tests cover:
- codex function: headless Codex CLI invocation with mocked subprocess
- Session resume: session_id round-trip and silent new-thread detection
- Streaming: internal Codex events forwarded to agent.io as they arrive
- Error paths: missing CLI, timeout, bad sandbox, non-zero exit
"""

import importlib
import io as _io
import json
from unittest.mock import patch, MagicMock

from connectonion.useful_tools.codex import codex

# The codex function shadows its own module in the package namespace
# (useful_tools.codex is the function after `from .codex import codex`),
# which breaks string-based patch targets on Python 3.10. Patch through
# the module object instead.
codex_module = importlib.import_module("connectonion.useful_tools.codex")


def _jsonl(*events):
    return [json.dumps(e) + "\n" for e in events]


THREAD_ID = "0199a213-81c0-7800-8aa1-bbab2a035a53"

SUCCESS_EVENTS = (
    {"type": "thread.started", "thread_id": THREAD_ID},
    {"type": "turn.started"},
    {"type": "item.completed", "item": {"type": "reasoning", "text": "thinking"}},
    {"type": "item.completed", "item": {"type": "command_execution", "command": "pytest"}},
    {"type": "item.completed", "item": {"type": "agent_message", "text": "Fixed the tests."}},
    {"type": "turn.completed", "usage": {"input_tokens": 100, "output_tokens": 20}},
)


class FakePopen:
    """Minimal stand-in for subprocess.Popen used by the codex tool."""

    def __init__(self, stdout_lines=(), stderr_text="", returncode=0):
        self.stdout = iter(stdout_lines)
        self.stderr = _io.StringIO(stderr_text)
        self.returncode = returncode

    def wait(self):
        return self.returncode

    def kill(self):
        self.returncode = -9


def _popen_factory(**kwargs):
    """Return a Popen mock whose call yields a fresh FakePopen."""
    fake = FakePopen(**kwargs)
    return MagicMock(return_value=fake), fake


class TestCodexSuccess:
    @patch.object(codex_module.shutil, "which", return_value="/usr/bin/codex")
    def test_returns_session_id_and_message(self, _which):
        popen, _ = _popen_factory(stdout_lines=_jsonl(*SUCCESS_EVENTS))
        with patch.object(codex_module.subprocess, "Popen", popen):
            result = json.loads(codex("fix the tests"))

        assert result["provider"] == "codex"
        assert result["session_id"] == THREAD_ID
        assert result["last_message"] == "Fixed the tests."
        assert result["usage"]["output_tokens"] == 20
        assert result["exit_code"] == 0
        assert result["resumed"] is False
        assert "error" not in result

    @patch.object(codex_module.shutil, "which", return_value="/usr/bin/codex")
    def test_builds_exec_command_with_json(self, _which):
        popen, _ = _popen_factory(stdout_lines=_jsonl(*SUCCESS_EVENTS))
        with patch.object(codex_module.subprocess, "Popen", popen):
            codex("do a task", approval="auto")

        cmd = popen.call_args[0][0]
        assert cmd[:2] == ["codex", "exec"]
        assert "--json" in cmd
        assert cmd[-1] == "do a task"

    @patch.object(codex_module.shutil, "which", return_value="/usr/bin/codex")
    def test_cwd_model_and_sandbox_flags(self, _which):
        popen, _ = _popen_factory(stdout_lines=_jsonl(*SUCCESS_EVENTS))
        with patch.object(codex_module.subprocess, "Popen", popen):
            codex("task", cwd="/repo", sandbox="workspace-write", model="gpt-5-codex", approval="auto")

        cmd = popen.call_args[0][0]
        assert cmd[cmd.index("--cd") + 1] == "/repo"
        assert cmd[cmd.index("--sandbox") + 1] == "workspace-write"
        assert cmd[cmd.index("--model") + 1] == "gpt-5-codex"


class TestCodexResume:
    @patch.object(codex_module.shutil, "which", return_value="/usr/bin/codex")
    def test_resume_uses_resume_subcommand(self, _which):
        popen, _ = _popen_factory(stdout_lines=_jsonl(*SUCCESS_EVENTS))
        with patch.object(codex_module.subprocess, "Popen", popen):
            codex("continue", session_id=THREAD_ID)

        cmd = popen.call_args[0][0]
        assert cmd[:4] == ["codex", "exec", "resume", THREAD_ID]

    @patch.object(codex_module.shutil, "which", return_value="/usr/bin/codex")
    def test_resumed_true_when_same_thread_id(self, _which):
        popen, _ = _popen_factory(stdout_lines=_jsonl(*SUCCESS_EVENTS))
        with patch.object(codex_module.subprocess, "Popen", popen):
            result = json.loads(codex("continue", session_id=THREAD_ID))

        assert result["resumed"] is True
        assert result["session_id"] == THREAD_ID

    @patch.object(codex_module.shutil, "which", return_value="/usr/bin/codex")
    def test_silent_new_thread_detected(self, _which):
        # Codex silently starts a new thread when resuming an ephemeral session
        new_thread = _jsonl(
            {"type": "thread.started", "thread_id": "different-thread-id"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "hi"}},
            {"type": "turn.completed", "usage": {}},
        )
        popen, _ = _popen_factory(stdout_lines=new_thread)
        with patch.object(codex_module.subprocess, "Popen", popen):
            result = json.loads(codex("continue", session_id=THREAD_ID))

        assert result["resumed"] is False
        assert result["session_id"] == "different-thread-id"


class _SignatureIO:
    """io stub matching the real connectonion IO.log(event_type, **data)
    signature, so a bad forward call collides here just like it would against
    the real IO — a bare MagicMock would silently swallow the mismatch."""
    def __init__(self):
        self.calls = []

    def log(self, event_type, **data):
        self.calls.append((event_type, data))

    def request_approval(self, tool, arguments):
        return True


class _SignatureAgent:
    def __init__(self):
        self.io = _SignatureIO()


class TestCodexStreaming:
    @patch.object(codex_module.shutil, "which", return_value="/usr/bin/codex")
    def test_events_forwarded_to_agent_io(self, _which):
        agent = _SignatureAgent()
        popen, _ = _popen_factory(stdout_lines=_jsonl(*SUCCESS_EVENTS))
        with patch.object(codex_module.subprocess, "Popen", popen):
            codex("task", agent=agent)

        # Every parsed event is streamed to the client as a codex_event.
        assert len(agent.io.calls) == len(SUCCESS_EVENTS)
        event_type, data = agent.io.calls[0]
        assert event_type == "codex_event"
        assert data["codex_type"] == "thread.started"
        # The command run inside Codex is visible to the frontend.
        item_types = [d["item_type"] for _, d in agent.io.calls]
        assert "command_execution" in item_types

    @patch.object(codex_module.shutil, "which", return_value="/usr/bin/codex")
    def test_no_io_when_agent_missing(self, _which):
        # Direct call without an agent must not raise (one-shot / test usage).
        popen, _ = _popen_factory(stdout_lines=_jsonl(*SUCCESS_EVENTS))
        with patch.object(codex_module.subprocess, "Popen", popen):
            result = json.loads(codex("task"))
        assert result["last_message"] == "Fixed the tests."

    @patch.object(codex_module.shutil, "which", return_value="/usr/bin/codex")
    def test_no_io_when_agent_has_no_io(self, _which):
        agent = MagicMock()
        agent.io = None
        popen, _ = _popen_factory(stdout_lines=_jsonl(*SUCCESS_EVENTS))
        with patch.object(codex_module.subprocess, "Popen", popen):
            result = json.loads(codex("task", agent=agent))
        assert result["session_id"] == THREAD_ID


class TestCodexApproval:
    @patch.object(codex_module.shutil, "which", return_value="/usr/bin/codex")
    def test_write_sandbox_downgrades_without_io(self, _which):
        # Default sandbox is workspace-write; with no interactive client and
        # manual approval it must NOT silently escalate — downgrade to read-only.
        popen, _ = _popen_factory(stdout_lines=_jsonl(*SUCCESS_EVENTS))
        with patch.object(codex_module.subprocess, "Popen", popen):
            result = json.loads(codex("task"))

        cmd = popen.call_args[0][0]
        assert cmd[cmd.index("--sandbox") + 1] == "read-only"
        assert "downgraded to read-only" in result["note"]

    @patch.object(codex_module.shutil, "which", return_value="/usr/bin/codex")
    def test_auto_approval_runs_write_sandbox(self, _which):
        popen, _ = _popen_factory(stdout_lines=_jsonl(*SUCCESS_EVENTS))
        with patch.object(codex_module.subprocess, "Popen", popen):
            codex("task", approval="auto")

        cmd = popen.call_args[0][0]
        assert cmd[cmd.index("--sandbox") + 1] == "workspace-write"

    @patch.object(codex_module.shutil, "which", return_value="/usr/bin/codex")
    def test_manual_approval_asks_user_and_runs_when_approved(self, _which):
        agent = MagicMock()
        agent.io.request_approval.return_value = True
        popen, _ = _popen_factory(stdout_lines=_jsonl(*SUCCESS_EVENTS))
        with patch.object(codex_module.subprocess, "Popen", popen):
            codex("task", cwd="/repo", agent=agent)

        agent.io.request_approval.assert_called_once()
        tool, args = agent.io.request_approval.call_args[0]
        assert tool == "codex"
        assert args["sandbox"] == "workspace-write" and args["cwd"] == "/repo"
        cmd = popen.call_args[0][0]
        assert cmd[cmd.index("--sandbox") + 1] == "workspace-write"

    @patch.object(codex_module.shutil, "which", return_value="/usr/bin/codex")
    def test_manual_approval_rejected_never_launches(self, _which):
        agent = MagicMock()
        agent.io.request_approval.return_value = False
        popen, _ = _popen_factory(stdout_lines=_jsonl(*SUCCESS_EVENTS))
        with patch.object(codex_module.subprocess, "Popen", popen):
            result = json.loads(codex("task", agent=agent))

        assert "rejected" in result["error"]
        assert popen.called is False

    @patch.object(codex_module.shutil, "which", return_value="/usr/bin/codex")
    def test_read_only_never_asks_for_approval(self, _which):
        agent = MagicMock()
        popen, _ = _popen_factory(stdout_lines=_jsonl(*SUCCESS_EVENTS))
        with patch.object(codex_module.subprocess, "Popen", popen):
            codex("task", sandbox="read-only", agent=agent)

        agent.io.request_approval.assert_not_called()
        cmd = popen.call_args[0][0]
        assert cmd[cmd.index("--sandbox") + 1] == "read-only"

    @patch.object(codex_module.shutil, "which", return_value="/usr/bin/codex")
    def test_invalid_approval_mode(self, _which):
        result = json.loads(codex("task", approval="whenever"))
        assert "Invalid approval" in result["error"]


class TestCodexErrors:
    @patch.object(codex_module.shutil, "which", return_value=None)
    def test_missing_cli(self, _which):
        result = json.loads(codex("task"))
        assert "codex CLI not found" in result["error"]

    @patch.object(codex_module.shutil, "which", return_value="/usr/bin/codex")
    def test_invalid_sandbox(self, _which):
        result = json.loads(codex("task", sandbox="yolo"))
        assert "Invalid sandbox" in result["error"]

    @patch.object(codex_module.shutil, "which", return_value="/usr/bin/codex")
    def test_timeout(self, _which):
        popen, fake = _popen_factory(stdout_lines=_jsonl(*SUCCESS_EVENTS))

        class InstantTimer:
            """Fires its callback immediately on start (simulates timeout)."""
            def __init__(self, _interval, fn):
                self._fn = fn

            def start(self):
                self._fn()

            def cancel(self):
                pass

        with patch.object(codex_module.subprocess, "Popen", popen), \
             patch.object(codex_module.threading, "Timer", InstantTimer):
            result = json.loads(codex("task", timeout=5))

        assert "timed out after 5 seconds" in result["error"]

    @patch.object(codex_module.shutil, "which", return_value="/usr/bin/codex")
    def test_nonzero_exit_includes_stderr(self, _which):
        popen, _ = _popen_factory(stderr_text="401 Unauthorized", returncode=1)
        with patch.object(codex_module.subprocess, "Popen", popen):
            result = json.loads(codex("task"))

        assert result["exit_code"] == 1
        assert "401 Unauthorized" in result["error"]

    @patch.object(codex_module.shutil, "which", return_value="/usr/bin/codex")
    def test_turn_failed_uses_structured_error(self, _which):
        # Real codex ends a failed run with turn.failed carrying a clean message,
        # while stderr is noisy transport spam — prefer the structured message.
        events = _jsonl(
            {"type": "thread.started", "thread_id": THREAD_ID},
            {"type": "turn.failed", "error": {"message": "401 Unauthorized: Missing bearer"}},
        )
        popen, _ = _popen_factory(stdout_lines=events,
                                  stderr_text="ERROR websocket spam " * 200, returncode=1)
        with patch.object(codex_module.subprocess, "Popen", popen):
            result = json.loads(codex("task"))

        assert result["exit_code"] == 1
        assert result["session_id"] == THREAD_ID
        assert "401 Unauthorized: Missing bearer" in result["error"]
        assert "websocket spam" not in result["error"]

    @patch.object(codex_module.shutil, "which", return_value="/usr/bin/codex")
    def test_turn_failed_with_nonstandard_error_shape(self, _which):
        # A malformed/other-version turn.failed (error as a bare string) must
        # not crash the tool — it must never raise to the agent loop.
        events = _jsonl(
            {"type": "thread.started", "thread_id": THREAD_ID},
            {"type": "turn.failed", "error": "plain string error"},
        )
        popen, _ = _popen_factory(stdout_lines=events, returncode=1)
        with patch.object(codex_module.subprocess, "Popen", popen):
            result = json.loads(codex("task"))

        assert result["exit_code"] == 1
        assert "plain string error" in result["error"]

    @patch.object(codex_module.shutil, "which", return_value="/usr/bin/codex")
    def test_non_json_lines_ignored(self, _which):
        lines = ["not json\n"] + _jsonl(*SUCCESS_EVENTS) + ["garbage\n"]
        popen, _ = _popen_factory(stdout_lines=lines)
        with patch.object(codex_module.subprocess, "Popen", popen):
            result = json.loads(codex("task"))

        assert result["session_id"] == THREAD_ID
        assert result["last_message"] == "Fixed the tests."
