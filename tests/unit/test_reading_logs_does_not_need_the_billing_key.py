"""Reading an agent's logs must not accept the key that pays for models (#670).

    if path in ["/admin/logs", "/admin/sessions"]:
        expected = os.environ.get("OPENONION_API_KEY", "")
        ... hmac.compare_digest(auth[7:], expected)

That is the key `co auth` obtains, `co create` writes into the project's .env,
and every `co/*` model call sends to oo.openonion.ai. So the only way to let
someone read an agent's activity is to hand them the credential that spends its
money.

The alternative is already in the same function. `/admin/trust/*` and
`/superadmin/*` take a signed request and check membership of the admin list,
with GETs carrying X-From / X-Signature / X-Timestamp because proxies strip GET
bodies. The comment above the older branch calls it "Legacy admin endpoints".

So this adds that path to the two legacy routes rather than inventing anything:
an admin can read logs by signing, and nobody has to be handed the billing key
to do it.

Bearer automation uses a separate per-deployment admin token. The billing key
is explicitly rejected even if it is copied into that setting.
"""

import pytest


ADMIN = "0x" + "a" * 64
STRANGER = "0x" + "b" * 64


class _TrustAgent:
    def is_admin(self, address):
        return address == ADMIN

    def is_super_admin(self, address):
        return False


@pytest.fixture
def call(monkeypatch):
    """Drive handle_admin_routes and capture what it answered."""
    from connectonion.network.trust import http_admin

    monkeypatch.setenv("OPENONION_API_KEY", "the-billing-key")
    monkeypatch.setenv("CONNECTONION_ADMIN_TOKEN", "the-admin-token")

    async def run(path, *, headers=None, bearer=None):
        sent = {}

        async def send_json(body, status=200):
            sent.update(body=body, status=status)

        async def send_text(text, status=200):
            sent.update(body=text, status=status)

        async def read_body(receive):
            return b""

        raw = []
        if bearer:
            raw.append((b"authorization", f"Bearer {bearer}".encode()))
        for key, value in (headers or {}).items():
            raw.append((key.encode(), value.encode()))

        def auth(data, mode):
            # Stands in for the host's signature check: valid when the caller
            # supplied one, and reporting who signed.
            who = data.get("from")
            if not who or not data.get("signature"):
                return None, None, False, "unauthorized: invalid signature"
            return None, who, True, None

        handlers = {
            "auth": auth,
            "trust_agent": _TrustAgent(),
            "admin_logs": lambda: {"content": "line one\nline two"},
            "admin_sessions": lambda: {"sessions": [{"session_id": "s1"}]},
        }

        handled = await http_admin.handle_admin_routes(
            "GET", path, {"headers": raw}, None, handlers,
            send_json=send_json, send_text=send_text, read_body=read_body,
        )
        return handled, sent

    return run


def _signed(who=ADMIN):
    return {"x-from": who, "x-signature": "sig", "x-timestamp": "1785999999"}


@pytest.mark.asyncio
class TestAnAdminCanReadWithoutTheBillingKey:

    async def test_logs_are_returned(self, call):
        handled, sent = await call("/admin/logs", headers=_signed())

        assert handled
        assert sent["status"] == 200
        assert "line one" in sent["body"]

    async def test_sessions_are_returned(self, call):
        _, sent = await call("/admin/sessions", headers=_signed())

        assert sent["status"] == 200
        assert sent["body"]["sessions"][0]["session_id"] == "s1"

    async def test_it_works_with_no_billing_key_configured(self, call, monkeypatch):
        monkeypatch.delenv("OPENONION_API_KEY", raising=False)

        _, sent = await call("/admin/logs", headers=_signed())

        assert sent["status"] == 200


@pytest.mark.asyncio
class TestSigningIsNotEnoughOnItsOwn:

    async def test_a_stranger_is_refused(self, call):
        _, sent = await call("/admin/logs", headers=_signed(STRANGER))

        assert sent["status"] == 403

    async def test_an_unsigned_request_is_refused(self, call):
        _, sent = await call("/admin/logs")

        assert sent["status"] == 401

    async def test_a_signature_without_a_sender_is_refused(self, call):
        _, sent = await call(
            "/admin/logs", headers={"x-signature": "sig", "x-timestamp": "1785999999"}
        )

        assert sent["status"] == 401


@pytest.mark.asyncio
class TestTheDedicatedBearerPath:

    async def test_the_billing_key_cannot_read_logs(self, call):
        _, sent = await call("/admin/logs", bearer="the-billing-key")

        assert sent["status"] == 401

    async def test_a_distinct_admin_token_reads_logs(self, call):
        _, sent = await call("/admin/logs", bearer="the-admin-token")

        assert sent["status"] == 200
        assert "line one" in sent["body"]

    async def test_a_wrong_bearer_is_still_refused(self, call):
        _, sent = await call("/admin/logs", bearer="not-the-key")

        assert sent["status"] == 401

    async def test_sessions_too(self, call):
        _, sent = await call("/admin/sessions", bearer="the-admin-token")

        assert sent["status"] == 200

    async def test_reusing_the_billing_key_as_admin_token_fails_closed(
        self, call, monkeypatch
    ):
        monkeypatch.setenv("CONNECTONION_ADMIN_TOKEN", "the-billing-key")

        _, sent = await call("/admin/logs", bearer="the-billing-key")

        assert sent["status"] == 401
