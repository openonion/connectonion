"""xray.trace() must print the history that exists.

It filtered for type == 'tool_execution', which nothing writes, so it always
took the "no history" branch — even when called from inside a tool with
xray.previous_tools proving the history was right there. The trace vocabulary
was renamed and trace() was not renamed with it.

The field names moved too, so fixing only the type would render `unknown()`
and `0.00ms` for every row: a fix that looks like a fix.

trace() finds the agent by walking the stack for a local named `agent`, so each
test binds one — the name is load-bearing.
"""

import pytest

from connectonion.debug.xray import xray


class FakeAgent:
    def __init__(self, trace):
        self.current_session = {"trace": trace, "user_prompt": "how many left?"}


def _tool_result(name="check_stock", args=None, result="7 units",
                 timing_ms=12.0, status="success", **extra):
    """Exactly the shape tool_executor writes."""
    return {"type": "tool_result", "tool_id": "call_1", "name": name,
            "args": args if args is not None else {"sku": "A1"},
            "status": status, "result": result, "timing_ms": timing_ms, **extra}


def _session_with_a_tool_call():
    return FakeAgent([
        {"type": "user_input", "content": "how many left?"},
        {"type": "llm_call"},
        {"type": "tool_call", "tool_id": "call_1", "name": "check_stock", "args": {"sku": "A1"}},
        _tool_result(),
        {"type": "llm_result"},
    ])


class TestItPrintsAtAll:
    def test_a_session_with_tool_history_is_not_reported_as_empty(self, capsys):
        agent = _session_with_a_tool_call()
        xray.trace()
        assert "No tool execution history" not in capsys.readouterr().out

    def test_the_tool_name_is_rendered_not_unknown(self, capsys):
        """The renderer reads `tool_name`; the writer writes `name`. Fixing only
        the type filter would print `unknown()` on every row."""
        agent = _session_with_a_tool_call()
        xray.trace()
        assert "check_stock" in capsys.readouterr().out

    def test_the_arguments_are_rendered(self, capsys):
        """Renderer reads `arguments`/`parameters`; writer writes `args`."""
        agent = _session_with_a_tool_call()
        xray.trace()
        out = capsys.readouterr().out
        assert "sku" in out and "A1" in out

    def test_the_timing_is_rendered_not_zero(self, capsys):
        """Renderer reads `timing`; writer writes `timing_ms`."""
        agent = _session_with_a_tool_call()
        xray.trace()
        out = capsys.readouterr().out
        assert "12ms" in out or "12.00ms" in out

    def test_the_result_is_rendered(self, capsys):
        agent = _session_with_a_tool_call()
        xray.trace()
        assert "7 units" in capsys.readouterr().out


class TestItStillSaysNothingWhenThereIsNothing:
    def test_a_session_with_no_tool_calls_reports_empty(self, capsys):
        """The message is right when it is true. This fix must not replace it
        with an empty table."""
        agent = FakeAgent([{"type": "user_input"}, {"type": "llm_call"}])
        xray.trace()
        assert "No tool execution history" in capsys.readouterr().out

    def test_an_error_entry_is_rendered_as_an_error(self, capsys):
        agent = FakeAgent([_tool_result(result="Error: boom", status="error", error="boom")])
        xray.trace()
        out = capsys.readouterr().out
        assert "check_stock" in out and "boom" in out
