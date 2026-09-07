"""`co eval` writes a record in which every measured field is empty.

The file it saves is meant to be compared across runs — did this change make the
agent slower, chattier, more expensive? Three of its fields cannot answer that,
because each reads the trace by a name the trace does not use:

    tokens         summed from `llm_call`      usage lives on `llm_result`
    cost           summed from `llm_call`      same
    tools_called   filtered by `tool_execution`  the entries are `tool_result`

So every saved eval says 0 tokens, $0.0 and no tools, whatever the agent did.
`tool_execution` is not a typo anyone made twice: it is what
`core/tool_executor.py`'s module note still claims to write, and the note is
stale. `logger.py` reads `tool_result` and is right.

The same `llm_call` mistake was in the run summary line — see
tests/unit/test_the_run_summary_counts_the_run.py. Two readers of one trace,
both counting the entry that is written before there is anything to count.
"""

import pytest

from connectonion.cli.commands.eval_commands import summarise_run
from connectonion.core.usage import TokenUsage
from connectonion.logger import Logger


def _format(entry):
    """The real formatter the command passes, not a stand-in for it."""
    return Logger.__new__(Logger)._format_tool_call(entry)


def _usage(input_tokens, output_tokens, cost):
    """model_dump(), because that is the shape agent.py records."""
    return TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens,
                      cost=cost).model_dump()


TRACE = [
    {"type": "user_input", "content": "What is 17 plus 25?"},
    {"type": "llm_call", "model": "co/gemini-3.7-flash", "status": "pending"},
    {"type": "llm_result", "usage": _usage(80, 18, 0.00102)},
    {"type": "tool_call", "name": "add", "args": {"a": 17, "b": 25}},
    {"type": "tool_result", "name": "add", "args": {"a": 17, "b": 25},
     "result": "42", "status": "success"},
    {"type": "llm_call", "model": "co/gemini-3.7-flash", "status": "pending"},
    {"type": "llm_result", "usage": _usage(213, 11, 0.00053)},
]


class TestWhatTheRunCost:

    def test_the_tokens_are_counted(self):
        assert summarise_run(TRACE, _format)["tokens"] == 322

    def test_the_cost_is_counted(self):
        assert summarise_run(TRACE, _format)["cost"] == pytest.approx(0.00155)

    def test_a_run_with_no_model_call_is_zero(self):
        assert summarise_run([{"type": "user_input"}], _format)["tokens"] == 0

    def test_a_result_without_usage_is_skipped_not_crashed(self):
        """Some providers return no usage block."""
        assert summarise_run([{"type": "llm_result", "usage": None}], _format)["cost"] == 0


class TestWhatTheAgentDid:

    def test_the_tools_it_called_are_named(self):
        assert summarise_run(TRACE, _format)["tools_called"] == ["add(a=17, b=25)"]

    def test_a_run_with_no_tools_lists_none(self):
        trace = [t for t in TRACE if not t["type"].startswith("tool_")]

        assert summarise_run(trace, _format)["tools_called"] == []

    def test_each_tool_appears_once(self):
        """tool_call and tool_result are both in the trace for one call; the
        summary counts the completed one."""
        assert len(summarise_run(TRACE, _format)["tools_called"]) == 1
