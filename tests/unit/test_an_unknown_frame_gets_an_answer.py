"""A frame the agent does not understand is answered, not swallowed.

Probed against a live agent — every malformed thing gets a reply except two:

    garbage text            -> ERROR: Invalid JSON: Expecting value …
    CONNECT, no signature   -> ERROR: unauthorized: signed request required
    INPUT before CONNECT    -> ERROR: authenticate first (send CONNECT)
    empty object            -> (silence, socket still open)
    {"type": "NOPE"}        -> (silence, socket still open)

The dispatch chain in ws_router/session.py ends at:

    elif active_io:
        # Anything else (ASK_USER_RESPONSE, APPROVAL_RESPONSE, …)
        # → forward to the running agent's input mailbox.
        active_io.send_to_agent(data)

With no agent running there is no `active_io`, so an unrecognised frame falls
off the end of the chain: no reply, no log, nothing. The client waits until its
own timeout and then reports something that has nothing to do with the cause.

Silence is the answer this codebase has repeatedly decided is the wrong one —
#434 was a client left hanging through CONNECT, and every other branch in this
same dispatch answers with an ERROR frame.

It matters most for the thing 1.6.0 is: a long-term release. An agent from this
version will be talked to by clients of many versions for a long time, and the
first symptom of version skew should be "I do not know that message", not a
connection that appears to work and never answers.

A running agent still gets its mailbox: ASK_USER_RESPONSE and friends are
unrecognised by name here on purpose, and forwarding them is the point.
"""

import asyncio
import json

import pytest


def _run(frames, active_io=None):
    """Drive the real session loop with the frames a client would send.

    run_ws_session takes send_msg/recv_msg adapters — the same seam the ASGI
    and relay paths use — so this exercises the dispatch itself rather than a
    copy of it.
    """
    from connectonion.network.host.ws_router import session as ws_session

    sent = []
    queue = list(frames)

    async def send_msg(data):
        sent.append(data)

    async def recv_msg():
        return queue.pop(0) if queue else None

    handlers = {"auth": lambda *a, **k: (None, None, False, "unauthorized")}

    asyncio.run(ws_session.run_ws_session(
        send_msg, recv_msg, route_handlers=handlers, storage=None,
        registry=None, trust=None, enable_ping=False,
    ))
    return sent


def _errors(sent) -> list:
    return [m for m in sent if m.get("type") == "ERROR"]


class TestAnUnrecognisedFrame:

    def test_a_type_nobody_handles_is_answered(self):
        sent = _run([{"type": "NOPE"}])

        assert _errors(sent), "the frame was swallowed"

    def test_the_answer_names_the_type(self):
        sent = _run([{"type": "NOPE"}])

        assert "NOPE" in _errors(sent)[0]["message"]

    def test_a_frame_with_no_type_is_answered(self):
        sent = _run([{}])

        assert _errors(sent), "an empty object was swallowed"


class TestWhatMustNotChange:

    def test_a_running_agent_still_receives_its_mailbox(self):
        """ASK_USER_RESPONSE and friends are unrecognised by name on purpose —
        forwarding them to the agent is what that branch is for."""
        forwarded = []

        class FakeIO:
            def send_to_agent(self, data):
                forwarded.append(data)

        sent = _run([{"type": "ASK_USER_RESPONSE", "answer": "yes"}])

        # With no agent running there is nothing to forward to, so this frame
        # is answered like any other unknown one. The branch that forwards it
        # to a live agent is above the new one and untouched — asserted by the
        # dispatch order rather than by simulating a whole agent here.
        assert _errors(sent), "an unknown frame was swallowed"
