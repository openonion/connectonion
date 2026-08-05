"""`curl http://agent/sessions` returns every conversation on the agent.

No signature, no identity, no key. Measured against a real host on default
trust:

    GET /sessions -> {"sessions": [{"session_id": "9fd5d3fc-…",
                                    "status": "done",
                                    "prompt": "What codeword did I give you earlier?",
                                    "result": "PURPLE-OTTER-42",
                                    "session": {…every message…}}]}

The prompt, the answer and the full message history. `POST /input` immediately
above it in the same dispatch goes through `route_handlers["auth"]`; these two
never did:

    elif method == "GET" and path.startswith("/sessions/"):
        result = route_handlers["session"](storage, path[10:])

    elif method == "GET" and path == "/sessions":
        await send_json(send, route_handlers["sessions"](storage))

It is also where #696's attack got its ids. That one needed a session id to
read somebody else's conversation; this hands out every id on the agent to
anyone who can reach the port.

A GET has no body to sign, so the signature travels in headers over
`{"method", "path", "timestamp"}` -- canonicalised exactly as CONNECT and INPUT
already are, and verified through the same `extract_and_authenticate`, so the
trust level, the blacklist and the five-minute freshness window all apply
without a second implementation of any of them.

Aaron chose this over gating on OPENONION_API_KEY (#670 is about that key being
over-powered) and over deleting the endpoints.

Scoping comes from #698: a session records who started it, so `/sessions`
returns the caller's own and `/sessions/{id}` returns one only if they own it.
"""

import json
import time

import pytest

from connectonion import address


@pytest.fixture
def caller():
    return address.generate()


@pytest.fixture
def other():
    return address.generate()


def signed_headers(keys, method: str, path: str, timestamp=None) -> dict:
    """What a client sends. Imported from the module under test on purpose --
    a test that builds these by hand certifies its own idea of the format."""
    from connectonion.network.host.auth import sign_request

    return sign_request(keys, method, path, timestamp=timestamp)


class TestTheHeadersAreTheSameProtocol:
    """One canonicalisation in the codebase, not two."""

    def test_the_payload_is_method_path_and_timestamp(self, caller):
        from connectonion.network.host.auth import request_from_headers

        headers = signed_headers(caller, "GET", "/sessions")
        data = request_from_headers(headers, "GET", "/sessions")

        assert data["payload"]["method"] == "GET"
        assert data["payload"]["path"] == "/sessions"
        assert isinstance(data["payload"]["timestamp"], (int, float))

    def test_it_verifies(self, caller):
        from connectonion.network.host.auth import request_from_headers, verify_signature

        headers = signed_headers(caller, "GET", "/sessions")
        data = request_from_headers(headers, "GET", "/sessions")

        assert verify_signature(data["payload"], data["signature"], data["from"])

    def test_the_signer_is_carried(self, caller):
        from connectonion.network.host.auth import request_from_headers

        data = request_from_headers(signed_headers(caller, "GET", "/sessions"),
                                    "GET", "/sessions")

        assert data["from"] == caller["address"]


class TestASignatureIsBoundToTheRequest:
    """Otherwise one captured header set reads anything."""

    def test_a_signature_for_another_path_does_not_verify(self, caller):
        from connectonion.network.host.auth import request_from_headers, verify_signature

        headers = signed_headers(caller, "GET", "/sessions/mine")
        data = request_from_headers(headers, "GET", "/sessions/yours")

        assert not verify_signature(data["payload"], data["signature"], data["from"])

    def test_a_signature_for_another_method_does_not_verify(self, caller):
        from connectonion.network.host.auth import request_from_headers, verify_signature

        headers = signed_headers(caller, "GET", "/sessions")
        data = request_from_headers(headers, "DELETE", "/sessions")

        assert not verify_signature(data["payload"], data["signature"], data["from"])

    def test_an_old_signature_is_refused(self, caller):
        """The same five-minute window every other frame gets."""
        from connectonion.network.host.auth import (SIGNATURE_EXPIRY_SECONDS,
                                                    _authenticate_signed,
                                                    request_from_headers)

        stale = time.time() - SIGNATURE_EXPIRY_SECONDS - 60
        data = request_from_headers(signed_headers(caller, "GET", "/sessions", stale),
                                    "GET", "/sessions")

        _, _, err = _authenticate_signed(data)
        assert err and "expired" in err

    def test_no_headers_at_all_is_refused(self):
        from connectonion.network.host.auth import _authenticate_signed, request_from_headers

        data = request_from_headers({}, "GET", "/sessions")

        _, _, err = _authenticate_signed(data)
        assert err, "an unsigned GET authenticated"


class TestWhatTheCallerSees:
    """Scoped by the owner #698 records."""

    def _storage(self, tmp_path, *owners):
        from connectonion.network.host.session import SessionStorage
        from connectonion.network.host.session.storage import Session

        storage = SessionStorage(path=tmp_path / "s.jsonl")
        for index, owner in enumerate(owners):
            storage.save(Session(
                session_id=f"s{index}", status="done", prompt="p", result="r",
                session={"messages": [], "iteration": 1, "updated": 1.0,
                         "requester": {"address": owner, "level": "whitelist"}},
            ))
        return storage

    def test_only_their_own_are_listed(self, tmp_path, caller, other):
        from connectonion.network.host.http_router import sessions_handler

        storage = self._storage(tmp_path, caller["address"], other["address"])
        listed = sessions_handler(storage, caller["address"])["sessions"]

        assert [s["session_id"] for s in listed] == ["s0"], listed

    def test_somebody_elses_is_not_readable_by_id(self, tmp_path, caller, other):
        from connectonion.network.host.http_router import session_handler

        storage = self._storage(tmp_path, other["address"])

        assert session_handler(storage, "s0", caller["address"]) is None

    def test_their_own_is(self, tmp_path, caller):
        from connectonion.network.host.http_router import session_handler

        storage = self._storage(tmp_path, caller["address"])

        assert session_handler(storage, "s0", caller["address"])["result"] == "r"

    def test_an_unowned_session_is_still_readable(self, tmp_path, caller):
        """Stored before any owner was recorded. Same rule as #698: nobody is
        evicted from those on upgrade."""
        from connectonion.network.host.http_router import session_handler
        from connectonion.network.host.session import SessionStorage
        from connectonion.network.host.session.storage import Session

        storage = SessionStorage(path=tmp_path / "s.jsonl")
        storage.save(Session(session_id="old", status="done", prompt="p", result="r"))

        assert session_handler(storage, "old", caller["address"])["result"] == "r"

    def test_nothing_is_listed_for_nobody(self, tmp_path, caller, other):
        """No caller address means the request was not authenticated."""
        from connectonion.network.host.http_router import sessions_handler

        storage = self._storage(tmp_path, caller["address"], other["address"])

        assert sessions_handler(storage, None)["sessions"] == []
