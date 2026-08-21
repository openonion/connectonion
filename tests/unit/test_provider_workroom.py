"""Owned native Codex Work Room continuation tests."""

from connectonion import Agent
from connectonion.network.host.provider_workroom import (
    prepare_provider_workroom_turn,
)
from connectonion.network.host.session import Session, SessionStorage
from connectonion.useful_plugins import tool_approval
from tests.utils.mock_helpers import MockLLM


def _stored_codex_session(*, owner="0xowner"):
    return {
        "mode": "auto",
        "requester": {"address": owner, "level": "admin"},
        "trace": [{
            "type": "provider_invocation",
            "invocationId": "codex:current",
            "parentToolCallId": "outer-call",
            "provider": "codex",
            "providerDisplayName": "Codex",
            "workroomId": "codex:root",
            "status": "cancelled",
            "sessionId": "thread-42",
            "stateRevision": 7,
        }],
    }


def test_owned_terminal_codex_thread_runs_only_the_native_tool_and_persists_safe_events(tmp_path):
    storage = SessionStorage(tmp_path / "sessions.jsonl")
    storage.save(Session(
        session_id="session-1",
        status="done",
        prompt="original outer prompt",
        session=_stored_codex_session(),
    ))
    created = []

    class DirectAgent:
        def __init__(self):
            self.io = None
            self.storage = None
            self.current_session = None
            self.calls = []

        def execute_tool(self, name, arguments):
            self.calls.append((name, arguments))
            # A direct turn may only return typed provider presentation events
            # to the source session; generic tool output is intentionally not
            # carried across the Work Room boundary.
            self.current_session["trace"].extend([
                {
                    "type": "provider_invocation",
                    "invocationId": "codex:continued",
                    "parentToolCallId": "manual-codex",
                    "provider": "codex",
                    "workroomId": "codex:root",
                    "continuationOf": "codex:current",
                    "status": "completed",
                    "stateRevision": 1,
                },
                {
                    "type": "provider_message",
                    "invocationId": "codex:continued",
                    "parentToolCallId": "manual-codex",
                    "provider": "codex",
                    "messageId": "assistant:1",
                    "role": "assistant",
                    "text": "The reverse-order fixture now passes.",
                },
                {"type": "tool_result", "result": "private raw output"},
            ])

    def create_agent():
        agent = DirectAgent()
        created.append(agent)
        return agent

    prepared = prepare_provider_workroom_turn(
        create_agent,
        storage,
        "session-1",
        "codex:current",
        "Please add a reverse-order fixture.",
        "input-1",
        "0xowner",
    )

    assert prepared["stateRevision"] == 7
    prepared["run"](object())

    assert len(created) == 1
    agent = created[0]
    assert agent.calls == [(
        "codex",
        {
            "prompt": "Please add a reverse-order fixture.",
            "cwd": "",
            "session_id": "thread-42",
        },
    )]
    assert agent.current_session["_provider_workroom_id"] == "codex:root"
    assert agent.current_session["_provider_continuation_of"] == "codex:current"
    assert agent.current_session["_provider_direct_message"] == (
        "Please add a reverse-order fixture."
    )
    assert agent.current_session["_provider_direct_state_revision"] == 7
    assert agent.current_session["_provider_direct_approved_tool"] == "codex"

    stored = storage.get("session-1")
    assert stored.status == "done"
    trace = stored.session["trace"]
    assert [event["type"] for event in trace[-2:]] == [
        "provider_invocation",
        "provider_message",
    ]
    assert all("private raw output" not in str(event) for event in trace)


def test_workroom_continuation_fails_closed_for_another_owner_or_live_source(tmp_path):
    storage = SessionStorage(tmp_path / "sessions.jsonl")
    storage.save(Session(
        session_id="session-1",
        status="done",
        prompt="original outer prompt",
        session=_stored_codex_session(),
    ))

    assert prepare_provider_workroom_turn(
        lambda: None,
        storage,
        "session-1",
        "codex:current",
        "Continue",
        "input-1",
        "0xother",
    ) == {"reason": "not_active"}

    active = storage.get("session-1")
    storage.save(active.model_copy(update={"status": "running"}))
    assert prepare_provider_workroom_turn(
        lambda: None,
        storage,
        "session-1",
        "codex:current",
        "Continue",
        "input-2",
        "0xowner",
    ) == {"reason": "not_active"}


def test_owned_continuation_reaches_codex_through_the_real_approval_plugin(tmp_path):
    storage = SessionStorage(tmp_path / "sessions.jsonl")
    storage.save(Session(
        session_id="session-1",
        status="done",
        prompt="original outer prompt",
        session=_stored_codex_session(),
    ))
    calls = []

    def codex(prompt: str, cwd: str, session_id: str) -> str:
        """Continue a Codex thread."""
        calls.append((prompt, cwd, session_id))
        return "continued"

    class NoOuterApprovalIO:
        def __init__(self):
            self.sent = []

        def send(self, event):
            self.sent.append(event)

        def receive(self):
            raise AssertionError("the outer Codex wrapper must not ask")

    def create_agent():
        return Agent(
            "direct-codex-test",
            llm=MockLLM(),
            tools=[codex],
            plugins=[tool_approval],
            log=False,
            quiet=True,
        )

    prepared = prepare_provider_workroom_turn(
        create_agent,
        storage,
        "session-1",
        "codex:current",
        "Please continue.",
        "input-1",
        "0xowner",
    )
    io = NoOuterApprovalIO()

    prepared["run"](io)

    assert calls == [("Please continue.", "", "thread-42")]
    assert all(event.get("type") != "approval_needed" for event in io.sent)
