"""Unit tests for connectonion/core/agent.py error & edge-case paths in the iteration loop.

Focus: exit conditions and propagation behaviors NOT covered by test_agent.py.
"""

import pytest

from connectonion import Agent
from connectonion.core.events import on_stop_signal
from connectonion.core.exceptions import InsufficientCreditsError
from connectonion.core.llm import LLMResponse, ToolCall
from connectonion.core.usage import TokenUsage
from tests.utils.mock_helpers import MockLLM


# ---------- max iterations ----------

def test_max_iterations_returns_incomplete_message():
    """When LLM keeps requesting tools past max_iterations, return a 'Task incomplete' message."""
    # Always return a tool call → loop never naturally exits
    def always_tool_call(messages, tools):
        return LLMResponse(
            content=None,
            tool_calls=[ToolCall(name="noop", arguments={}, id="t1")],
            raw_response={},
            usage=TokenUsage(),
        )

    def noop():
        """Returns nothing useful — keeps loop going."""
        return "ok"

    agent = Agent(
        name="loop_capped",
        llm=MockLLM(on_complete=always_tool_call),
        tools=[noop],
        max_iterations=3,
        log=False,
    )
    result = agent.input("go")
    assert "Maximum iterations" in result
    assert "3" in result


def test_max_iterations_can_be_overridden_per_input():
    """Per-call max_iterations overrides the agent default."""
    def always_tool_call(messages, tools):
        return LLMResponse(
            content=None,
            tool_calls=[ToolCall(name="noop", arguments={}, id="t1")],
            raw_response={},
            usage=TokenUsage(),
        )

    def noop():
        return "ok"

    agent = Agent(
        name="loop_override",
        llm=MockLLM(on_complete=always_tool_call),
        tools=[noop],
        max_iterations=100,
        log=False,
    )
    result = agent.input("go", max_iterations=2)
    assert "Maximum iterations (2)" in result


# ---------- stop_signal short-circuit ----------

def test_stop_signal_breaks_loop_and_fires_on_stop_signal_event():
    """A plugin can set current_session['stop_signal'] = True to pause the loop."""
    stop_handler_calls = []

    @on_stop_signal
    def record_stop(agent):
        stop_handler_calls.append(agent.current_session['iteration'])

    def set_stop_then_finish(messages, tools):
        # First call: request a tool. Second call would have happened, but the
        # tool sets stop_signal in after_each_tool — wait, plugin can also set it.
        return LLMResponse(
            content=None,
            tool_calls=[ToolCall(name="trigger_stop", arguments={}, id="t1")],
            raw_response={},
            usage=TokenUsage(),
        )

    def trigger_stop(agent):
        """Tool that needs agent; sets stop_signal to break loop."""
        agent.current_session['stop_signal'] = True
        return "stopping"

    # tool_factory detects `agent` arg and injects at call time
    agent = Agent(
        name="stoppable",
        llm=MockLLM(on_complete=set_stop_then_finish),
        tools=[trigger_stop],
        on_events=[record_stop],
        log=False,
    )
    result = agent.input("go")
    assert result == "What would you like me to do?"
    assert len(stop_handler_calls) == 1


# ---------- LLM exception propagation ----------

class _FakeAPIError(Exception):
    """Stand-in for openai.APIStatusError carrying a 402 detail body."""
    def __init__(self, balance, required, shortfall):
        super().__init__("402")
        self.body = {'detail': {
            'balance': balance, 'required': required, 'shortfall': shortfall,
            'address': '0xabc', 'public_key': '0xdef', 'message': 'no credits',
        }}


def test_insufficient_credits_propagates_to_caller():
    """LLM raising InsufficientCreditsError must NOT be retried — bubble up so the caller
    can show a meaningful credit-shortage message."""

    def credit_failure(messages, tools):
        raise InsufficientCreditsError(_FakeAPIError(0.01, 0.05, 0.04))

    agent = Agent(
        name="poor",
        llm=MockLLM(on_complete=credit_failure),
        log=False,
    )
    with pytest.raises(InsufficientCreditsError) as exc:
        agent.input("hello")
    assert exc.value.shortfall == 0.04
    assert exc.value.balance == 0.01


def test_generic_llm_exception_propagates():
    """Any LLM exception (network, rate-limit, etc.) must propagate, not silently retry."""

    def rate_limit(messages, tools):
        raise RuntimeError("429 Too Many Requests")

    agent = Agent(name="ratelimited", llm=MockLLM(on_complete=rate_limit), log=False)
    with pytest.raises(RuntimeError, match="429"):
        agent.input("hi")


# ---------- tool error captured in trace, loop continues ----------

def test_tool_exception_does_not_crash_agent_and_is_recorded_in_trace():
    """If a tool raises, the agent should record the error and let the LLM see it,
    not propagate to the caller (LLM gets a chance to retry / explain)."""

    # First call: ask for tool. Second call: respond after seeing tool error.
    responses = [
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(name="boom", arguments={}, id="t1")],
            raw_response={},
            usage=TokenUsage(),
        ),
        LLMResponse(
            content="I saw the tool failed and am giving up.",
            tool_calls=[],
            raw_response={},
            usage=TokenUsage(),
        ),
    ]

    def boom():
        """Always raises."""
        raise ValueError("boom!")

    agent = Agent(
        name="resilient",
        llm=MockLLM(responses=responses),
        tools=[boom],
        log=False,
    )
    result = agent.input("trigger boom")
    assert "tool failed" in result

    # Trace must contain a tool entry with error info
    trace = agent.current_session['trace']
    tool_entries = [e for e in trace if e.get('type') == 'tool_call']
    assert tool_entries, "expected tool_call trace entry"
    failed = [e for e in tool_entries if e.get('status') == 'error' or 'error' in (e.get('result') or '').lower() or 'boom' in str(e).lower()]
    assert failed, f"expected an error-marked tool entry, got: {tool_entries}"


# ---------- empty tool list edge case ----------

def test_agent_with_no_tools_still_runs_when_llm_returns_content():
    agent = Agent(
        name="toolless",
        llm=MockLLM(responses=[LLMResponse(
            content="just text",
            tool_calls=[],
            raw_response={},
            usage=TokenUsage(),
        )]),
        log=False,
    )
    assert agent.input("hi") == "just text"
