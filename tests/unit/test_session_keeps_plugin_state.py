"""What survives a session round-trip, and who gets to decide it.

`Agent.input(session=…)` rebuilt current_session from four keys — session_id,
messages, trace, turn — and dropped everything else. Plugins keep their state
there, so Full access lost `mode` and `turns_left` on every turn and silently
fell back to Auto: the web client visibly stepped back after a turn
or two, and over HTTP, where mode_change messages do not exist, Full access never
worked at all. #191.

The same drop quietly disabled the approval gate added in #579: the host writes
`session['requester']`, input() threw it away, and every requester looked
unknown — which is the path that behaves as before.

Keeping everything is not the fix. `merge_sessions` picks the client's session
or the server's wholesale, so a client that wins the merge would be handing the
agent its own authority state. A defined set of keys is therefore
the server's to state, taken from what it stored and never from what arrived.
"""

from connectonion import Agent
from connectonion.network.host.http_router import input_handler
from connectonion.network.host.session import Session, SessionStorage
from tests.utils.mock_helpers import MockLLM


class TestInputKeepsWhatItIsGiven:

    def test_plugin_fields_survive_a_restore(self):
        agent = Agent("a", llm=MockLLM())

        agent.input("hi", session={
            'session_id': 's1', 'messages': [], 'trace': [], 'turn': 0,
            'mode': 'full-access', 'turns_left': 4,
        })

        assert agent.current_session.get('mode') == 'full-access'
        assert agent.current_session.get('turns_left') == 4

    def test_legacy_plugin_fields_are_discarded_before_the_turn_runs(self):
        agent = Agent("a", llm=MockLLM())

        agent.input("hi", session={
            'session_id': 's1', 'messages': [], 'trace': [], 'turn': 0,
            'mode': 'ulw', 'ulw_turns': 5, 'ulw_turns_used': 1,
            'skip_tool_approval': True,
        })

        assert agent.current_session.get('mode') == 'auto'
        assert 'full_access_turns' not in agent.current_session
        assert 'ulw_turns' not in agent.current_session

    def test_malformed_full_access_state_is_removed_before_the_turn_runs(self):
        agent = Agent("a", llm=MockLLM())

        agent.input("hi", session={
            'session_id': 's1', 'messages': [], 'trace': [], 'turn': 0,
            'mode': ':danger-full-access', 'full_access_turns': 5,
            'full_access_turns_used': 5, 'skip_tool_approval': True,
        })

        assert agent.current_session.get('mode') == 'auto'
        assert 'skip_tool_approval' not in agent.current_session

    def test_the_requester_survives_a_restore(self):
        """#579's gate reads this. Dropped, it silently does nothing."""
        agent = Agent("a", llm=MockLLM())

        agent.input("hi", session={
            'session_id': 's1', 'messages': [], 'trace': [], 'turn': 0,
            'requester': {'address': '0xbeef', 'level': 'contact'},
        })

        assert agent.current_session.get('requester') == {
            'address': '0xbeef', 'level': 'contact'}

    def test_the_known_four_are_still_normalised(self):
        agent = Agent("a", llm=MockLLM())
        messages = [{'role': 'user', 'content': 'x'}]

        agent.input("hi", session={'session_id': 's2', 'messages': messages,
                                   'trace': [], 'turn': 3})

        assert agent.current_session['session_id'] == 's2'
        assert agent.current_session['turn'] == 4, "the turn continued from 3"
        assert agent.current_session['messages'] is not messages, (
            "the caller's list must not be aliased into the live session"
        )


class TestTheClientDoesNotGrantItself:
    """A session dict arrives from the client. Some of its keys are answers the
    server already gave, and those it does not get to change."""

    def _run(self, tmp_path, client_session, stored_session=None):
        seen = {}

        class Probe:
            def __init__(self):
                self.io = None
                self.storage = None
                self.current_session = {}

            def input(self, prompt, session=None, **kw):
                seen.update(session or {})
                self.current_session = dict(session or {})
                return 'ok'

        storage = SessionStorage(tmp_path / '.co' / 'sessions.jsonl')
        if stored_session is not None:
            storage.save(Session(session_id='s1', status='done', prompt='p',
                                 session=stored_session))
        input_handler(Probe, storage, 'hi', 60, session=client_session)
        return seen

    def test_a_client_cannot_bring_its_own_approval_bypass(self, tmp_path):
        seen = self._run(tmp_path, {
            'session_id': 's1', 'messages': [], 'trace': [], 'turn': 0,
            'skip_tool_approval': True,
        })

        assert not seen.get('skip_tool_approval'), (
            "a client handed itself a bypass of every approval check"
        )

    def test_a_client_cannot_bring_its_own_permissions(self, tmp_path):
        seen = self._run(tmp_path, {
            'session_id': 's1', 'messages': [], 'trace': [], 'turn': 0,
            'permissions': {'bash': {'allowed': True, 'source': 'user'}},
        })

        assert not seen.get('permissions')

    def test_the_servers_own_full_access_state_is_restored(self, tmp_path):
        """The point of keeping these at all: state the server set, persisting."""
        seen = self._run(
            tmp_path,
            {'session_id': 's1', 'messages': [], 'trace': [], 'turn': 0},
            stored_session={'session_id': 's1', 'messages': [], 'trace': [],
                            'turn': 0, 'mode': 'full-access', 'turns_left': 5},
        )

        assert seen.get('mode') == 'full-access'
        assert seen.get('turns_left') == 5
