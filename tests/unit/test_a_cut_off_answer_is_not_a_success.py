"""A response the provider cut off at its output limit is not an answer (#1758).

No provider's complete() looked at finish_reason / stop_reason. Half a
migration plan came back as the final answer with `turn_result: natural`, and
a tool call whose JSON arguments were cut mid-string raised JSONDecodeError
out of agent.input() — after the server had charged for 8k output tokens that
agent.total_cost never saw.

Now every provider raises TruncatedResponseError carrying the usage, and the
agent records that cost, tells the model to shorten or split, and tries again.
"""

from types import SimpleNamespace as NS

import pytest

from connectonion import Agent, llm_do
from connectonion.core.exceptions import TruncatedResponseError
from connectonion.core.llm import (
    AnthropicLLM, GeminiLLM, GrokLLM, GroqLLM, MistralLLM, OpenAICompatibleLLM,
    OpenAILLM, OpenOnionLLM, OpenRouterLLM,
)

CUT = "Here is the full migration plan: step 1 ... step 2 ... and then we"
CUT_ARGS = '{"path": "a.py", "content": "def f():\\n    retu'


def openai_usage():
    return NS(prompt_tokens=100, completion_tokens=8192, total_tokens=8292,
              prompt_tokens_details=None, cost_usd=0.02)


def reply(finish, content=None, tool_calls=None):
    message = NS(content=content, tool_calls=tool_calls, refusal=None)
    return NS(choices=[NS(message=message, finish_reason=finish)], usage=openai_usage())


def cut_tool_call():
    return NS(id="c1", function=NS(name="write_file", arguments=CUT_ARGS), extra_content=None)


class Replies:
    def __init__(self, *responses):
        self.responses = list(responses)

    def create(self, **kwargs):
        return self.responses.pop(0)


def managed(*responses):
    llm = OpenOnionLLM(api_key="fake", model="co/gemini-3.8-flash")
    llm.client = NS(chat=NS(completions=Replies(*responses)))
    return llm


OPENAI_SHAPED = [
    lambda: OpenAILLM(api_key="fake", model="gpt-5"),
    lambda: GeminiLLM(api_key="fake", model="gemini-2.5-flash"),
    lambda: GroqLLM(api_key="fake"),
    lambda: GrokLLM(api_key="fake"),
    lambda: OpenRouterLLM(api_key="fake"),
    lambda: MistralLLM(api_key="fake"),
    lambda: OpenOnionLLM(api_key="fake"),
    lambda: OpenAICompatibleLLM(model="local", base_url="http://localhost:1/v1"),
]


@pytest.mark.parametrize("make", OPENAI_SHAPED)
@pytest.mark.parametrize("cut", [
    {"content": CUT},
    {"tool_calls": [cut_tool_call()]},
], ids=["text", "tool_call"])
def test_every_openai_shaped_provider_refuses_a_cut_off_response(make, cut):
    llm = make()
    llm.client = NS(chat=NS(completions=Replies(reply("length", **cut))))

    with pytest.raises(TruncatedResponseError) as caught:
        llm.complete([{"role": "user", "content": "plan"}])

    # The tokens were spent; the error is where they are recorded.
    assert caught.value.usage.output_tokens == 8192
    assert caught.value.content == cut.get("content")


def test_anthropic_refuses_a_response_stopped_at_max_tokens():
    llm = AnthropicLLM(api_key="fake")
    cut = NS(type="tool_use", name="write_file", id="t1", input={"path": "a.py"})
    usage = NS(input_tokens=100, output_tokens=8192,
               cache_read_input_tokens=0, cache_creation_input_tokens=0)
    llm.client = NS(messages=Replies(NS(content=[cut], stop_reason="max_tokens", usage=usage)))

    with pytest.raises(TruncatedResponseError) as caught:
        llm.complete([{"role": "user", "content": "write it"}])

    assert caught.value.usage.output_tokens == 8192


def test_llm_do_does_not_return_half_an_answer(monkeypatch):
    llm_do_module = __import__("connectonion.llm_do", fromlist=["create_llm"])
    monkeypatch.setattr(llm_do_module, "create_llm",
                        lambda **kwargs: managed(reply("length", content=CUT)))

    with pytest.raises(TruncatedResponseError):
        llm_do("plan", model="co/gemini-3.8-flash")


def test_a_cut_off_answer_is_retried_shorter_and_its_cost_kept():
    llm = managed(reply("length", content=CUT), reply("stop", content="Short plan."))
    agent = Agent("t", llm=llm, log=False, quiet=True)

    assert agent.input("plan") == "Short plan."

    assert agent.total_cost == pytest.approx(0.04)
    assert any("cut off" in str(m.get("content")) for m in agent.current_session["messages"])
    statuses = [e.get("status") for e in agent.current_session["trace"]
                if e.get("type") == "llm_result"]
    assert statuses == ["truncated", "success"]
    turn = [e for e in agent.current_session["trace"] if e.get("type") == "turn_result"][-1]
    assert turn["usage"]["cost"] == pytest.approx(0.04)


def test_a_cut_off_tool_call_is_not_run_and_does_not_lose_its_cost():
    wrote = []

    def write_file(path: str, content: str) -> str:
        """Write a file."""
        wrote.append(path)
        return "ok"

    llm = managed(reply("length", tool_calls=[cut_tool_call()]),
                  reply("stop", content="I will write it in parts."))
    agent = Agent("t", llm=llm, tools=[write_file], log=False, quiet=True)

    assert agent.input("write it") == "I will write it in parts."
    assert wrote == []
    assert agent.total_cost == pytest.approx(0.04)


def test_a_model_that_keeps_running_out_fails_the_turn_with_the_cost_recorded():
    llm = managed(*[reply("length", content=CUT) for _ in range(5)])
    agent = Agent("t", llm=llm, log=False, quiet=True)

    with pytest.raises(TruncatedResponseError):
        agent.input("plan")

    calls = [e for e in agent.current_session["trace"] if e.get("type") == "llm_result"]
    assert agent.total_cost == pytest.approx(0.02 * len(calls))
    turn = agent.current_session["trace"][-1]
    assert (turn["type"], turn["reason"]) == ("turn_result", "error")
