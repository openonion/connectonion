"""Unit tests for interruptible blocking agent steps."""

import importlib
import threading
import time

import pytest

from connectonion import Agent, before_each_tool
from connectonion.cli.co_ai.tools.claude_code import claude_code as co_ai_claude_code
from connectonion.cli.co_ai.tools.codex import codex as co_ai_codex
from connectonion.core.interrupt import InterruptibleIO, UserInterrupt, run_interruptible
from connectonion.core.tool_executor import execute_single_tool
from connectonion.logger import Logger
from connectonion.network.io.websocket import WebSocketIO
from tests.utils.mock_helpers import MockLLM


class MailboxIO:
    def __init__(self, messages=None):
        self.messages = list(messages or [])
        self.lock = threading.Lock()

    def send_to_agent(self, message):
        with self.lock:
            self.messages.append(message)

    def receive_all(self, msg_type=None):
        with self.lock:
            if msg_type is None:
                result = list(self.messages)
                self.messages.clear()
                return result
            matched = [m for m in self.messages if m.get("type") == msg_type]
            self.messages[:] = [m for m in self.messages if m.get("type") != msg_type]
            return matched


def test_direct_call_without_io_has_no_worker_thread():
    caller = threading.get_ident()

    result, interrupted = run_interruptible(threading.get_ident, None)

    assert result == caller
    assert interrupted is False


def test_pending_interrupt_prevents_step_from_starting():
    io = MailboxIO([{"type": "INTERRUPT"}])
    started = False

    def step():
        nonlocal started
        started = True

    result, interrupted = run_interruptible(step, io, poll_seconds=0.01)

    assert result is None
    assert interrupted is True
    assert started is False


def test_interrupt_abandons_slow_step_and_preserves_other_messages():
    io = MailboxIO([{"type": "mode_change", "mode": "safe"}])
    started = threading.Event()
    release = threading.Event()

    def step():
        started.set()
        release.wait(timeout=2)
        return "late"

    def interrupt():
        assert started.wait(timeout=1)
        io.send_to_agent({"type": "INTERRUPT"})

    threading.Thread(target=interrupt, daemon=True).start()
    before = time.monotonic()
    result, interrupted = run_interruptible(step, io, poll_seconds=0.01)
    elapsed = time.monotonic() - before
    release.set()

    assert result is None
    assert interrupted is True
    assert elapsed < 0.3
    assert io.receive_all() == [{"type": "mode_change", "mode": "safe"}]


def test_completed_step_wins_same_poll_window():
    class RaceIO(MailboxIO):
        def __init__(self):
            super().__init__()
            self.polls = 0

        def receive_all(self, msg_type=None):
            self.polls += 1
            if self.polls == 1:
                return []
            return [{"type": "INTERRUPT"}]

    io = RaceIO()

    result, interrupted = run_interruptible(
        lambda: (time.sleep(0.01), "done")[1],
        io,
        poll_seconds=0.1,
    )

    assert result == "done"
    assert interrupted is False
    assert io.polls == 1


def test_worker_exception_is_reraised_on_caller_thread():
    def fail():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        run_interruptible(fail, MailboxIO(), poll_seconds=0.01)


def test_abandoned_agent_tool_cannot_commit_session_or_registry_changes():
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def late_tool(agent) -> str:
        started.set()
        release.wait(timeout=2)
        agent.current_session["late_worker_poison"] = True
        agent.tools.remove("victim")
        try:
            agent.io.receive()
        finally:
            finished.set()
        return "late"

    def victim() -> str:
        return "still registered"

    agent = Agent(
        "lease-test", llm=MockLLM(), tools=[late_tool, victim], log=False, quiet=True
    )
    old_session = {"messages": [], "trace": [], "iteration": 1}
    agent.current_session = old_session
    agent.io = WebSocketIO()

    def interrupt():
        assert started.wait(timeout=1)
        agent.io.send_to_agent({"type": "INTERRUPT"})

    threading.Thread(target=interrupt, daemon=True).start()
    trace = execute_single_tool(
        "late_tool", {}, "late-call", agent.tools, agent, Logger("lease-test", log=False)
    )
    assert trace["status"] == "interrupted"

    new_session = {"messages": [], "trace": [], "iteration": 1}
    agent.current_session = new_session
    next_reply = {"type": "ask_user_response", "answer": "next turn"}
    agent.io.send_to_agent(next_reply)
    release.set()

    assert finished.wait(timeout=1)
    assert "late_worker_poison" not in new_session
    assert "late_worker_poison" not in old_session
    assert "victim" in agent.tools
    assert agent.io.receive_all() == [next_reply]


@pytest.mark.parametrize(
    ("provider", "tool", "module_name", "backend_name"),
    [
        (
            "codex",
            co_ai_codex,
            "connectonion.cli.co_ai.tools.codex",
            "run_codex",
        ),
        (
            "claude_code",
            co_ai_claude_code,
            "connectonion.cli.co_ai.tools.claude_code",
            "run_claude_code",
        ),
    ],
)
def test_interrupted_coding_provider_cannot_commit_late_state_or_io(
    monkeypatch, tmp_path, provider, tool, module_name, backend_name
):
    """Both wrappers revoke framework state and IO after an interrupt.

    Subprocess/filesystem rollback is deliberately outside this transaction;
    providers still need their own bounded cleanup and cooperative cancellation.
    """
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def slow_backend(**kwargs):
        tool_agent = kwargs["agent"]
        tool_agent.io.log("provider_progress", provider=provider, phase="started")
        started.set()
        release.wait(timeout=2)
        tool_agent.current_session["provider_session_id"] = "late-session"
        tool_agent.io.log("provider_progress", provider=provider, phase="late")
        try:
            tool_agent.io.receive()
        except UserInterrupt:
            pass
        finally:
            finished.set()
        return '{"session_id":"late-session","last_message":"late"}'

    module = importlib.import_module(module_name)
    monkeypatch.setattr(module, backend_name, slow_backend)
    agent = Agent(
        f"{provider}-interrupt",
        llm=MockLLM(),
        tools=[tool],
        log=False,
        quiet=True,
    )
    old_session = {"messages": [], "trace": [], "iteration": 1, "mode": "safe"}
    agent.current_session = old_session
    agent.io = WebSocketIO()

    def interrupt():
        assert started.wait(timeout=1)
        agent.io.send_to_agent({"type": "INTERRUPT"})

    threading.Thread(target=interrupt, daemon=True).start()
    trace = execute_single_tool(
        provider,
        {"prompt": "inspect", "cwd": str(tmp_path)},
        f"{provider}-call",
        agent.tools,
        agent,
        Logger(f"{provider}-interrupt", log=False),
    )

    assert trace["status"] == "interrupted"
    new_session = {"messages": [], "trace": [], "iteration": 1, "mode": "safe"}
    agent.current_session = new_session
    next_reply = {"type": "ask_user_response", "answer": "next turn"}
    agent.io.send_to_agent(next_reply)
    release.set()

    assert finished.wait(timeout=1)
    assert "provider_session_id" not in old_session
    assert "provider_session_id" not in new_session
    progress = [
        message
        for message in agent.io._msgs_from_agent
        if message.get("type") == "provider_progress"
    ]
    assert [message["phase"] for message in progress] == ["started"]
    assert agent.io.receive_all() == [next_reply]


def test_cancelled_receive_all_cannot_drain_the_next_turn_mailbox():
    entered_receive_all = threading.Event()
    release_receive_all = threading.Event()
    finished = threading.Event()

    class PausedWebSocketIO(WebSocketIO):
        def receive_all_interruptibly(self, cancel_event, msg_type=None):
            entered_receive_all.set()
            release_receive_all.wait(timeout=2)
            return super().receive_all_interruptibly(cancel_event, msg_type)

    def polling_tool(agent) -> str:
        try:
            agent.io.receive_all("ask_user_response")
        finally:
            finished.set()
        return "late"

    agent = Agent("atomic-lease", llm=MockLLM(), tools=[polling_tool], log=False, quiet=True)
    agent.current_session = {"messages": [], "trace": [], "iteration": 1}
    agent.io = PausedWebSocketIO()

    def interrupt():
        assert entered_receive_all.wait(timeout=1)
        agent.io.send_to_agent({"type": "INTERRUPT"})

    threading.Thread(target=interrupt, daemon=True).start()
    trace = execute_single_tool(
        "polling_tool", {}, "poll-call", agent.tools, agent,
        Logger("atomic-lease", log=False),
    )
    assert trace["status"] == "interrupted"

    next_reply = {"type": "ask_user_response", "answer": "next turn secret"}
    agent.io.send_to_agent(next_reply)
    release_receive_all.set()

    assert finished.wait(timeout=1)
    assert agent.io.receive_all() == [next_reply]


def test_receive_all_interrupt_preserves_unrelated_mailbox_frames():
    io = WebSocketIO()
    lease = InterruptibleIO(io)
    reply = {"type": "ask_user_response", "answer": "keep me"}
    io.send_to_agent(reply)
    io.send_to_agent({"type": "INTERRUPT"})

    with pytest.raises(UserInterrupt):
        lease.receive_all()

    assert io.receive_all() == [reply]


def test_interruptible_io_makes_request_approval_an_interrupted_tool():
    entered = threading.Event()

    def approval_tool(agent) -> str:
        entered.set()
        approved = agent.io.request_approval("publish", {"target": "prod"})
        return "approved" if approved else "denied"

    agent = Agent("approval-test", llm=MockLLM(), tools=[approval_tool], log=False, quiet=True)
    agent.current_session = {"messages": [], "trace": [], "iteration": 1}
    agent.io = WebSocketIO()

    def interrupt():
        assert entered.wait(timeout=1)
        agent.io.send_to_agent({"type": "INTERRUPT"})

    threading.Thread(target=interrupt, daemon=True).start()
    trace = execute_single_tool(
        "approval_tool", {}, "approval-call", agent.tools, agent,
        Logger("approval-test", log=False),
    )

    assert trace["status"] == "interrupted"
    assert trace["result"] == "Interrupted by user"


def test_completed_agent_tool_commits_its_session_snapshot():
    def change_mode(agent) -> str:
        agent.current_session["mode"] = "accept_edits"
        agent.tools.remove("victim")
        return "changed"

    def victim() -> str:
        return "removed on success"

    agent = Agent(
        "snapshot-commit", llm=MockLLM(), tools=[change_mode, victim],
        log=False, quiet=True,
    )
    session = {"messages": [], "trace": [], "iteration": 1, "mode": "safe"}
    agent.current_session = session
    agent.io = WebSocketIO()

    trace = execute_single_tool(
        "change_mode", {}, "change-call", agent.tools, agent,
        Logger("snapshot-commit", log=False),
    )

    assert trace["status"] == "success"
    assert agent.current_session is session
    assert session["mode"] == "accept_edits"
    assert "victim" not in agent.tools


def test_pending_tool_is_cleared_when_gate_interrupts():
    @before_each_tool
    def interrupt_gate(agent):
        raise UserInterrupt()

    def work() -> str:
        return "unreachable"

    agent = Agent(
        "gate-test",
        llm=MockLLM(),
        tools=[work],
        on_events=[interrupt_gate],
        log=False,
        quiet=True,
    )
    agent.current_session = {"messages": [], "trace": [], "iteration": 1}

    trace = execute_single_tool(
        "work", {}, "gate-call", agent.tools, agent, Logger("gate-test", log=False)
    )

    assert trace["status"] == "interrupted"
    assert "pending_tool" not in agent.current_session
