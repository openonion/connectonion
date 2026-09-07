"""The Agent exposes one structured outcome for each attempted turn."""

from __future__ import annotations

import threading
from copy import deepcopy
from pathlib import Path

import pytest

from connectonion import Agent, after_iteration, on_complete
from connectonion.core.llm import LLMResponse, ToolCall
from connectonion.core.usage import TokenUsage
from tests.utils.mock_helpers import MockLLM


def response(
    content: str = "done",
    *,
    tool_calls: list[ToolCall] | None = None,
    usage: TokenUsage | None = None,
) -> LLMResponse:
    return LLMResponse(
        content=content,
        tool_calls=tool_calls or [],
        raw_response={},
        usage=usage,
    )


def outcomes(agent: Agent) -> list[dict]:
    return [
        event
        for event in agent.current_session['trace']
        if event.get('type') == 'turn_result'
    ]


def test_natural_turn_keeps_string_api_and_records_measured_usage(tmp_path):
    usage = TokenUsage(
        input_tokens=120,
        output_tokens=30,
        cached_tokens=20,
        cache_write_tokens=4,
        total_tokens=170,
        cost=0.0012,
    )
    agent = Agent(
        name="outcome",
        llm=MockLLM(responses=[response("answer", usage=usage)]),
        log=False,
        quiet=True,
        co_dir=tmp_path / ".co",
    )

    assert agent.input("question") == "answer"
    assert outcomes(agent) == [
        {
            'type': 'turn_result',
            'turn': 1,
            'reason': 'natural',
            'usage': {
                'input_tokens': 120,
                'output_tokens': 30,
                'cached_tokens': 20,
                'cache_write_tokens': 4,
                'total_tokens': 170,
                'cost': pytest.approx(0.0012),
            },
            'id': outcomes(agent)[0]['id'],
            'ts': outcomes(agent)[0]['ts'],
        }
    ]


def test_usage_is_aggregated_per_turn_not_over_session_history(tmp_path):
    agent = Agent(
        name="multi-turn",
        llm=MockLLM(responses=[
            response("first", usage=TokenUsage(
                input_tokens=10, output_tokens=2, total_tokens=20, cost=0.1
            )),
            response("second", usage=TokenUsage(
                input_tokens=30, output_tokens=4, cached_tokens=5, cost=0.2
            )),
        ]),
        log=False,
        quiet=True,
        co_dir=tmp_path / ".co",
    )

    assert agent.input("one") == "first"
    assert agent.input("two") == "second"

    first, second = outcomes(agent)
    assert first['turn'] == 1
    assert first['usage']['total_tokens'] == 20
    assert second['turn'] == 2
    assert second['usage'] == {
        'input_tokens': 30,
        'output_tokens': 4,
        'cached_tokens': 5,
        'cache_write_tokens': 0,
        'total_tokens': 34,
        'cost': pytest.approx(0.2),
    }


def test_multiple_llm_calls_use_explicit_or_reconciled_totals(tmp_path):
    def lookup(query: str) -> str:
        """Look up a value."""
        return query.upper()

    agent = Agent(
        name="multi-call",
        tools=[lookup],
        llm=MockLLM(responses=[
            response(
                tool_calls=[ToolCall(name="lookup", arguments={"query": "x"}, id="t1")],
                usage=TokenUsage(
                    input_tokens=12, output_tokens=3, total_tokens=25, cost=0.01
                ),
            ),
            response("complete", usage=TokenUsage(
                input_tokens=20,
                output_tokens=5,
                cached_tokens=4,
                cache_write_tokens=2,
                cost=0.02,
            )),
        ]),
        log=False,
        quiet=True,
        co_dir=tmp_path / ".co",
    )

    assert agent.input("work") == "complete"
    assert outcomes(agent)[0]['usage'] == {
        'input_tokens': 32,
        'output_tokens': 8,
        'cached_tokens': 4,
        'cache_write_tokens': 2,
        'total_tokens': 50,
        'cost': pytest.approx(0.03),
    }


def test_turn_usage_keeps_measured_cache_classes_and_status(tmp_path):
    usage = TokenUsage(
        input_tokens=600,
        output_tokens=50,
        cached_tokens=200,
        cache_write_tokens=300,
        total_tokens=650,
        cost=0.002685,
        input_tokens_total=600,
        input_tokens_uncached=100,
        cache_read_input_tokens=200,
        cache_write_input_tokens=300,
        cache_write_5m_input_tokens=100,
        cache_write_1h_input_tokens=200,
        cache_metadata_status="reported",
    )
    agent = Agent(
        name="cache-contract",
        llm=MockLLM(responses=[response("answer", usage=usage)]),
        log=False,
        quiet=True,
        co_dir=tmp_path / ".co",
    )

    agent.input("question")

    turn_usage = outcomes(agent)[0]["usage"]
    assert turn_usage["input_tokens_total"] == 600
    assert turn_usage["input_tokens_uncached"] == 100
    assert turn_usage["cache_read_input_tokens"] == 200
    assert turn_usage["cache_write_input_tokens"] == 300
    assert turn_usage["cache_write_5m_input_tokens"] == 100
    assert turn_usage["cache_write_1h_input_tokens"] == 200
    assert turn_usage["cache_metadata_status"] == "reported"


def test_missing_usage_remains_null(tmp_path):
    agent = Agent(
        name="no-usage",
        llm=MockLLM(responses=[response(usage=None)]),
        log=False,
        quiet=True,
        co_dir=tmp_path / ".co",
    )

    agent.input("question")

    assert outcomes(agent)[0]['usage'] is None


def test_max_iterations_has_structured_reason_and_existing_text(tmp_path):
    def noop() -> str:
        """Do nothing."""
        return "ok"

    agent = Agent(
        name="limited",
        tools=[noop],
        llm=MockLLM(responses=[response(
            tool_calls=[ToolCall(name="noop", arguments={}, id="t1")],
            usage=TokenUsage(input_tokens=4, output_tokens=1),
        )]),
        log=False,
        quiet=True,
        co_dir=tmp_path / ".co",
    )

    assert agent.input("work", max_iterations=1) == (
        "Task incomplete: Maximum iterations (1) reached."
    )
    assert outcomes(agent)[0]['reason'] == 'max_iterations'


def test_policy_stop_signal_has_stopped_reason(tmp_path):
    @after_iteration
    def stop(agent):
        agent.current_session['stop_signal'] = 'stop requested'

    agent = Agent(
        name="stopped",
        llm=MockLLM(responses=[response("unused", usage=TokenUsage())]),
        on_events=[stop],
        log=False,
        quiet=True,
        co_dir=tmp_path / ".co",
    )

    assert agent.input("work") == "What would you like me to do?"
    assert outcomes(agent)[0]['reason'] == 'stopped'


def test_no_progress_stop_signal_has_stopped_reason(tmp_path):
    @after_iteration
    def stop(agent):
        agent.current_session['stop_signal'] = True

    agent = Agent(
        name="no-progress",
        llm=MockLLM(responses=[response("unused", usage=TokenUsage())]),
        on_events=[stop],
        log=False,
        quiet=True,
        co_dir=tmp_path / ".co",
    )

    assert agent.input("work") == "What would you like me to do?"
    assert outcomes(agent)[0]['reason'] == 'stopped'


def test_client_interrupt_has_interrupted_reason(tmp_path):
    def noop() -> str:
        """Do nothing."""
        return "ok"

    @after_iteration
    def interrupt(agent):
        agent.current_session['stop_signal'] = 'user_interrupt'

    agent = Agent(
        name="client-interrupt",
        tools=[noop],
        llm=MockLLM(responses=[response(
            tool_calls=[ToolCall(name="noop", arguments={}, id="t1")],
            usage=TokenUsage(),
        )]),
        on_events=[interrupt],
        log=False,
        quiet=True,
        co_dir=tmp_path / ".co",
    )

    assert agent.input("work") == "What would you like me to do?"
    assert outcomes(agent)[0]['reason'] == 'interrupted'


def test_exception_records_type_without_message_then_reraises(tmp_path):
    class FailingLLM:
        model = "failing"

        def complete(self, messages, tools=None):
            raise RuntimeError("super-secret provider detail")

    agent = Agent(
        name="error",
        llm=FailingLLM(),
        log=False,
        quiet=True,
        co_dir=tmp_path / ".co",
    )

    with pytest.raises(RuntimeError, match="super-secret provider detail"):
        agent.input("work")

    assert len(outcomes(agent)) == 1
    assert outcomes(agent)[0]['reason'] == 'error'
    assert outcomes(agent)[0]['error_type'] == 'RuntimeError'
    assert 'super-secret' not in str(outcomes(agent)[0])
    assert outcomes(agent)[0]['usage'] is None


def test_outcome_stream_failure_does_not_mask_original_turn_error(tmp_path):
    class FailingIO:
        def send(self, event):
            raise OSError("transport is closed")

    agent = Agent(
        name="error-order",
        llm=MockLLM(),
        log=False,
        quiet=True,
        co_dir=tmp_path / ".co",
    )
    agent.io = FailingIO()

    with pytest.raises(OSError, match="transport is closed"):
        agent.input("work")

    assert len(outcomes(agent)) == 1
    assert outcomes(agent)[0]['reason'] == 'error'
    assert outcomes(agent)[0]['error_type'] == 'OSError'


def test_terminal_stream_failure_does_not_turn_completed_work_into_failure(tmp_path):
    class TerminalFailingIO:
        def send(self, event):
            if event.get('type') == 'turn_result':
                raise OSError("terminal frame failed")

        def receive_all(self, message_type=None):
            return []

    agent = Agent(
        name="completed-before-stream-failure",
        llm=MockLLM(responses=[response("answer", usage=TokenUsage())]),
        log=False,
        quiet=True,
        co_dir=tmp_path / ".co",
    )
    agent.io = TerminalFailingIO()

    assert agent.input("work") == "answer"
    assert len(outcomes(agent)) == 1
    assert outcomes(agent)[0]['reason'] == 'natural'


def test_interrupt_during_on_complete_is_not_carried_into_next_turn(tmp_path):
    class InterruptIO:
        def __init__(self):
            self.messages = []
            self.lock = threading.Lock()

        def send(self, event):
            pass

        def receive_all(self, message_type=None):
            with self.lock:
                matched = [
                    message for message in self.messages
                    if message.get('type') == message_type
                ]
                self.messages[:] = [
                    message for message in self.messages
                    if message.get('type') != message_type
                ]
                return matched

        def interrupt(self):
            with self.lock:
                self.messages.append({'type': 'INTERRUPT'})

    hook_started = threading.Event()
    release_hook = threading.Event()

    @on_complete
    def block_first_completion(agent):
        if agent.current_session['turn'] == 1:
            hook_started.set()
            assert release_hook.wait(timeout=1)

    io = InterruptIO()
    agent = Agent(
        name="completion-race",
        llm=MockLLM(responses=[
            response("first", usage=TokenUsage()),
            response("second", usage=TokenUsage()),
        ]),
        on_events=[block_first_completion],
        log=False,
        quiet=True,
        co_dir=tmp_path / ".co",
    )
    agent.io = io

    def interrupt_completion():
        assert hook_started.wait(timeout=1)
        io.interrupt()
        release_hook.set()

    threading.Thread(target=interrupt_completion, daemon=True).start()

    assert agent.input("one") == "first"
    assert agent.input("two") == "second"
    assert [outcome['reason'] for outcome in outcomes(agent)] == [
        'natural',
        'natural',
    ]


def test_completed_turn_survives_late_interrupt_drain_failure(tmp_path):
    class DrainFailingIO:
        def __init__(self):
            self.receive_calls = 0

        def send(self, event):
            pass

        def receive_all(self, message_type=None):
            self.receive_calls += 1
            if self.receive_calls == 3:
                raise OSError("mailbox unavailable")
            return []

    io = DrainFailingIO()
    agent = Agent(
        name="drain-failure",
        llm=MockLLM(responses=[response("answer", usage=TokenUsage())]),
        log=False,
        quiet=True,
        co_dir=tmp_path / ".co",
    )
    agent.io = io

    assert agent.input("work") == "answer"
    assert io.receive_calls == 3
    assert outcomes(agent)[0]['reason'] == 'natural'


def test_first_session_sync_contains_the_current_user_message(tmp_path):
    class CapturingIO:
        def __init__(self):
            self.events = []

        def send(self, event):
            self.events.append(deepcopy(event))

        def receive_all(self, message_type=None):
            return []

    io = CapturingIO()
    agent = Agent(
        name="sync-order",
        llm=MockLLM(responses=[response("answer", usage=TokenUsage())]),
        log=False,
        quiet=True,
        co_dir=tmp_path / ".co",
    )
    agent.io = io

    agent.input("current turn")

    first_sync = next(event for event in io.events if event['type'] == 'session_sync')
    assert first_sync['session']['messages'][-1] == {
        'role': 'user',
        'content': 'current turn',
    }
    user_messages = [
        message for message in first_sync['session']['messages']
        if message.get('role') == 'user'
    ]
    assert user_messages == [{'role': 'user', 'content': 'current turn'}]


def test_upload_preprocessing_error_has_terminal_outcome(tmp_path, monkeypatch):
    llm = MockLLM()
    agent = Agent(
        name="upload-error",
        llm=llm,
        log=False,
        quiet=True,
        co_dir=tmp_path / ".co",
    )

    def fail_decode(_encoded):
        raise ValueError("malformed upload")

    monkeypatch.setattr("connectonion.core.agent.base64.b64decode", fail_decode)

    with pytest.raises(ValueError, match="malformed upload"):
        agent.input(
            "inspect",
            files=[{"name": "bad.txt", "data": "data:text/plain;base64,bad"}],
        )

    assert llm.call_count == 0
    assert outcomes(agent)[0]['reason'] == 'error'
    assert outcomes(agent)[0]['error_type'] == 'ValueError'
    assert agent.current_session['turn'] == 1


def test_partial_multi_file_write_is_rolled_back(tmp_path, monkeypatch):
    agent = Agent(
        name="partial-upload",
        llm=MockLLM(),
        log=False,
        quiet=True,
        co_dir=tmp_path / ".co",
    )
    original_write_bytes = Path.write_bytes
    writes = 0

    def fail_second_write(path, data):
        nonlocal writes
        writes += 1
        if writes == 2:
            original_write_bytes(path, b"partial")
            raise OSError("disk full")
        return original_write_bytes(path, data)

    monkeypatch.setattr(Path, "write_bytes", fail_second_write)

    with pytest.raises(OSError, match="disk full"):
        agent.input(
            "inspect",
            files=[
                {"name": "one.txt", "data": "data:text/plain;base64,b25l"},
                {"name": "two.txt", "data": "data:text/plain;base64,dHdv"},
            ],
        )

    uploads = tmp_path / ".co" / "uploads"
    assert list(uploads.iterdir()) == []
    assert outcomes(agent)[0]['reason'] == 'error'
    assert not any(
        event.get('type') == 'files_received'
        for event in agent.current_session['trace']
    )


def test_upload_cleanup_failure_does_not_replace_write_error(tmp_path, monkeypatch):
    agent = Agent(
        name="cleanup-error",
        llm=MockLLM(),
        log=False,
        quiet=True,
        co_dir=tmp_path / ".co",
    )
    original_write_bytes = Path.write_bytes

    def partial_write_then_fail(path, data):
        original_write_bytes(path, b"partial")
        raise OSError("original disk error")

    def fail_cleanup(path, missing_ok=False):
        raise PermissionError("cleanup denied")

    monkeypatch.setattr(Path, "write_bytes", partial_write_then_fail)
    monkeypatch.setattr(Path, "unlink", fail_cleanup)

    with pytest.raises(OSError, match="original disk error"):
        agent.input(
            "inspect",
            files=[{"name": "one.txt", "data": "data:text/plain;base64,b25l"}],
        )

    assert outcomes(agent)[0]['reason'] == 'error'


def test_logger_setup_error_is_inside_attempted_turn_boundary(tmp_path, monkeypatch):
    agent = Agent(
        name="logger-error",
        llm=MockLLM(),
        log=False,
        quiet=True,
        co_dir=tmp_path / ".co",
    )

    def fail_start(*_args, **_kwargs):
        raise OSError("logger unavailable")

    monkeypatch.setattr(agent.logger, "start_session", fail_start)

    with pytest.raises(OSError, match="logger unavailable"):
        agent.input("work")

    assert outcomes(agent)[0]['reason'] == 'error'
    assert outcomes(agent)[0]['error_type'] == 'OSError'
    assert agent.current_session['turn'] == 1
