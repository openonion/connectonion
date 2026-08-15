"""Who is allowed to answer an approval prompt.

The host knows exactly who is on the socket: CONNECT is signed, and the trust
layer classifies the caller as admin / whitelist / contact / blocked before
the session exists. That answer was computed and dropped — `approval.py` had
zero references to the requester.

An operator-issued invite is the normal B2B user grant. A contact can approve
ordinary work in the session authenticated as that contact. Admin status is
reserved for control-plane routes; strangers and blocked identities cannot use
an approval dialog to cross the trust boundary.
"""

import pytest

from connectonion.useful_plugins.tool_approval import check_approval


class FakeIO:
    def __init__(self, responses=None):
        self.responses = responses or [{'approved': True}]
        self.sent = []
        self.i = 0

    def send(self, event):
        self.sent.append(event)

    def receive(self):
        if self.i < len(self.responses):
            self.i += 1
            return self.responses[self.i - 1]
        return {'type': 'io_closed'}

    def receive_all(self, msg_type=None):
        return []


class FakeAgent:
    def __init__(self, io=None, requester=None):
        self.io = io
        self.storage = None
        self.current_session = {'messages': [], 'trace': [], 'pending_tool': None}
        if requester is not None:
            self.current_session['requester'] = requester


DANGEROUS = {'name': 'bash', 'arguments': {'command': 'rm -rf build',
                                           'description': 'clean'}}


class TestAuthenticatedUsersCanApproveTheirOwnWork:

    @pytest.mark.parametrize("level", ['contact', 'whitelist', 'admin'])
    def test_a_contact_or_admin_is_shown_the_dialog(self, level):
        io = FakeIO(responses=[{'approved': True}])
        agent = FakeAgent(io=io, requester={'address': '0x' + 'e' * 64,
                                            'level': level})
        agent.current_session['pending_tool'] = DANGEROUS

        check_approval(agent)

        assert [event['type'] for event in io.sent] == ['approval_needed']

    @pytest.mark.parametrize("level", ['stranger', 'blocked', None])
    def test_an_untrusted_requester_is_not_shown_the_dialog(self, level):
        io = FakeIO()
        agent = FakeAgent(io=io, requester={'address': '0x' + 'e' * 64,
                                            'level': level})
        agent.current_session['pending_tool'] = DANGEROUS

        with pytest.raises(ValueError) as exc:
            check_approval(agent)

        assert io.sent == []
        assert 'authenticated contact or admin' in str(exc.value)

    def test_a_safe_tool_is_unaffected_for_everyone(self):
        """This gates approval, not access. A contact may still use the agent."""
        io = FakeIO()
        agent = FakeAgent(io=io, requester={'address': '0x' + 'e' * 64,
                                            'level': 'contact'})
        agent.current_session['pending_tool'] = {'name': 'read_file',
                                                 'arguments': {'path': 'a.md'}}

        check_approval(agent)

        assert io.sent == []

    def test_a_contact_cannot_approve_rewriting_protected_policy(self):
        io = FakeIO(responses=[{'approved': True}])
        agent = FakeAgent(io=io, requester={'address': '0x' + 'e' * 64,
                                            'level': 'contact'})
        agent.current_session['pending_tool'] = {
            'name': 'write',
            'arguments': {'path': '.co/host.yaml', 'content': 'permissions: {}'},
        }

        with pytest.raises(ValueError) as exc:
            check_approval(agent)

        assert io.sent == []
        assert 'does not get to write it' in str(exc.value)


class TestAnUnknownRequester:
    """No requester recorded means the session did not come through the host.

    A local `co ai` run is exactly that, and it must keep working. The rule is
    about a socket with someone else on it, not about the absence of a field.
    """

    def test_no_requester_recorded_behaves_as_before(self):
        io = FakeIO(responses=[{'approved': True}])
        agent = FakeAgent(io=io)
        agent.current_session['pending_tool'] = DANGEROUS

        check_approval(agent)

        assert len(io.sent) == 1


class TestTheClientCannotDeclareItsOwnLevel:
    """The session dict round-trips through the client, so it is their input.

    A client sends its session back on every turn and the server merges it. If
    the requester's level were read from there, claiming to be the operator
    would be a matter of editing one JSON field — a worse hole than the one
    this closes, introduced by closing it.

    So the level is recomputed from the signed address every turn and
    overwrites whatever arrived.
    """

    def test_a_forged_requester_is_overwritten(self, tmp_path, monkeypatch):
        from connectonion.network.host.http_router import input_handler
        from connectonion.network.host.session import SessionStorage

        monkeypatch.chdir(tmp_path)
        (tmp_path / '.co').mkdir()
        seen = {}

        class Agent:
            def __init__(self):
                self.io = None
                self.storage = None
                self.current_session = {}

            def input(self, prompt, session=None, **kw):
                seen['requester'] = (session or {}).get('requester')
                self.current_session = dict(session or {})
                return 'ok'

        forged = {'session_id': 'abc', 'requester': {'address': '0xdead',
                                                     'level': 'admin'}}

        input_handler(Agent, SessionStorage(tmp_path / '.co' / 'sessions.jsonl'), 'hi', 60,
                      session=forged, requester={'address': '0xbeef',
                                                 'level': 'contact'})

        assert seen['requester'] == {'address': '0xbeef', 'level': 'contact'}, (
            "the client's own claim about its level survived into the session"
        )


class TestTheLevelTheHostActuallyComputes:
    """The gate compares against a value real code has to be able to produce.

    The first version of this compared `get_level(...) != 'admin'`, and every
    test passed — because every test wrote `level: 'admin'` by hand. `get_level`
    returns stranger / contact / whitelist / blocked and never 'admin', so the
    gate would have refused the owner too: nobody could approve anything over
    a socket.

    This test goes through the resolver the host uses, so agreeing with the
    implementation is not enough to pass it.
    """

    def _resolve(self, address, tmp_path):
        from connectonion.network.trust import TrustAgent
        trust = TrustAgent('careful')
        return {'address': address,
                'level': 'admin' if trust.is_admin(address)
                         else trust.get_level(address)}

    def test_an_address_in_admins_txt_resolves_to_admin(self, tmp_path, monkeypatch):
        owner = '0x' + '1' * 64
        co = tmp_path / '.co'
        co.mkdir()
        (co / 'admins.txt').write_text(owner + '\n')
        monkeypatch.chdir(tmp_path)

        requester = self._resolve(owner, tmp_path)

        assert requester['level'] == 'admin', (
            "the owner does not resolve to the level the gate requires, so "
            "nobody could approve anything"
        )

    def test_the_owner_is_still_shown_the_dialog(self, tmp_path, monkeypatch):
        owner = '0x' + '1' * 64
        co = tmp_path / '.co'
        co.mkdir()
        (co / 'admins.txt').write_text(owner + '\n')
        monkeypatch.chdir(tmp_path)

        io = FakeIO(responses=[{'approved': True}])
        agent = FakeAgent(io=io, requester=self._resolve(owner, tmp_path))
        agent.current_session['pending_tool'] = DANGEROUS

        check_approval(agent)

        assert len(io.sent) == 1

    def test_someone_not_in_admins_txt_is_not_admin(self, tmp_path, monkeypatch):
        co = tmp_path / '.co'
        co.mkdir()
        (co / 'admins.txt').write_text('0x' + '1' * 64 + '\n')
        monkeypatch.chdir(tmp_path)

        requester = self._resolve('0x' + '2' * 64, tmp_path)

        assert requester['level'] != 'admin'

    def test_the_real_whitelist_level_can_approve(self, tmp_path, monkeypatch):
        from connectonion.network.trust import TrustAgent

        address = '0x' + '3' * 64
        (tmp_path / '.co').mkdir()
        monkeypatch.chdir(tmp_path)
        trust = TrustAgent('careful')
        trust.promote_to_whitelist(address)

        requester = self._resolve(address, tmp_path)
        io = FakeIO(responses=[{'approved': True}])
        agent = FakeAgent(io=io, requester=requester)
        agent.current_session['pending_tool'] = DANGEROUS

        check_approval(agent)

        assert requester['level'] == 'whitelist'
        assert io.sent[0]['type'] == 'approval_needed'


class TestFreshInviteJourney:
    """An invite creates a usable contact and survives a host restart."""

    POLICY = """---
allow: [contact]
deny: [blocked]
onboard:
  invite_code: [TEAM-INVITE]
default: deny
---
"""

    def test_invited_contact_can_approve_after_restart(self, tmp_path, monkeypatch):
        from connectonion.network.trust import TrustAgent

        monkeypatch.chdir(tmp_path)
        (tmp_path / '.co').mkdir()
        address = '0x' + 'c' * 64

        first_host = TrustAgent(self.POLICY)
        assert first_host.verify_invite(address, 'TEAM-INVITE') is True
        assert first_host.get_level(address) == 'contact'

        # A new TrustAgent is the restart boundary. Contact state is read from
        # the project trust files rather than kept only in process memory.
        restarted_host = TrustAgent(self.POLICY)
        requester = {'address': address, 'level': restarted_host.get_level(address)}
        io = FakeIO(responses=[{'approved': True}])
        agent = FakeAgent(io=io, requester=requester)
        agent.current_session['pending_tool'] = DANGEROUS

        check_approval(agent)

        assert io.sent[0]['type'] == 'approval_needed'
