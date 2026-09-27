"""Every turn of a Host session reaches the model with the agent's system prompt (#1766).

`input_handler` starts a new session as `{"session_id": ...}` with no messages,
and `Agent.input` restored that empty list as it was. So the first turn of
every Host session (HTTP, WebSocket, inbox channels, schedule) went to the
model without the system prompt, and because the next turn continues from
what was stored, no later turn had it either.

Driven through the real `input_handler` with a real Agent; the mock LLM only
records what it was sent.
"""

import pytest

from connectonion import Agent
from connectonion.network.host.http_router import input_handler
from connectonion.network.host.session import Session, SessionStorage
from tests.utils.mock_helpers import LLMResponseBuilder, MockLLM

pytestmark = pytest.mark.usefixtures("own_project")
PROMPT = "You are Probe. Answer in one word."


def host(tmp_path, llm):
    storage = SessionStorage(tmp_path / ".co" / "session_results.jsonl")
    return storage, (lambda: Agent("probe", system_prompt=PROMPT, llm=llm, quiet=True))


def sent(llm, call):
    return llm._calls[call]["messages"]


def test_the_first_turn_of_a_new_session_carries_the_system_prompt(tmp_path):
    llm = MockLLM(responses=[LLMResponseBuilder.text_response("ok")])
    storage, create = host(tmp_path, llm)

    input_handler(create, storage, "hi", 60, session={"session_id": "s1"})

    assert sent(llm, 0)[0] == {"role": "system", "content": PROMPT}


def test_a_later_turn_carries_it_exactly_once(tmp_path):
    llm = MockLLM(responses=[LLMResponseBuilder.text_response("one"), LLMResponseBuilder.text_response("two")])
    storage, create = host(tmp_path, llm)

    input_handler(create, storage, "hi", 60, session={"session_id": "s1"})
    input_handler(create, storage, "again", 60, session={"session_id": "s1"})

    roles = [m["role"] for m in sent(llm, 1)]
    assert roles[0] == "system" and roles.count("system") == 1


def test_a_session_stored_without_it_gets_it_back(tmp_path):
    """Sessions written while this was broken have user/assistant turns and no system message."""
    llm = MockLLM(responses=[LLMResponseBuilder.text_response("ok")])
    storage, create = host(tmp_path, llm)
    storage.save(Session(session_id="s1", status="done", prompt="hi", session={
        "session_id": "s1", "turn": 1, "trace": [],
        "messages": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}],
    }))

    input_handler(create, storage, "again", 60, session={"session_id": "s1"})

    assert sent(llm, 0)[0] == {"role": "system", "content": PROMPT}
    assert [m["role"] for m in sent(llm, 0)][1:] == ["user", "assistant", "user"]
