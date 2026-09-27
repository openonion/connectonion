"""An llm_do inside an agent run is part of that run's cost (#730, #1758).

auto_compact, re_act, reflect, web_fetch, gmail, the browser's element finder
and the intent step each make llm_do calls while agent.input() is running.
None of them reached agent.total_cost — which is also the Control Center's
budget cap — and structured_complete() threw its usage away on every provider,
so a run could spend well past its cap while reporting less.
"""

import importlib
from types import SimpleNamespace as NS

import pytest
from pydantic import BaseModel

from connectonion import Agent, llm_do
from connectonion.core.llm import LLM, LLMResponse, OpenOnionLLM, ToolCall
from connectonion.core.usage import TokenUsage

llm_do_module = importlib.import_module("connectonion.llm_do")


class Verdict(BaseModel):
    value: int


class SideLLM(LLM):
    """What llm_do builds for its one-shot call."""

    def __init__(self):
        self.model = "co/gemini-3.8-flash"

    def complete(self, messages, tools=None, **kwargs):
        return LLMResponse("summary", [], None,
                           TokenUsage(input_tokens=40, output_tokens=10, cost=0.25))

    def structured_complete(self, messages, output_schema, **kwargs):
        self.last_structured_usage = TokenUsage(input_tokens=40, output_tokens=2, cost=0.5)
        return output_schema(value=1)


class MainLLM(LLM):
    """Calls one tool, then answers."""

    def __init__(self):
        self.model = "main"
        self.turns = 0

    def complete(self, messages, tools=None, **kwargs):
        self.turns += 1
        usage = TokenUsage(input_tokens=1, output_tokens=1, cost=1.0)
        if self.turns == 1:
            return LLMResponse(None, [ToolCall("summarise", {}, "c1")], None, usage)
        return LLMResponse("done", [], None, usage)

    def structured_complete(self, messages, output_schema, **kwargs):
        raise NotImplementedError


def summarise() -> str:
    """Summarise with two side calls."""
    llm_do("shorten this")
    return str(llm_do("score this", output=Verdict).value)


def test_side_calls_in_a_tool_land_on_total_cost_and_the_trace(monkeypatch):
    monkeypatch.setattr(llm_do_module, "create_llm", lambda **kwargs: SideLLM())
    agent = Agent("t", llm=MainLLM(), tools=[summarise], log=False, quiet=True)

    assert agent.input("go") == "done"

    assert agent.total_cost == pytest.approx(2.0 + 0.25 + 0.5)
    side = [e for e in agent.current_session["trace"]
            if e.get("type") == "llm_result" and e.get("source") == "llm_do"]
    assert [e["usage"]["cost"] for e in side] == [0.25, 0.5]
    turn = agent.current_session["trace"][-1]
    assert turn["usage"]["cost"] == pytest.approx(2.75)


def test_llm_do_outside_a_run_records_nothing_anywhere(monkeypatch):
    monkeypatch.setattr(llm_do_module, "create_llm", lambda **kwargs: SideLLM())
    agent = Agent("t", llm=MainLLM(), log=False, quiet=True)

    assert llm_do("hello") == "summary"
    assert agent.total_cost == 0


def test_structured_complete_keeps_the_usage_it_was_billed():
    usage = NS(prompt_tokens=50, completion_tokens=5, total_tokens=55,
               prompt_tokens_details=None, cost_usd=0.0007)
    llm = OpenOnionLLM(api_key="fake", model="co/gemini-3.8-flash")
    llm.client = NS(beta=NS(chat=NS(completions=NS(parse=lambda **kw: NS(
        choices=[NS(message=NS(parsed=Verdict(value=391)), finish_reason="stop")],
        usage=usage)))))

    assert llm.structured_complete([{"role": "user", "content": "x"}], Verdict).value == 391
    assert llm.last_structured_usage.cost == pytest.approx(0.0007)


def test_a_tool_on_the_interruptible_worker_thread_still_finds_the_run():
    """Hosted runs execute tools on a worker thread; a new thread starts with an
    empty context unless it is handed one."""
    import contextvars

    from connectonion.core.interrupt import run_interruptible

    marker = contextvars.ContextVar("marker", default=None)
    marker.set("the run")

    seen, interrupted = run_interruptible(marker.get, io=None, timeout_seconds=5)

    assert (seen, interrupted) == ("the run", False)
