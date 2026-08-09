"""Unit tests for connectonion/useful_tools/codex.py (native codex app-server).

The CodexAppServer client is replaced with a fake that drives the on_event /
on_approval callbacks, so these run without spawning `codex app-server`. A
real-binary end-to-end lives in tests/e2e/real_api/test_real_codex.py.
"""

import importlib
import io
import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from connectonion.useful_tools.codex import codex

# `from .codex import codex` makes useful_tools.codex the function, shadowing the
# module; reach the module (for CodexAppServer / helpers) via importlib.
codex_module = importlib.import_module("connectonion.useful_tools.codex")


class FakeServer:
    """Stand-in CodexAppServer that simulates one turn via callbacks."""
    last = None

    def __init__(self, command, cwd=None, on_event=None, on_approval=None):
        self.command = command
        self.cwd = cwd
        self.on_event = on_event
        self.on_approval = on_approval
        self.calls = []
        self.approval_decision = None
        FakeServer.last = self

    def start(self):
        self.calls.append("start")

    def close(self):
        self.calls.append("close")

    def initialize(self, timeout=60):
        self.calls.append("initialize")

    def start_thread(
        self,
        sandbox="workspace-write",
        model="",
        approval_policy="on-request",
        timeout=60,
    ):
        self.calls.append(("start_thread", sandbox, model, approval_policy))
        return "thread-1"

    def resume_thread(
        self,
        thread_id,
        sandbox="workspace-write",
        model="",
        approval_policy="on-request",
        timeout=60,
    ):
        self.calls.append(
            ("resume_thread", thread_id, sandbox, model, approval_policy)
        )
        return thread_id

    def run_turn(self, thread_id, prompt, cwd="", timeout=600):
        self.calls.append(("run_turn", thread_id, prompt))
        self.on_event({"kind": "agent_message", "text": "Hello "})
        self.on_event({"kind": "tool_start", "id": "c1", "name": "pytest"})
        self.approval_decision = self.on_approval(
            "item/commandExecution/requestApproval",
            {"command": "pytest -q", "cwd": "/repo"},
        )
        self.on_event({"kind": "tool_end", "id": "c1", "name": "pytest", "failed": False})
        self.on_event({"kind": "agent_message", "text": "world"})
        return {"status": "completed", "usage": {"input_tokens": 5}}


class _IO:
    def __init__(self, approve=True):
        self.approve = approve
        self.events = []
        self.asked = []

    def log(self, event_type, **data):
        self.events.append((event_type, data))

    def request_approval(self, tool, arguments):
        self.asked.append((tool, arguments))
        return self.approve


class _Agent:
    def __init__(self, io):
        self.io = io


def _run(**kwargs):
    with patch.object(codex_module, "CodexAppServer", FakeServer), \
         patch.object(codex_module, "_base_command", return_value=["codex", "app-server"]):
        return json.loads(codex(**kwargs))


class TestCodexRun:
    def test_new_thread_accumulates_message(self):
        agent = _Agent(_IO(approve=True))
        result = _run(prompt="fix", cwd=".", approval="auto", agent=agent)

        assert result["provider"] == "codex"
        assert result["session_id"] == "thread-1"
        assert result["resumed"] is False
        assert result["last_message"] == "Hello world"
        assert result["exit_code"] == 0
        assert result["usage"]["input_tokens"] == 5

    def test_resume_reapplies_sandbox_and_model(self):
        agent = _Agent(_IO())
        result = _run(
            prompt="continue",
            session_id="prev",
            sandbox="read-only",
            model="gpt-5-codex",
            approval="auto",
            agent=agent,
        )

        assert result["resumed"] is True
        assert result["session_id"] == "prev"
        assert (
            "resume_thread",
            "prev",
            "read-only",
            "gpt-5-codex",
            "never",
        ) in FakeServer.last.calls

    def test_sandbox_and_model_passed_to_thread_start(self):
        _run(prompt="fix", sandbox="read-only", model="gpt-5-codex", approval="auto", agent=_Agent(_IO()))
        assert (
            "start_thread",
            "read-only",
            "gpt-5-codex",
            "never",
        ) in FakeServer.last.calls

    def test_missing_binary_errors(self):
        with patch.object(codex_module, "_base_command", return_value=None):
            result = json.loads(codex("fix"))
        assert "codex CLI not found" in result["error"]

    def test_invalid_sandbox(self):
        assert "Invalid sandbox" in json.loads(codex("fix", sandbox="yolo"))["error"]

    def test_invalid_approval(self):
        assert "Invalid approval" in json.loads(codex("fix", approval="whenever"))["error"]

    @pytest.mark.parametrize("timeout", [0, -1, True, 1.5])
    def test_invalid_timeout(self, timeout):
        result = json.loads(codex("fix", timeout=timeout))
        assert "positive integer" in result["error"]


class TestFrontendEventVocabulary:
    """Codex steps must be forwarded as the SDK's native tool_call/tool_result
    events (not a custom type), so the frontend renders them unchanged."""

    def test_tool_call_and_result_emitted(self):
        agent = _Agent(_IO())
        _run(prompt="fix", approval="auto", agent=agent)

        types = [et for et, _ in agent.io.events]
        assert "tool_call" in types and "tool_result" in types

        call = next(d for et, d in agent.io.events if et == "tool_call")
        assert call["tool_id"] == "c1" and call["name"] == "pytest"
        result = next(d for et, d in agent.io.events if et == "tool_result")
        assert result["tool_id"] == "c1" and result["status"] == "done"

    def test_failed_tool_maps_to_error(self):
        agent = _Agent(_IO())

        class FailServer(FakeServer):
            def run_turn(self, thread_id, prompt, cwd="", timeout=600):
                self.on_event({"kind": "tool_start", "id": "x", "name": "rm"})
                self.on_event({"kind": "tool_end", "id": "x", "name": "rm", "failed": True})
                return {"status": "completed"}

        with patch.object(codex_module, "CodexAppServer", FailServer), \
             patch.object(codex_module, "_base_command", return_value=["codex", "app-server"]):
            codex("fix", approval="auto", agent=agent)

        result = next(d for et, d in agent.io.events if et == "tool_result")
        assert result["status"] == "error"

    def test_no_custom_codex_event_type(self):
        agent = _Agent(_IO())
        _run(prompt="fix", approval="auto", agent=agent)
        assert all(et != "codex_event" for et, _ in agent.io.events)


class TestApproval:
    def test_auto_approves_without_asking(self):
        agent = _Agent(_IO(approve=False))     # io says no, but auto ignores io
        _run(prompt="fix", approval="auto", agent=agent)
        assert FakeServer.last.approval_decision is True
        assert agent.io.asked == []

    def test_manual_approved_renders_card_and_allows(self):
        agent = _Agent(_IO(approve=True))
        _run(prompt="fix", approval="manual", agent=agent)
        assert FakeServer.last.approval_decision is True
        assert agent.io.asked and agent.io.asked[0][0] == "codex"
        # the approval summary shows the actual command
        assert agent.io.asked[0][1]["command"] == "pytest -q"
        assert agent.io.asked[0][1]["cwd"] == "/repo"

    def test_manual_rejected_denies(self):
        agent = _Agent(_IO(approve=False))
        _run(prompt="fix", approval="manual", agent=agent)
        assert FakeServer.last.approval_decision is False

    def test_manual_without_io_denies(self):
        assert (
            codex_module._approval_allowed(
                "item/commandExecution/requestApproval",
                {"command": "x"},
                "manual",
                agent=None,
            )
            is False
        )

    def test_deny_never_asks(self):
        agent = _Agent(_IO(approve=True))
        _run(prompt="inspect", approval="deny", agent=agent)
        assert FakeServer.last.approval_decision is False
        assert agent.io.asked == []


class TestApprovalDetails:
    def test_legacy_command_list_is_joined(self):
        details = codex_module._approval_details(
            "execCommandApproval", {"command": ["git", "push"], "cwd": "/repo"}
        )
        assert details["command"] == "git push"

    def test_v2_file_change_shows_the_grant_root(self):
        details = codex_module._approval_details(
            "item/fileChange/requestApproval",
            {"grantRoot": "/repo/src", "reason": "write parser"},
        )
        assert details["grant_root"] == "/repo/src"
        assert "/repo/src" in details["action"]

    def test_legacy_patch_shows_the_grant_root_and_changed_files(self):
        details = codex_module._approval_details(
            "applyPatchApproval",
            {
                "grantRoot": "/repo/src",
                "fileChanges": {
                    "parser.py": {"type": "update"},
                    "test_parser.py": {"type": "add"},
                },
                "reason": "implement parser",
            },
        )
        assert details["grant_root"] == "/repo/src"
        assert details["files"] == ["parser.py", "test_parser.py"]
        assert "parser.py" in details["action"]
        assert "test_parser.py" in details["action"]

    def test_v2_permissions_show_the_exact_requested_profile(self):
        permissions = {"network": {"enabled": True}}
        details = codex_module._approval_details(
            "item/permissions/requestApproval",
            {"permissions": permissions, "cwd": "/repo"},
        )
        assert details["permissions"] == permissions
        assert '"network"' in details["action"]


class TestResumeProtocol:
    def test_start_uses_separate_process_group_and_drains_stderr(self):
        client = codex_module.CodexAppServer(["codex", "app-server"], cwd="/repo")
        process = MagicMock()
        with patch.object(codex_module.subprocess, "Popen", return_value=process) as popen, \
             patch.object(codex_module.threading, "Thread") as thread:
            client.start()

        assert popen.call_args.kwargs["stderr"] is subprocess.PIPE
        assert popen.call_args.kwargs["shell"] is False
        group_option = (
            "creationflags" if codex_module.os.name == "nt" else "start_new_session"
        )
        assert popen.call_args.kwargs[group_option]
        assert thread.call_count == 2

    def test_resume_request_reapplies_execution_policy(self):
        client = codex_module.CodexAppServer(["codex", "app-server"], cwd="/repo")
        with patch.object(
            client,
            "request",
            return_value={"thread": {"id": "thread-1"}},
        ) as request:
            assert (
                client.resume_thread(
                    "thread-1",
                    sandbox="read-only",
                    model="gpt-5-codex",
                    approval_policy="never",
                    timeout=9,
                )
                == "thread-1"
            )

        request.assert_called_once_with(
            "thread/resume",
            {
                "threadId": "thread-1",
                "cwd": "/repo",
                "sandbox": "read-only",
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "model": "gpt-5-codex",
            },
            timeout=9,
        )

    def test_resume_rejects_a_different_thread_id(self):
        client = codex_module.CodexAppServer(["codex", "app-server"])
        with patch.object(
            client,
            "request",
            return_value={"thread": {"id": "different"}},
        ):
            with pytest.raises(RuntimeError, match="expected 'thread-1'"):
                client.resume_thread("thread-1")

    def test_turn_request_and_wait_share_one_timeout_budget(self):
        client = codex_module.CodexAppServer(["codex", "app-server"])
        done = MagicMock()
        done.wait.return_value = True
        client._turn_done = done
        with patch.object(client, "request", return_value={}) as request, patch.object(
            codex_module.time, "monotonic", side_effect=[0, 0, 4]
        ):
            client.run_turn("thread-1", "continue", timeout=10)

        assert request.call_args.kwargs["timeout"] == 10
        done.wait.assert_called_once_with(6)

    def test_close_reaps_the_process_tree_and_closes_every_pipe(self):
        client = codex_module.CodexAppServer(["codex", "app-server"])
        process = MagicMock()
        client.proc = process

        with patch.object(codex_module, "_terminate_process_tree") as terminate:
            client.close()

        terminate.assert_called_once_with(process)
        process.stdin.close.assert_called_once()
        process.stdout.close.assert_called_once()
        process.stderr.close.assert_called_once()

    def test_posix_process_tree_escalates_after_grace_period(self):
        process = MagicMock(pid=42)
        process.wait.side_effect = [subprocess.TimeoutExpired("codex", 2), 0]
        with patch.object(codex_module.os, "name", "posix"), patch.object(
            codex_module.os, "killpg"
        ) as killpg:
            codex_module._terminate_process_tree(process)

        assert [entry.args for entry in killpg.call_args_list] == [
            (42, codex_module.signal.SIGTERM),
            (42, 0),
            (42, codex_module.signal.SIGKILL),
        ]

    def test_reader_eof_immediately_fails_pending_requests_with_stderr(self):
        client = codex_module.CodexAppServer(["codex", "app-server"])
        slot = {"event": MagicMock(), "result": None, "error": None}
        client._pending[1] = slot
        client._stderr_tail = "authentication failed\n"
        client.proc = MagicMock(stdout=[], poll=lambda: 1)

        client._read_loop()

        assert client._pending == {}
        assert "authentication failed" in slot["error"]
        slot["event"].set.assert_called_once()
        assert client._turn_done.is_set()

    def test_request_after_reader_eof_fails_without_waiting(self):
        client = codex_module.CodexAppServer(["codex", "app-server"])
        client._stderr_tail = "invalid configuration\n"
        client.proc = MagicMock(stdout=[], poll=lambda: 1)
        client._read_loop()

        with patch.object(client, "_send") as send, pytest.raises(
            RuntimeError, match="invalid configuration"
        ):
            client.request("thread/start", {}, timeout=30)

        send.assert_not_called()
        assert client._pending == {}

    def test_stderr_reader_keeps_only_a_bounded_tail(self):
        client = codex_module.CodexAppServer(["codex", "app-server"])
        client.proc = MagicMock(stderr=io.StringIO("x" * 5000 + "useful error"))

        client._read_stderr()

        assert len(client._stderr_tail) == 4000
        assert client._stderr_tail.endswith("useful error")


class TestApprovalProtocol:
    def _response(self, method, params, allowed):
        client = codex_module.CodexAppServer(
            ["codex", "app-server"], on_approval=lambda *_: allowed
        )
        with patch.object(client, "_send") as send:
            client._handle_server_request(7, method, params)
        return send.call_args.args[0]["result"]

    @pytest.mark.parametrize(
        "method",
        [
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
        ],
    )
    def test_v2_action_decisions_use_accept_and_decline(self, method):
        assert self._response(method, {}, True) == {"decision": "accept"}
        assert self._response(method, {}, False) == {"decision": "decline"}

    def test_v2_permissions_grant_only_the_requested_profile(self):
        requested = {"network": {"enabled": True}}
        method = "item/permissions/requestApproval"
        assert self._response(method, {"permissions": requested}, True) == {
            "permissions": requested,
            "scope": "turn",
        }
        assert self._response(method, {"permissions": requested}, False) == {
            "permissions": {},
            "scope": "turn",
        }

    @pytest.mark.parametrize(
        "method", ["execCommandApproval", "applyPatchApproval"]
    )
    def test_legacy_decisions_use_the_legacy_schema(self, method):
        assert self._response(method, {}, True) == {"decision": "approved"}
        denied = self._response(method, {}, False)
        assert denied["decision"]["denied"]["rejection"]
