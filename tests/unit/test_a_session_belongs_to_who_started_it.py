"""Naming someone else's session id hands you their conversation.

Measured against a real host over a real WebSocket, two different identities,
both whitelisted on the same agent:

    A CONNECTED session=457204c5… status=new
    A -> "Remember this exactly: my codeword is PURPLE-OTTER-42. Reply OK."
    A <- "OK."

    B CONNECTED session=457204c5… status=connected     <- B named A's session id
    B -> "What codeword did I give you earlier? Answer with just the codeword."
    B <- "PURPLE-OTTER-42."

B was a freshly generated identity that had never spoken to this agent.

The session id comes off the client's frame and nothing checks who it belongs
to:

    session_id = data.get("session_id") or str(uuid.uuid4())
    ...
    stored = storage.get(session_id)
    if stored and stored.session:
        conn["session"], server_newer = merge_sessions(...)

    active = registry.get(session_id)
    if active and active.status == 'running':
        status = "running"

Two ways in, and the live one is worse: `resume_forwarding` rewinds and streams
the output of someone else's turn in progress.

The owner was already being recorded. `input_handler` writes
`session['requester']` from the signature-verified address on every turn, and
`requester` is in SERVER_OWNED_SESSION_KEYS -- the client carries it but does
not get to author it, for exactly this class of reason. Nothing read it back.

A session owned by someone else is treated as not found: a fresh session with
that id, indistinguishable from one that expired. Refusing would confirm the
session exists. This discloses nothing and breaks nothing legitimate, because a
session is one conversation with one caller.
"""

from unittest.mock import MagicMock

import pytest

from connectonion.network.host.session import SessionStorage
from connectonion.network.host.session.storage import Session


A = "0x" + "a" * 64
B = "0x" + "b" * 64
SID = "session-under-test"


def _stored(storage, owner):
    """A finished turn belonging to `owner`, the way input_handler writes one."""
    storage.save(Session(
        session_id=SID, status="done", prompt="hello", result="hi",
        # `iteration` and `updated` are what merge_sessions compares. A real
        # stored session has both -- input_handler stamps `updated` after every
        # turn -- and without them the empty client session wins the merge and
        # this fixture proves nothing either way.
        session={"messages": [{"role": "user", "content": "my codeword is PURPLE-OTTER-42"}],
                 "iteration": 1, "updated": 1_000_000.0,
                 "requester": {"address": owner, "level": "whitelist"}},
    ))


@pytest.fixture
def storage(tmp_path):
    return SessionStorage(path=tmp_path / "sessions.jsonl")


class TestTheStoredConversation:

    def test_a_stranger_naming_it_gets_nothing(self, storage):
        from connectonion.network.host.session import session_owner

        _stored(storage, owner=A)

        assert session_owner(storage.get(SID)) == A
        assert session_owner(storage.get(SID)) != B

    def test_the_owner_is_read_from_where_the_server_wrote_it(self, storage):
        """Not from anywhere the client can reach: `requester` is server-owned."""
        from connectonion.network.host.session import session_owner
        from connectonion.network.host.http_router import SERVER_OWNED_SESSION_KEYS

        assert "requester" in SERVER_OWNED_SESSION_KEYS
        _stored(storage, owner=A)

        assert session_owner(storage.get(SID)) == A

    def test_a_session_with_no_owner_belongs_to_nobody(self, storage):
        """Sessions written before this existed. Nobody inherits them."""
        from connectonion.network.host.session import session_owner

        storage.save(Session(session_id=SID, status="done", prompt="x",
                             session={"messages": []}))

        assert session_owner(storage.get(SID)) is None

    def test_a_missing_session_has_no_owner(self, storage):
        from connectonion.network.host.session import session_owner

        assert session_owner(None) is None


class TestTheLiveSession:
    """The worse half: `resume_forwarding` streams a turn in progress."""

    def test_the_registry_records_who_started_it(self):
        from connectonion.network.host.session import ActiveSessionRegistry

        registry = ActiveSessionRegistry()
        registry.register(SID, io=object(), thread=None, owner=A)

        assert registry.get(SID).owner == A

    def test_an_entry_registered_without_one_belongs_to_nobody(self):
        from connectonion.network.host.session import ActiveSessionRegistry

        registry = ActiveSessionRegistry()
        registry.register(SID, io=object(), thread=None)

        assert registry.get(SID).owner is None

    def test_marking_it_running_again_keeps_the_owner(self):
        """A second turn on the same session must not clear it."""
        from connectonion.network.host.session import ActiveSessionRegistry

        registry = ActiveSessionRegistry()
        registry.register(SID, io=object(), thread=None, owner=A)
        registry.mark_session_running(SID, io=object(), thread=None)

        assert registry.get(SID).owner == A


class TestWhatConnectDoes:
    """The two decisions establish_connection makes with a session id."""

    def _connect_as(self, caller, storage, registry):
        import asyncio

        from connectonion.network.host.ws_router.connect import establish_connection

        conn = {"authenticated": False, "agent_address": None,
                "session_id": None, "session": None}
        sent = []

        async def send_msg(msg):
            sent.append(msg)

        async def run():
            return await establish_connection(
                {"session_id": SID}, caller, send_msg, conn, storage, registry,
                {"agent_metadata": {"name": "t"}},
            )

        asyncio.run(run())
        return conn, sent

    def test_the_owner_gets_their_conversation_back(self, storage):
        from connectonion.network.host.session import ActiveSessionRegistry

        _stored(storage, owner=A)
        conn, _ = self._connect_as(A, storage, ActiveSessionRegistry())

        messages = (conn["session"] or {}).get("messages") or []
        assert any("PURPLE-OTTER-42" in str(m) for m in messages), conn["session"]

    def test_somebody_else_does_not(self, storage):
        from connectonion.network.host.session import ActiveSessionRegistry

        _stored(storage, owner=A)
        conn, _ = self._connect_as(B, storage, ActiveSessionRegistry())

        messages = (conn["session"] or {}).get("messages") or []
        assert not any("PURPLE-OTTER-42" in str(m) for m in messages), (
            f"B was handed A's conversation: {conn['session']}"
        )

    def test_somebody_else_is_told_it_is_new(self, storage):
        """Not refused -- refusing would confirm the session exists."""
        from connectonion.network.host.session import ActiveSessionRegistry

        _stored(storage, owner=A)
        _, sent = self._connect_as(B, storage, ActiveSessionRegistry())

        connected = [m for m in sent if m.get("type") == "CONNECTED"]
        assert connected and connected[0]["status"] == "new", sent

    def test_somebody_else_does_not_attach_to_a_running_turn(self, storage):
        from connectonion.network.host.session import ActiveSessionRegistry

        registry = ActiveSessionRegistry()
        registry.register(SID, io=object(), thread=None, owner=A)
        _, sent = self._connect_as(B, storage, registry)

        connected = [m for m in sent if m.get("type") == "CONNECTED"]
        assert connected[0]["status"] == "new", (
            "B attached to A's turn in progress and gets its output streamed"
        )

    def test_the_owner_does_attach_to_their_running_turn(self, storage):
        """The owner reaches resume_forwarding, which rewinds the live stream --
        so `io` has to be something that can be rewound. The bare object() the
        other cases use is enough for them precisely because they never get
        this far."""
        from connectonion.network.host.session import ActiveSessionRegistry

        registry = ActiveSessionRegistry()
        registry.register(SID, io=MagicMock(), thread=None, owner=A)
        _, sent = self._connect_as(A, storage, registry)

        connected = [m for m in sent if m.get("type") == "CONNECTED"]
        assert connected[0]["status"] == "running"


class TestASquatterDoesNotDestroyIt:
    """Treating the session as "not found" is not enough on its own.

    The first version of this fix kept the client's session id and gave them an
    empty session under it. Their turn then saved a record with that id --
    storage is append-only, last entry wins -- and the owner came back to find
    their conversation replaced. Measured, after that version:

        A turn 1: session=1b7625e1…  -> OK.
        B squats on it (status=new)  -> Hello!
        A returns (status=connected) -> "I don't have a codeword from you."
        A LOST their conversation

    Which is a worse trade than the leak it fixed: the leak needed the id, and
    so does this, but this destroys rather than discloses. So a caller who names
    somebody else's session gets a *different* id, and the owner's record is
    never written to.
    """

    def _connect(self, caller, storage, registry, wanted=SID):
        import asyncio

        from connectonion.network.host.ws_router.connect import establish_connection

        conn = {"authenticated": False, "agent_address": None,
                "session_id": None, "session": None}
        sent = []

        async def send_msg(msg):
            sent.append(msg)

        asyncio.run(establish_connection({"session_id": wanted}, caller, send_msg,
                                         conn, storage, registry,
                                         {"agent_metadata": {"name": "t"}}))
        return conn, sent

    def test_the_squatter_gets_a_different_id(self, storage):
        from connectonion.network.host.session import ActiveSessionRegistry

        _stored(storage, owner=A)
        conn, sent = self._connect(B, storage, ActiveSessionRegistry())

        assert conn["session_id"] != SID, (
            "B keeps the id, so B's turn overwrites A's stored session"
        )

    def test_the_client_is_told_the_id_it_actually_has(self, storage):
        from connectonion.network.host.session import ActiveSessionRegistry

        _stored(storage, owner=A)
        conn, sent = self._connect(B, storage, ActiveSessionRegistry())
        connected = [m for m in sent if m.get("type") == "CONNECTED"][0]

        assert connected["session_id"] == conn["session_id"]
        assert connected["session_id"] != SID

    def test_the_owner_keeps_theirs(self, storage):
        from connectonion.network.host.session import ActiveSessionRegistry

        _stored(storage, owner=A)
        conn, _ = self._connect(A, storage, ActiveSessionRegistry())

        assert conn["session_id"] == SID

    def test_a_live_session_is_protected_the_same_way(self, storage):
        from connectonion.network.host.session import ActiveSessionRegistry

        registry = ActiveSessionRegistry()
        registry.register(SID, io=object(), thread=None, owner=A)
        conn, _ = self._connect(B, storage, registry)

        assert conn["session_id"] != SID, (
            "B would register a second agent under A's live session id"
        )

    def test_an_unowned_session_is_still_shared(self, storage):
        """Sessions stored before any of this have no owner. Nobody is evicted
        from them on upgrade."""
        from connectonion.network.host.session import ActiveSessionRegistry

        storage.save(Session(session_id=SID, status="done", prompt="x",
                             session={"messages": [], "iteration": 1, "updated": 1.0}))
        conn, _ = self._connect(B, storage, ActiveSessionRegistry())

        assert conn["session_id"] == SID
