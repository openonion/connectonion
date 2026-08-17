"""Unit tests for connectonion/useful_tools/codex.py (native codex app-server).

The CodexAppServer client is replaced with a fake that drives the on_event /
on_approval callbacks, so these run without spawning `codex app-server`. A
real-binary end-to-end lives in tests/e2e/real_api/test_real_codex.py.
"""

import base64
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


@pytest.fixture(autouse=True)
def _reap_open_only_clients():
    codex_module._close_open_threads()
    yield
    codex_module._close_open_threads()


class FakeServer:
    """Stand-in CodexAppServer that simulates one turn via callbacks."""
    last = None

    def __init__(
        self, command, cwd=None, on_event=None, on_approval=None, cancelled=None
    ):
        self.command = command
        self.cwd = cwd
        self.on_event = on_event
        self.on_approval = on_approval
        self.cancelled = cancelled
        self.calls = []
        self.approval_decision = None
        FakeServer.last = self

    def start(self):
        self.calls.append("start")

    def close(self):
        self.calls.append("close")

    def initialize(self, timeout=60):
        self.calls.append("initialize")

    def refresh_account(self, timeout=60):
        self.calls.append("refresh_account")

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
            {"command": "pytest -q", "cwd": self.cwd},
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

    def request_approval(self, tool, arguments, *, context=None):
        self.asked.append((tool, arguments, context))
        return self.approve


class _Agent:
    def __init__(self, io, current_session=None):
        self.io = io
        self.current_session = current_session or {}


class _WorkroomIO(_IO):
    """Small native-message mailbox and wire capture for Work Room tests."""

    def __init__(self, messages=()):
        super().__init__()
        self.messages = list(messages)
        self.outbound = []

    def receive_all(self, message_type):
        assert message_type == "PROVIDER_INPUT"
        result = self.messages
        self.messages = []
        return result

    def send(self, event):
        self.outbound.append(event)


def _run(**kwargs):
    with patch.object(codex_module, "CodexAppServer", FakeServer), \
         patch.object(codex_module, "_base_command", return_value=["codex", "app-server"]):
        return json.loads(codex(**kwargs))


class TestCodexRun:
    def test_open_without_prompt_creates_thread_without_starting_a_turn(self):
        result = _run(prompt="", cwd=".", approval="auto", agent=_Agent(_IO()))

        assert result["session_id"] == "thread-1"
        assert result["opened"] is True
        assert result["exit_code"] == 0
        assert "refresh_account" not in FakeServer.last.calls
        assert not any(
            isinstance(call, tuple) and call[0] == "run_turn"
            for call in FakeServer.last.calls
        )
        assert "close" not in FakeServer.last.calls

    def test_first_prompt_reuses_the_exact_open_only_thread(self):
        with (
            patch.object(codex_module, "CodexAppServer", FakeServer),
            patch.object(
                codex_module,
                "_base_command",
                return_value=["codex", "app-server"],
            ),
        ):
            opened = json.loads(
                codex(prompt="", cwd=".", approval="auto", agent=_Agent(_IO()))
            )
            server = FakeServer.last
            result = json.loads(
                codex(
                    prompt="inspect",
                    session_id=opened["session_id"],
                    cwd=".",
                    approval="auto",
                    agent=_Agent(_IO()),
                )
            )

        assert FakeServer.last is server
        assert result["session_id"] == opened["session_id"]
        assert result["resumed"] is True
        assert ("run_turn", "thread-1", "inspect") in server.calls
        assert not any(
            isinstance(call, tuple) and call[0] == "resume_thread"
            for call in server.calls
        )
        assert server.calls[-1] == "close"

    def test_expired_open_only_thread_is_closed(self):
        opened = _run(
            prompt="", cwd=".", approval="auto", agent=_Agent(_IO())
        )
        server = FakeServer.last

        codex_module._close_expired_open_threads(
            now=codex_module.time.monotonic()
            + codex_module._OPEN_THREAD_TTL_SECONDS
        )

        assert opened["session_id"] not in codex_module._open_threads
        assert server.calls[-1] == "close"

    def test_open_only_registry_evicts_the_oldest_process(self):
        servers = []
        for index in range(codex_module._MAX_OPEN_THREADS + 1):
            server = FakeServer(["codex", "app-server"])
            servers.append(server)
            codex_module._store_open_thread(
                f"thread-{index}",
                server,
                cwd=".",
                sandbox="read-only",
                model="",
                approval_policy="never",
            )

        assert len(codex_module._open_threads) == codex_module._MAX_OPEN_THREADS
        assert "thread-0" not in codex_module._open_threads
        assert servers[0].calls[-1] == "close"

    def test_changed_policy_refuses_and_closes_an_open_only_process(self):
        _run(prompt="", cwd=".", approval="auto", agent=_Agent(_IO()))
        server = FakeServer.last

        claimed = codex_module._take_open_thread(
            "thread-1",
            cwd=".",
            sandbox="workspace-write",
            model="",
            approval_policy="untrusted",
        )

        assert claimed is None
        assert server.calls[-1] == "close"

    def test_open_existing_session_without_prompt_resumes_without_turn(self):
        result = _run(
            prompt="",
            session_id="prev",
            cwd=".",
            approval="auto",
            agent=_Agent(_IO()),
        )

        assert result["session_id"] == "prev"
        assert result["resumed"] is True
        assert result["opened"] is True
        assert not any(
            isinstance(call, tuple) and call[0] == "run_turn"
            for call in FakeServer.last.calls
        )

    def test_new_thread_accumulates_message(self):
        agent = _Agent(_IO(approve=True))
        result = _run(prompt="fix", cwd=".", approval="auto", agent=agent)

        assert result["provider"] == "codex"
        assert result["session_id"] == "thread-1"
        assert result["resumed"] is False
        assert result["last_message"] == "Hello world"
        assert result["exit_code"] == 0
        assert result["usage"]["input_tokens"] == 5
        assert FakeServer.last.calls[:4] == [
            "start",
            "initialize",
            "refresh_account",
            ("start_thread", "workspace-write", "", "never"),
        ]

    def test_live_workroom_message_is_acknowledged_only_after_native_steer(self):
        io = _WorkroomIO([{
            "type": "PROVIDER_INPUT",
            "invocationId": "codex:outer",
            "stateRevision": 7,
            "text": "Please add a reverse-order fixture.",
            "requestId": "direct-1",
        }])
        agent = _Agent(io, {"_active_tool_call_id": "outer"})
        client = MagicMock()

        codex_module._steer_workroom_inputs(agent, client, "thread-1", "turn-1")

        client.steer_turn.assert_called_once_with(
            "thread-1",
            "turn-1",
            "Please add a reverse-order fixture.",
            "direct-1",
        )
        assert io.events == [("provider_message", {
            "provider": "codex",
            "invocationId": "codex:outer",
            "parentToolCallId": "outer",
            "messageId": "user:direct-1",
            "role": "user",
            "text": "Please add a reverse-order fixture.",
            "workroomId": "codex:outer",
        })]
        assert io.outbound == [{
            "type": "PROVIDER_INPUT_ACK",
            "requestId": "direct-1",
            "invocationId": "codex:outer",
            "accepted": True,
            "stateRevision": 7,
        }]

    def test_failed_native_steer_keeps_the_workroom_message_unacknowledged(self):
        io = _WorkroomIO([{
            "type": "PROVIDER_INPUT",
            "invocationId": "codex:outer",
            "stateRevision": 7,
            "text": "Please add a reverse-order fixture.",
            "requestId": "direct-1",
        }])
        agent = _Agent(io, {"_active_tool_call_id": "outer"})
        client = MagicMock()
        client.steer_turn.side_effect = RuntimeError("turn already completed")

        codex_module._steer_workroom_inputs(agent, client, "thread-1", "turn-1")

        assert io.events == []
        assert io.outbound == []

    def test_direct_continuation_acknowledges_the_source_only_after_turn_start(self):
        io = _WorkroomIO()
        agent = _Agent(io, {
            "_active_tool_call_id": "continued",
            "_provider_workroom_id": "codex:root",
            "_provider_continuation_of": "codex:source",
            "_provider_direct_message": "Run the C11 checks now.",
            "_provider_direct_message_id": "direct-2",
            "_provider_direct_state_revision": 7,
        })

        codex_module._confirm_direct_workroom_turn(agent)

        assert io.events == [("provider_message", {
            "provider": "codex",
            "invocationId": "codex:continued",
            "parentToolCallId": "continued",
            "messageId": "user:direct-2",
            "role": "user",
            "text": "Run the C11 checks now.",
            "workroomId": "codex:root",
            "continuationOf": "codex:source",
        })]
        assert io.outbound == [{
            "type": "PROVIDER_INPUT_ACK",
            "requestId": "direct-2",
            "invocationId": "codex:source",
            "accepted": True,
            "stateRevision": 7,
        }]

    def test_auth_refresh_failure_does_not_start_a_thread(self):
        class AuthFailureServer(FakeServer):
            def refresh_account(self, timeout=60):
                super().refresh_account(timeout)
                raise RuntimeError("account/read failed: login required")

        with (
            patch.object(codex_module, "CodexAppServer", AuthFailureServer),
            patch.object(
                codex_module,
                "_base_command",
                return_value=["codex", "app-server"],
            ),
        ):
            result = json.loads(codex("fix", approval="auto"))

        assert result["error"] == (
            "codex app-server: account/read failed: login required"
        )
        assert AuthFailureServer.last.calls == [
            "start",
            "initialize",
            "refresh_account",
            "close",
        ]

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
        assert call["status"] == "in_progress"
        result = next(d for et, d in agent.io.events if et == "tool_result")
        assert result["tool_id"] == "c1" and result["status"] == "completed"

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
        assert result["status"] == "failed"

    def test_no_custom_codex_event_type(self):
        agent = _Agent(_IO())
        _run(prompt="fix", approval="auto", agent=agent)
        assert all(et != "codex_event" for et, _ in agent.io.events)

    def test_safe_provider_activity_precedes_the_legacy_tool_compatibility_event(self):
        agent = _Agent(_IO(), {"_active_tool_call_id": "parent-1"})
        start = {
            "kind": "tool_start",
            "id": "compile-1",
            "name": "cc -std=c11 -Wall -Werror sort.c -o sort",
            "native_kind": "commandExecution",
            "args": {
                "command": "cc -std=c11 -Wall -Werror sort.c -o sort --token private-value",
                "cwd": "/private/tmp/operator/private-workroom",
            },
        }
        end = {**start, "kind": "tool_end", "failed": False, "result": "private output"}

        codex_module._forward_ui(agent, start)
        codex_module._forward_ui(agent, end)

        typed = [data for event_type, data in agent.io.events if event_type == "provider_activity"]
        assert typed == [
            {
                "provider": "codex",
                "activityId": "compile-1",
                "sequence": 1,
                "kind": "command",
                "status": "running",
                "title": "Compile the requested C11 program",
                "summary": "Compiling the requested C11 program",
                "invocationId": "codex:parent-1",
                "parentToolCallId": "parent-1",
            },
            {
                "provider": "codex",
                "activityId": "compile-1",
                "sequence": 1,
                "kind": "command",
                "status": "completed",
                "title": "Compile the requested C11 program",
                "summary": "Compiled the requested C11 program",
                "invocationId": "codex:parent-1",
                "parentToolCallId": "parent-1",
            },
        ]
        assert "private" not in json.dumps(typed)
        assert [event_type for event_type, _ in agent.io.events] == [
            "provider_activity", "tool_call", "provider_activity", "tool_result",
        ]

    def test_completed_workspace_image_view_becomes_a_current_safe_artifact(self, tmp_path):
        workspace = tmp_path / "workroom"
        workspace.mkdir()
        image = workspace / "latest.png"
        thumbnail = (
            "data:image/png;base64,"
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlRjyoAAAAASUVORK5CYII="
        )
        image.write_bytes(base64.b64decode(thumbnail.split(",", 1)[1]))
        agent = _Agent(_IO(), {"_active_tool_call_id": "parent-image-1"})

        codex_module._forward_ui(
            agent,
            {"kind": "image_view", "id": "view-1", "path": str(image)},
            workspace=workspace,
        )

        assert [event_type for event_type, _ in agent.io.events] == [
            "provider_invocation", "provider_artifact",
        ]
        lifecycle, artifact = [data for _, data in agent.io.events]
        assert lifecycle == {
            "invocationId": "codex:parent-image-1",
            "parentToolCallId": "parent-image-1",
            "provider": "codex",
            "providerDisplayName": "Codex",
            "status": "running",
            "currentSummary": "Working in the selected workspace",
            "stateRevision": 1,
        }
        assert artifact["stateRevision"] == lifecycle["stateRevision"]
        assert artifact["thumbnailDataUrl"] == thumbnail
        assert artifact["alt"] == "Latest provider workspace view"
        assert str(image) not in json.dumps(agent.io.events)

    def test_image_view_outside_the_workspace_is_never_forwarded(self, tmp_path):
        workspace = tmp_path / "workroom"
        workspace.mkdir()
        image = tmp_path / "private.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\nnot-a-workroom-preview")
        agent = _Agent(_IO(), {"_active_tool_call_id": "parent-image-1"})

        codex_module._forward_ui(
            agent,
            {"kind": "image_view", "id": "view-1", "path": str(image)},
            workspace=workspace,
        )

        assert agent.io.events == []


class TestApproval:
    def test_native_approval_has_a_safe_verified_workroom_presentation(self):
        agent = _Agent(
            _IO(approve=True),
            {"_active_tool_call_id": "parent-codex-call"},
        )

        allowed = codex_module._approval_allowed(
            "item/commandExecution/requestApproval",
            {
                "command": "cc -std=c11 sort.c --token private-value",
                "cwd": "/private/tmp/workroom",
                "reason": "compile private-value",
            },
            "manual",
            agent,
            fallback_cwd="/private/tmp/workroom",
        )

        assert allowed is True
        _, arguments, context = agent.io.asked[0]
        assert arguments == {
            "action": "Compile the requested C11 program",
            "scope": "This Work Room only",
            "reason": "Compile the requested workspace files before continuing",
        }
        assert context["providerApproval"] == {
            "action": "Compile the requested C11 program",
            "scope": "This Work Room only",
            "reason": "Compile the requested workspace files before continuing",
            "scopeClassification": "workroom",
            "allowOnce": True,
            "allowSession": False,
            "files": ["sort.c"],
        }
        assert "private" not in json.dumps({"arguments": arguments, "context": context})
        provider_events = [
            data for event_type, data in agent.io.events
            if event_type == "provider_invocation"
        ]
        assert provider_events == [
            {
                "invocationId": "codex:parent-codex-call",
                "parentToolCallId": "parent-codex-call",
                "provider": "codex",
                "providerDisplayName": "Codex",
                "status": "awaiting_approval",
                "currentSummary": "Waiting for your decision",
                "stateRevision": 1,
            },
            {
                "invocationId": "codex:parent-codex-call",
                "parentToolCallId": "parent-codex-call",
                "provider": "codex",
                "providerDisplayName": "Codex",
                "status": "running",
                "currentSummary": "Working in the selected workspace",
                "stateRevision": 2,
            },
        ]

    def test_native_approval_outside_the_workroom_fails_closed_after_review(self):
        agent = _Agent(_IO(approve=True), {"_active_tool_call_id": "parent-codex-call"})

        allowed = codex_module._approval_allowed(
            "item/fileChange/requestApproval",
            {
                "grantRoot": "/private/tmp/outside-workroom",
                "fileChanges": {"/private/tmp/outside-workroom/private.py": {}},
            },
            "manual",
            agent,
            fallback_cwd="/private/tmp/workroom",
        )

        assert allowed is False
        _, arguments, context = agent.io.asked[0]
        assert arguments["scope"] == "Outside this Work Room"
        assert context["providerApproval"]["scopeClassification"] == "elevated"
        assert context["providerApproval"]["allowOnce"] is False

    def test_native_approval_with_an_unknown_boundary_fails_closed_after_review(self):
        agent = _Agent(_IO(approve=True), {"_active_tool_call_id": "parent-codex-call"})

        allowed = codex_module._approval_allowed(
            "item/commandExecution/requestApproval",
            {"command": "pytest -q"},
            "manual",
            agent,
            fallback_cwd="",
        )

        assert allowed is False
        _, arguments, context = agent.io.asked[0]
        assert arguments["scope"] == "Boundary could not be verified"
        assert context["providerApproval"]["scopeClassification"] == "unknown"
        assert context["providerApproval"]["allowOnce"] is False

    def test_auto_denies_unexpected_callback_without_asking(self):
        agent = _Agent(_IO(approve=True))
        _run(prompt="fix", approval="auto", agent=agent)
        assert FakeServer.last.approval_decision is False
        assert agent.io.asked == []

    def test_manual_approved_renders_card_and_allows(self):
        agent = _Agent(_IO(approve=True))
        _run(prompt="fix", approval="manual", agent=agent)
        assert FakeServer.last.approval_decision is True
        assert agent.io.asked and agent.io.asked[0][0] == "codex"
        # The approval summary is safe presentation, not raw provider transport.
        assert agent.io.asked[0][1] == {
            "action": "Run the requested tests",
            "scope": "This Work Room only",
            "reason": "Verify the requested workspace changes before continuing",
        }

    def test_manual_rejected_denies(self):
        agent = _Agent(_IO(approve=False))
        _run(prompt="fix", approval="manual", agent=agent)
        assert FakeServer.last.approval_decision is False

    def test_manual_approval_has_provider_correlation(self):
        agent = _Agent(
            _IO(),
            {"_active_tool_call_id": "parent-codex-call"},
        )

        _run(
            prompt="fix",
            cwd="/private/tmp/workspace/.workroom-e2e",
            approval="manual",
            agent=agent,
        )

        _, details, context = agent.io.asked[0]
        assert details == {
            "action": "Run the requested tests",
            "scope": "This Work Room only",
            "reason": "Verify the requested workspace changes before continuing",
        }
        assert context == {
            "provider": "codex",
            "invocationId": "codex:parent-codex-call",
            "parentToolCallId": "parent-codex-call",
            "providerApproval": {
                "action": "Run the requested tests",
                "scope": "This Work Room only",
                "reason": "Verify the requested workspace changes before continuing",
                "scopeClassification": "workroom",
                "allowOnce": True,
                "allowSession": False,
            },
        }
        assert [event[0] for event in agent.io.events] == [
            "provider_message",
            "provider_activity",
            "tool_call",
            "provider_invocation",
            "provider_invocation",
            "provider_activity",
            "tool_result",
            "provider_message",
        ]

    def test_hosted_contact_cannot_answer_manual_approval(self):
        agent = _Agent(
            _IO(approve=True),
            {"requester": {"address": "0xcontact", "level": "contact"}},
        )

        _run(prompt="fix", approval="manual", agent=agent)

        assert FakeServer.last.approval_decision is False
        assert agent.io.asked == []

    def test_hosted_admin_can_answer_manual_approval(self):
        agent = _Agent(
            _IO(approve=True),
            {"requester": {"address": "0xadmin", "level": "admin"}},
        )

        _run(prompt="fix", approval="manual", agent=agent)

        assert FakeServer.last.approval_decision is True
        assert agent.io.asked

    @pytest.mark.parametrize(
        "method",
        [
            "item/permissions/requestApproval",
            "item/fileChange/requestApproval",
            "item/commandExecution/requestApproval",
            "applyPatchApproval",
            "execCommandApproval",
        ],
    )
    def test_auto_refuses_every_unexpected_escalation_callback(self, method):
        agent = _Agent(_IO(approve=True))

        allowed = codex_module._approval_allowed(
            method,
            {
                "permissions": {"network": {"enabled": True}},
                "grantRoot": "/outside-workspace",
                "additionalPermissions": {"network": True},
            },
            "auto",
            agent,
        )

        assert allowed is False
        assert agent.io.asked == []

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
        assert details == {
            "action": "Run a workspace command",
            "scope": "Outside this Work Room",
            "reason": "Codex requested approval to continue",
        }

    def test_outbound_command_never_inherits_a_workroom_allowance(self):
        presentation = codex_module._provider_approval_presentation(
            "item/commandExecution/requestApproval",
            {"command": "git push origin main", "cwd": "/private/tmp/workroom"},
            fallback_cwd="/private/tmp/workroom",
        )

        assert presentation["action"] == "Run a workspace command"
        assert presentation["scopeClassification"] == "elevated"
        assert presentation["allowOnce"] is False

    def test_v2_file_change_shows_the_grant_root(self):
        details = codex_module._approval_details(
            "item/fileChange/requestApproval",
            {"grantRoot": "/repo/src", "reason": "write parser"},
        )
        assert details == {
            "action": "Make workspace file changes",
            "scope": "Boundary could not be verified",
            "reason": "Apply the requested workspace file changes",
        }

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
        assert details == {
            "action": "Make workspace file changes",
            "scope": "Boundary could not be verified",
            "reason": "Apply the requested workspace file changes",
        }

    def test_missing_provider_cwd_uses_a_safe_workroom_label(self):
        details = codex_module._approval_details(
            "item/fileChange/requestApproval",
            {"fileChanges": {"dijkstra.py": {}}},
            fallback_cwd="/private/tmp/operator-project/.workroom-e2e-20260816",
        )

        assert details == {
            "action": "Make workspace file changes",
            "scope": "This Work Room only",
            "reason": "Apply the requested workspace file changes",
        }

    def test_v2_permissions_show_the_exact_requested_profile(self):
        permissions = {"network": {"enabled": True}}
        details = codex_module._approval_details(
            "item/permissions/requestApproval",
            {"permissions": permissions, "cwd": "/repo"},
        )
        assert details == {
            "action": "Expand provider permissions",
            "scope": "Boundary could not be verified",
            "reason": "Review the requested permission expansion",
        }


class TestResumeProtocol:
    def test_account_refresh_uses_codex_managed_auth(self):
        client = codex_module.CodexAppServer(["codex", "app-server"])
        with patch.object(client, "request", return_value={}) as request:
            client.refresh_account(timeout=9)

        request.assert_called_once_with(
            "account/read", {"refreshToken": True}, timeout=9
        )

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
        done.wait.assert_called_once_with(0.1)

    def test_turn_start_callback_runs_only_after_codex_returns_a_turn_id(self):
        client = codex_module.CodexAppServer(["codex", "app-server"])
        done = MagicMock()
        done.wait.return_value = True
        client._turn_done = done
        started = []
        with patch.object(
            client,
            "request",
            return_value={"turn": {"id": "turn-7"}},
        ):
            client.run_turn(
                "thread-1",
                "continue",
                timeout=10,
                on_turn_started=started.append,
            )

        assert started == ["turn-7"]

    def test_turn_wait_preserves_the_full_budget_after_manual_approval(self):
        client = codex_module.CodexAppServer(["codex", "app-server"])

        class ApprovalDelayEvent:
            def __init__(self):
                self.waits = []

            def clear(self):
                pass

            def wait(self, seconds):
                self.waits.append(seconds)
                if len(self.waits) == 1:
                    # Simulate 100 seconds of operator review between two
                    # active execution slices without sleeping in the test.
                    client._approval_wait_seconds = 100
                    return False
                return True

        done = ApprovalDelayEvent()
        client._turn_done = done
        with patch.object(client, "request", return_value={}), patch.object(
            codex_module.time, "monotonic", side_effect=[0, 0, 1, 101]
        ):
            client.run_turn("thread-1", "continue", timeout=10)

        assert done.waits == [0.1, 0.1]

    def test_approval_request_records_operator_review_time(self):
        client = codex_module.CodexAppServer(
            ["codex", "app-server"], on_approval=lambda *_: True
        )
        with patch.object(client, "_send"), patch.object(
            codex_module.time, "monotonic", side_effect=[10, 35]
        ):
            client._handle_server_request(
                1, "item/commandExecution/requestApproval", {"command": "pytest -q"}
            )

        assert client._approval_wait_seconds == 25

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

    def test_posix_process_tree_falls_back_when_group_signal_is_denied(self):
        process = MagicMock(pid=42)
        with patch.object(codex_module.os, "name", "posix"), patch.object(
            codex_module.os, "killpg", side_effect=PermissionError
        ):
            codex_module._terminate_process_tree(process)

        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=1)

    @pytest.mark.parametrize("outcome", [0, 1, "timeout"])
    def test_windows_process_tree_cleanup_handles_taskkill_outcomes(self, outcome):
        process = MagicMock(pid=42)
        with patch.object(codex_module.os, "name", "nt"), patch.object(
            codex_module.subprocess, "run"
        ) as taskkill:
            if outcome == "timeout":
                taskkill.side_effect = subprocess.TimeoutExpired("taskkill", 5)
            else:
                taskkill.return_value.returncode = outcome

            codex_module._terminate_process_tree(process)

        taskkill.assert_called_once()
        assert taskkill.call_args.args[0] == [
            "taskkill",
            "/F",
            "/T",
            "/PID",
            "42",
        ]
        assert taskkill.call_args.kwargs["timeout"] == 5
        assert taskkill.call_args.kwargs["shell"] is False
        if outcome == 0:
            process.kill.assert_not_called()
        else:
            process.kill.assert_called_once()

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
