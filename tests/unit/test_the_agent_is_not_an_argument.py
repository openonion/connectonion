"""What a trace entry is allowed to hold.

Tools that declare `agent` in their signature get the live Agent injected so
they can reach `agent.io`. That injection mutated the caller's dict in place:

    trace_entry["args"] = tool_args      # by reference
    ...
    tool_args['agent'] = agent           # now the trace holds an Agent
    ...
    agent._record_trace(trace_entry)     # forwarded over the socket
    ...
    finally:
        tool_args.pop('agent', None)     # too late to matter

In host/WebSocket mode the agent runs on its own thread while the forwarder
drains queued messages, so the window between recording the trace and clearing
the field is a window in which an Agent object is being JSON-encoded. The
existing comment on that `pop` says it exists to prevent exactly that warning,
so the hazard was known and the mitigation was a race.

The fix is not a narrower window. `agent` is not an argument the model supplied
— it is plumbing — and it does not belong in the record of what was called.
"""

import json

import pytest

from connectonion.core.tool_executor import execute_single_tool


class FakeLogger:
    def print(self, *a, **k): pass
    def log_tool_call(self, *a, **k): pass
    def log_tool_result(self, *a, **k): pass


class RecordingAgent:
    """Captures every trace at the moment it is recorded, not afterwards."""

    def __init__(self):
        self.io = None
        self.recorded = []
        self.current_session = {'messages': [], 'trace': [], 'turn': 1,
                                'iteration': 0}

    def _invoke_events(self, name):
        # The real path calls this between recording the tool_call trace and
        # injecting the agent. A fake without it raises, gets swallowed by the
        # except, and the test passes having exercised nothing.
        pass

    def _record_trace(self, entry):
        # A copy, because the point is what the entry held *then* — the finally
        # block cleans up after, and asserting later would test the cleanup.
        self.recorded.append({k: dict(v) if isinstance(v, dict) else v
                              for k, v in entry.items()})


def _tools_with(func, name='needs_agent_tool'):
    func._needs_agent = True
    func.__name__ = name

    class Registry:
        def get(self, n):
            return func if n == name else None
    return Registry()


class TestATraceCarriesNoLiveObjects:

    def test_the_injected_agent_never_reaches_a_recorded_trace(self):
        def tool(x, agent=None):
            return f"got {x}"

        agent = RecordingAgent()
        execute_single_tool('needs_agent_tool', {'x': 1}, 'id1',
                            _tools_with(tool), agent, FakeLogger())

        assert agent.recorded, "nothing was recorded"
        for entry in agent.recorded:
            assert 'agent' not in entry.get('args', {}), (
                "a live Agent was in the trace at the moment it was recorded — "
                "the forwarder thread can serialise it there"
            )

    def test_a_recorded_trace_is_json_encodable(self):
        """The property that actually matters downstream."""
        def tool(x, agent=None):
            return "ok"

        agent = RecordingAgent()
        execute_single_tool('needs_agent_tool', {'x': 1}, 'id1',
                            _tools_with(tool), agent, FakeLogger())

        for entry in agent.recorded:
            json.dumps(entry)  # raises TypeError if an Agent slipped in

    def test_it_holds_for_the_error_path_too(self):
        """Both paths record before the finally runs."""
        def tool(x, agent=None):
            raise RuntimeError('boom')

        agent = RecordingAgent()
        execute_single_tool('needs_agent_tool', {'x': 1}, 'id1',
                            _tools_with(tool), agent, FakeLogger())

        for entry in agent.recorded:
            assert 'agent' not in entry.get('args', {})
            json.dumps(entry)

    def test_the_tool_still_receives_the_agent(self):
        """Keeping it out of the trace must not keep it from the tool."""
        seen = {}

        def tool(x, agent=None):
            seen['agent'] = agent
            return "ok"

        agent = RecordingAgent()
        execute_single_tool('needs_agent_tool', {'x': 1}, 'id1',
                            _tools_with(tool), agent, FakeLogger())

        assert seen['agent'] is agent

    def test_the_callers_dict_is_not_mutated(self):
        """The caller passed these arguments; they are not ours to edit."""
        def tool(x, agent=None):
            return "ok"

        args = {'x': 1}
        agent = RecordingAgent()
        execute_single_tool('needs_agent_tool', args, 'id1',
                            _tools_with(tool), agent, FakeLogger())

        assert args == {'x': 1}


class TestBothCallPaths:
    """There are two invocations, and only one of them was changed at first.

    A sync-only test passes while an async tool that declares `agent` gets
    called without it — a TypeError at the point the tool runs, in the path
    no unit test was covering.
    """

    def test_an_async_tool_also_receives_the_agent(self):
        seen = {}

        async def tool(x, agent=None):
            seen['agent'] = agent
            return "ok"

        agent = RecordingAgent()
        execute_single_tool('needs_agent_tool', {'x': 1}, 'id1',
                            _tools_with(tool), agent, FakeLogger())

        assert seen.get('agent') is agent, (
            "the async call site still passes the un-injected dict"
        )

    def test_an_async_tools_trace_is_also_clean(self):
        async def tool(x, agent=None):
            return "ok"

        agent = RecordingAgent()
        execute_single_tool('needs_agent_tool', {'x': 1}, 'id1',
                            _tools_with(tool), agent, FakeLogger())

        for entry in agent.recorded:
            assert 'agent' not in entry.get('args', {})
            json.dumps(entry)
