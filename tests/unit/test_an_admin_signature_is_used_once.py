"""One admin signature opens every admin route, as many times as you like.

Measured against a real host on :8833, with one signature over `{timestamp}`:

    1st use on /admin/logs                       200
    SAME signature reused on /admin/sessions     200
    SAME signature replayed on /admin/logs       200

So a signature captured once is, for its five-minute window, a bearer token for
the whole admin surface. Nothing binds it to the route it was made for, and
nothing stops it being used again.

`auth.py` built the answer to both and says why, above the headers it defines:

    The signature travels in headers over {method, path, timestamp},
    canonicalised exactly as CONNECT and INPUT already are, and is then verified
    by the same _authenticate_signed below. One canonicalisation, one freshness
    window, one blacklist check -- a second implementation of any of those is how
    the halves of a gate drift apart, which is most of what this release has been
    about.

The admin routes are that second implementation: different header names
(`x-from` against `x-co-from`), and a payload of `{timestamp}` alone, so the
signature says "I am an admin, some time in the last five minutes" and nothing
about what it authorises.

Replay is the part with a fix already written. `signature_already_used()` lives
in auth.py, records each signature for the freshness window, and is called from
exactly one place — ws_router/connect.py, for CONNECT (#649). The admin routes
never call it.

I widened this path to /admin/logs and /admin/sessions in the previous commit
while fixing #670, so the reach of a replayed admin signature is something I
made worse. Binding the signature to method and path is a protocol change for
any client already signing admin calls; refusing a second use of the same
signature is not, and is what this does.
"""

import time

import pytest


ADMIN = "0x" + "a" * 64


class _TrustAgent:
    def is_admin(self, address):
        return address == ADMIN

    def is_super_admin(self, address):
        return address == ADMIN


@pytest.fixture(autouse=True)
def clean_replay_cache():
    from connectonion.network.host import auth

    auth._seen_signatures.clear()
    yield
    auth._seen_signatures.clear()


@pytest.fixture
def call(monkeypatch):
    from connectonion.network.trust import http_admin

    monkeypatch.delenv("OPENONION_API_KEY", raising=False)

    async def run(path, signature, *, method="GET", replay_check=None):
        sent = {}

        async def send_json(body, status=200):
            sent.update(body=body, status=status)

        async def send_text(text, status=200):
            sent.update(body=text, status=status)

        async def read_body(receive):
            return b""

        headers = [
            (b"x-from", ADMIN.encode()),
            (b"x-signature", signature.encode()),
            (b"x-timestamp", str(time.time()).encode()),
        ]

        def auth(data, mode):
            # The real verifier's answer for a well-formed signed request.
            return None, data.get("from"), True, None

        handlers = {
            "auth": auth,
            "trust_agent": _TrustAgent(),
            "admin_logs": lambda: {"content": "log body"},
            "admin_sessions": lambda: {"sessions": []},
            "admin_trust_level": lambda client_id: {"level": "contact"},
        }
        if replay_check is not None:
            handlers["replay"] = replay_check

        await http_admin.handle_admin_routes(
            method, path, {"headers": headers}, None, handlers,
            send_json=send_json, send_text=send_text, read_body=read_body,
        )
        return sent

    return run


@pytest.mark.asyncio
class TestASignatureWorksOnce:

    async def test_admin_route_uses_the_injected_replay_guard(self, call):
        claimed = []

        sent = await call(
            "/admin/logs", "sig-one",
            replay_check=lambda data: claimed.append(data) or True,
        )

        assert [item["signature"] for item in claimed] == ["sig-one"]
        assert sent["status"] == 401

    async def test_the_first_use_is_allowed(self, call):
        sent = await call("/admin/logs", "sig-one")

        assert sent["status"] == 200

    async def test_the_second_use_is_refused(self, call):
        await call("/admin/logs", "sig-one")
        sent = await call("/admin/logs", "sig-one")

        assert sent["status"] == 401

    async def test_it_cannot_be_carried_to_another_admin_route(self, call):
        await call("/admin/logs", "sig-one")
        sent = await call("/admin/sessions", "sig-one")

        assert sent["status"] == 401

    async def test_the_refusal_says_why(self, call):
        await call("/admin/logs", "sig-one")
        sent = await call("/admin/logs", "sig-one")

        assert "replay" in str(sent["body"]).lower() or "used" in str(sent["body"]).lower()


@pytest.mark.asyncio
class TestAFreshSignatureStillWorks:
    """The window belongs to the signature, not to the caller."""

    async def test_a_second_distinct_signature_is_allowed(self, call):
        await call("/admin/logs", "sig-one")
        sent = await call("/admin/logs", "sig-two")

        assert sent["status"] == 200

    async def test_many_calls_each_with_their_own_signature(self, call):
        for index in range(5):
            sent = await call("/admin/sessions", f"sig-{index}")

            assert sent["status"] == 200

    async def test_the_trust_routes_get_the_same_protection(self, call):
        await call("/admin/trust/level/0xabc", "sig-trust")
        sent = await call("/admin/trust/level/0xabc", "sig-trust")

        assert sent["status"] == 401


@pytest.mark.asyncio
class TestTheDedicatedBearerPathIsUnaffected:
    """A distinct admin bearer carries no signature to replay."""

    async def test_a_bearer_call_does_not_consume_a_signature(
        self, call, monkeypatch
    ):
        from connectonion.network.trust import http_admin

        monkeypatch.setenv("OPENONION_API_KEY", "billing-key")
        monkeypatch.setenv("CONNECTONION_ADMIN_TOKEN", "admin-key")

        sent = {}

        async def send_json(body, status=200):
            sent.update(body=body, status=status)

        async def send_text(text, status=200):
            sent.update(body=text, status=status)

        async def read_body(receive):
            return b""

        await http_admin.handle_admin_routes(
            "GET", "/admin/logs",
            {"headers": [(b"authorization", b"Bearer admin-key")]},
            None,
            {"admin_logs": lambda: {"content": "log body"}},
            send_json=send_json, send_text=send_text, read_body=read_body,
        )

        assert sent["status"] == 200
