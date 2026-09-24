"""A relayed conversation is routed per client socket, not per session (#1606).

Two devices with the same conversation open reach the agent through the relay
as frames carrying the same `session_id`. Routed by that id they were fed into
one protocol handler, which cannot serve two sockets; the relay refused the
second device instead. A relay that tags each socket with `conn_id` gives every
device its own handler, and every reply goes back to the socket that owns it.
"""

import asyncio
import json

from connectonion.network import relay


class RelaySocket:
    def __init__(self):
        self.frames = []

    async def send(self, text):
        self.frames.append(json.loads(text))


def test_a_relay_that_names_the_socket_routes_by_it():
    assert relay._route_key({"session_id": "s1", "conn_id": "c1"}) == "c1"


def test_an_older_relay_still_routes_by_session():
    assert relay._route_key({"session_id": "s1"}) == "s1"


def _serve_one(first_msg, reply):
    """Run one connection's handler; it answers the first frame once."""
    socket = RelaySocket()
    sessions = {relay._route_key(first_msg): asyncio.Queue()}

    async def handler(send_msg, recv_msg):
        await recv_msg()
        await send_msg(reply)

    asyncio.run(relay._run_session(
        relay._route_key(first_msg), first_msg, sessions, socket, handler,
    ))
    return socket.frames, sessions


def test_replies_carry_the_socket_they_belong_to():
    frames, sessions = _serve_one(
        {"type": "CONNECT", "session_id": "s1", "conn_id": "phone"},
        {"type": "CONNECTED"},
    )
    assert frames == [{"type": "CONNECTED", "session_id": "s1", "conn_id": "phone"}]
    assert sessions == {}     # the handler's queue is gone with it


def test_an_older_relay_gets_no_conn_id_back():
    frames, _ = _serve_one({"type": "CONNECT", "session_id": "s1"}, {"type": "CONNECTED"})
    assert frames == [{"type": "CONNECTED", "session_id": "s1"}]


def test_one_logged_event_sent_to_two_sockets_is_not_stamped_by_the_first():
    event = {"type": "thinking", "content": "x"}
    laptop, _ = _serve_one({"type": "INPUT", "session_id": "s1", "conn_id": "laptop"}, event)
    phone, _ = _serve_one({"type": "CONNECT", "session_id": "s1", "conn_id": "phone"}, event)

    assert laptop[0]["conn_id"] == "laptop"
    assert phone[0]["conn_id"] == "phone"
    assert "conn_id" not in event
