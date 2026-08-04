"""Every tool spins forever in a live client.

`tool_call` and `tool_result` are two events, each with its own event `id`. What
they share is `tool_id` — the LLM's call id, which is what correlates them. The
producer says so:

    "tool_id": tool_id,  # LLM's tool call ID for client-side matching

The client correlates on `id`:

    tool_id = event.get("id")
    for ui_event in self._ui_events:
        if ui_event.get("type") == "tool_call" and ui_event.get("id") == tool_id:
            ui_event["status"] = "done" if ... else "error"

so the match never succeeds. Captured off the wire from a real hosted agent
running a real tool:

    tool_call    id='cce032b5-8037…'  tool_id='function-call-…'  status=None
    tool_result  id='dac9873f-9ee8…'  tool_id='function-call-…'  status=success  result='42'

    ui tool_call entries: [('cce032b5-…', 'running')]

The tool returned 42 and the entry it belongs to still says `running`. Nothing
ever moves it off that, so a client rendering the live stream shows every tool
spinning for the rest of the session, and never shows a result.

The replayed path already gets this right — `session/ui.py` keys on
`entry.get('tool_id')` — so a page that reloads shows the finished state while
the live view of the same turn does not.

Same shape as #676, found by the sweep that #676 prompted: the client reads a
field the producer fills with something else. The frames below are the ones
captured above, not invented, because a fake that agrees with the reader is what
let both of these live this long.
"""

import pytest

from connectonion.network.connect import RemoteAgent


CALL = {
    "type": "tool_call",
    "id": "cce032b5-8037-4452-9f07-3d1ab4551588",
    "tool_id": "function-call-16919299771",
    "name": "add_two_numbers",
    "args": {"a": 17, "b": 25},
    "session_id": "s1",
    "ts": 1,
}

RESULT = {
    "type": "tool_result",
    "id": "dac9873f-9ee8-4c1e-9d2e-2f0b6d5f9a11",
    "tool_id": "function-call-16919299771",
    "name": "add_two_numbers",
    "status": "success",
    "result": "42",
    "session_id": "s1",
    "ts": 2,
}


@pytest.fixture
def agent():
    return RemoteAgent("0x" + "a" * 64)


def _tool_entries(agent):
    return [e for e in agent.ui if e.get("type") == "tool_call"]


class TestTheResultReachesItsCall:

    def test_the_call_stops_running(self, agent):
        agent._handle_stream_event(CALL)
        agent._handle_stream_event(RESULT)

        assert _tool_entries(agent)[0]["status"] == "done"

    def test_the_result_is_shown(self, agent):
        agent._handle_stream_event(CALL)
        agent._handle_stream_event(RESULT)

        assert _tool_entries(agent)[0]["result"] == "42"

    def test_a_failure_says_error(self, agent):
        agent._handle_stream_event(CALL)
        agent._handle_stream_event({**RESULT, "status": "error", "result": "boom"})

        assert _tool_entries(agent)[0]["status"] == "error"

    def test_two_calls_in_one_turn_each_get_their_own_result(self, agent):
        second_call = {**CALL, "id": "other-event-id", "tool_id": "function-call-2",
                       "args": {"a": 1, "b": 2}}
        second_result = {**RESULT, "id": "another-event-id",
                         "tool_id": "function-call-2", "result": "3"}

        agent._handle_stream_event(CALL)
        agent._handle_stream_event(second_call)
        agent._handle_stream_event(RESULT)
        agent._handle_stream_event(second_result)

        assert [e["result"] for e in _tool_entries(agent)] == ["42", "3"]


class TestWhatTheEntryStillCarries:
    """The UI event's own `id` is what a client keys its rendering on."""

    def test_the_event_id_is_unchanged(self, agent):
        agent._handle_stream_event(CALL)

        assert _tool_entries(agent)[0]["id"] == CALL["id"]

    def test_the_name_and_args_survive(self, agent):
        agent._handle_stream_event(CALL)
        entry = _tool_entries(agent)[0]

        assert entry["name"] == "add_two_numbers"
        assert entry["args"] == {"a": 17, "b": 25}

    def test_it_starts_running(self, agent):
        agent._handle_stream_event(CALL)

        assert _tool_entries(agent)[0]["status"] == "running"


class TestAProducerWithoutToolId:
    """Older frames, or a tool that does not set one — match on `id` as before."""

    def test_matching_ids_still_correlate(self, agent):
        agent._handle_stream_event({k: v for k, v in CALL.items() if k != "tool_id"})
        agent._handle_stream_event({k: v for k, v in RESULT.items() if k != "tool_id"}
                                   | {"id": CALL["id"]})

        assert _tool_entries(agent)[0]["status"] == "done"

    def test_an_unmatched_result_changes_nothing(self, agent):
        agent._handle_stream_event(CALL)
        agent._handle_stream_event({**RESULT, "tool_id": "belongs-to-another-call"})

        assert _tool_entries(agent)[0]["status"] == "running"


class TestTheProducerAndTheReplayAgree:
    """`session/ui.py` already correlates on tool_id; this is the live half."""

    def test_the_replay_path_keys_on_tool_id(self):
        import inspect

        from connectonion.network.host.session import ui

        assert "tool_id" in inspect.getsource(ui), (
            "the replayed path stopped using tool_id; the two halves have diverged again"
        )
