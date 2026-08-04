"""The agent asks a question and the client is handed an empty string.

`ask_user` sends the question under `question`:

    event = {
        "type": "ask_user",
        "question": question,
        "options": options,
        "multi_select": multi_select,
    }

`connect.py` reads it under `text`:

    result_text = event.get("text", "")
    ...
    self._add_ui_event({"type": "ask_user", "text": event.get("text"), ...})

No producer sends `text`. `diff_writer` sends `question` too. So every
multi-turn conversation over the network arrives with the question missing.

Measured against a real hosted agent holding the `ask_user` tool, from a client
with its own identity:

    turn 1 done      False          correct
    agent.status     "waiting"      correct
    Response.text    ''             the question
    ui ask_user      text=None, options=['Red','Blue','Green', …]

The options arrive because both sides happen to spell that one the same. So a
client following the documented contract -- "done=False: Agent asked a question"
with the question in `.text` -- renders a list of buttons under a blank prompt.
`multi_select` and `fields` are dropped entirely; a form asked for over the
network cannot be rendered at all.

The suite certified this. tests/unit/test_connect.py builds the event by hand:

    json.dumps({"type": "ask_user", "text": "Which date?"})

and asserts `response.text == "Which date?"`. The fake sends a key the real tool
has never sent, so the test passes on a contract that exists nowhere else. That
fake is corrected in this change rather than left to agree with itself.

`text` is still accepted on the way in. It costs one `or` and means a client
built against the old fake, or any third-party tool that copied it, keeps
working.
"""

import asyncio
import json
from unittest.mock import patch

import pytest

from connectonion.network.connect import RemoteAgent, Response
from tests.unit.test_connect import create_mock_ws


def _ask(event: dict) -> tuple:
    """Run one turn whose only server event is this ask_user frame."""
    agent = RemoteAgent("0x" + "a" * 64)
    ws = create_mock_ws([
        json.dumps({"type": "CONNECTED", "session_id": "s1", "status": "new"}),
        json.dumps(event),
    ])
    with patch("websockets.connect", return_value=ws):
        # asyncio.run, not get_event_loop: another test in the same session may
        # have left no current loop, and then these fail for a reason that has
        # nothing to do with what they are checking.
        response = asyncio.run(agent._stream_input("go", 30.0))
    return response, agent


class TestTheRealEventFromTheRealTool:
    """The shape `useful_tools/ask_user.py` actually sends."""

    def test_the_question_is_the_response_text(self):
        response, _ = _ask({
            "type": "ask_user",
            "question": "Which colour do you prefer?",
            "options": ["Red", "Blue"],
            "multi_select": False,
        })

        assert response.text == "Which colour do you prefer?"

    def test_the_turn_is_not_done(self):
        response, agent = _ask({
            "type": "ask_user", "question": "Which date?", "options": None,
            "multi_select": False,
        })

        assert response.done is False
        assert agent.status == "waiting"

    def test_the_ui_event_carries_the_question(self):
        _, agent = _ask({
            "type": "ask_user", "question": "Which date?", "options": ["Mon"],
            "multi_select": False,
        })
        asked = [e for e in agent.ui if e.get("type") == "ask_user"]

        assert asked and asked[0]["text"] == "Which date?"

    def test_the_options_still_arrive(self):
        """They already did — both sides spell this one the same."""
        _, agent = _ask({
            "type": "ask_user", "question": "Pick", "options": ["Red", "Blue"],
            "multi_select": False,
        })
        asked = [e for e in agent.ui if e.get("type") == "ask_user"]

        assert asked[0]["options"] == ["Red", "Blue"]

    def test_multi_select_arrives(self):
        """Dropped entirely before: the client could not tell one answer from many."""
        _, agent = _ask({
            "type": "ask_user", "question": "Pick some", "options": ["a", "b"],
            "multi_select": True,
        })
        asked = [e for e in agent.ui if e.get("type") == "ask_user"]

        assert asked[0].get("multi_select") is True

    def test_fields_arrive(self):
        """A form asked for over the network could not be rendered at all."""
        fields = [{"name": "email", "label": "Your email"}]
        _, agent = _ask({
            "type": "ask_user", "question": "Details?", "options": None,
            "multi_select": False, "fields": fields,
        })
        asked = [e for e in agent.ui if e.get("type") == "ask_user"]

        assert asked[0].get("fields") == fields


class TestTheOldShapeStillWorks:
    """A client built against the old fake, or a tool that copied it."""

    def test_text_is_still_accepted(self):
        response, _ = _ask({"type": "ask_user", "text": "Which date?"})

        assert response.text == "Which date?"
        assert response.done is False


class TestNeitherKey:

    def test_it_does_not_crash(self):
        response, agent = _ask({"type": "ask_user", "options": ["a"]})

        assert response.done is False
        assert response.text == ""
        assert agent.status == "waiting"


class TestTheProducersAgree:
    """Both tools that raise this event spell the field the same way.

    If a third one appears spelling it differently, this is where that shows.
    """

    @pytest.mark.parametrize("module,attr", [
        ("connectonion.useful_tools.ask_user", "ask_user"),
        ("connectonion.useful_tools.diff_writer", None),
    ])
    def test_the_source_sends_question(self, module, attr):
        import importlib
        import inspect

        source = inspect.getsource(importlib.import_module(module))
        raised = source[source.index('"type": "ask_user"'):]

        assert '"question"' in raised[:400], f"{module} does not send `question`"
