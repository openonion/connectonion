"""Session bookkeeping stays on the session. The provider never sees it (#2702).

A reminder is a user message marked ``internal`` so the chat can hide it, and a
watch turn carries ``watch_event`` / ``watch_events`` for the same reason.
``messages_for_provider()`` used to copy every key except ``id``, so a strict
Chat Completions API rejected the next request. Mistral answers that with 422
``Extra inputs are not permitted``, which is how a truncation retry, a file
upload, and an empty-answer reminder died on ``mistral/...`` models.
"""

import json

import httpx
import openai

from connectonion import Agent
from connectonion.core.llm import create_llm
from connectonion.core.provider_messages import messages_for_provider

_SESSION_ONLY = ("id", "internal", "watch_event", "watch_events")


def test_messages_for_provider_drops_session_keys_and_keeps_provider_keys():
    session = [
        {
            "role": "user",
            "content": "plan the migration",
            "name": "planner",
            "id": "msg-1",
            "internal": True,
            "watch_event": {"event_id": "e1", "kind": "file"},
            "watch_events": [{"event_id": "e2"}],
        },
        {
            "role": "assistant",
            "content": None,
            "id": "trace-9",
            "tool_calls": [{
                "id": "call-1",
                "type": "function",
                "function": {"name": "read_file", "arguments": "{}"},
            }],
        },
        {
            "role": "tool",
            "tool_call_id": "call-1",
            "content": "ok",
            "id": "msg-2",
        },
    ]
    original = [dict(message) for message in session]

    sent = messages_for_provider(session)

    assert sent[0] == {
        "role": "user",
        "content": "plan the migration",
        "name": "planner",
    }
    assert sent[1]["role"] == "assistant"
    assert sent[1]["content"] is None
    assert sent[1]["tool_calls"][0]["id"] == "call-1"
    assert sent[2] == {
        "role": "tool",
        "tool_call_id": "call-1",
        "content": "ok",
    }
    for message in sent:
        leaked = [key for key in _SESSION_ONLY if key in message]
        assert leaked == []
    assert session == original


def test_a_mistral_truncation_retry_sends_no_internal_marker():
    """The #1758 retry appends a reminder. The session keeps ``internal``;
    the request Mistral validates does not."""
    bodies = []

    def fake_mistral(request):
        bodies.append(json.loads(request.content))
        finish = "length" if len(bodies) == 1 else "stop"
        return httpx.Response(200, json={
            "id": "c",
            "object": "chat.completion",
            "created": 0,
            "model": "mistral-large-latest",
            "choices": [{
                "index": 0,
                "finish_reason": finish,
                "message": {"role": "assistant", "content": "Short plan."},
            }],
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 10,
                "total_tokens": 30,
            },
        })

    llm = create_llm("mistral/mistral-large-latest", api_key="test-key")
    llm.client = openai.OpenAI(
        api_key="test-key",
        base_url="https://api.mistral.ai/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(fake_mistral)),
    )
    agent = Agent("planner", llm=llm, log=False, quiet=True)

    assert agent.input("Write the migration plan") == "Short plan."

    reminder = bodies[1]["messages"][-1]
    assert reminder["role"] == "user"
    assert "<system-reminder>" in reminder["content"]
    assert set(reminder) <= {"role", "content", "name", "tool_calls", "tool_call_id"}
    assert "internal" not in reminder
    for body in bodies:
        for message in body["messages"]:
            assert not any(key in message for key in _SESSION_ONLY)
    assert any(
        message.get("internal") is True and "<system-reminder>" in message.get("content", "")
        for message in agent.current_session["messages"]
    )
