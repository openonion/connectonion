"""Admin signatures authorise one HTTP method and path, not any admin call."""

import pytest

from connectonion import address
from connectonion.network.host.auth import extract_and_authenticate
from connectonion.network.trust import http_admin


class _TrustAgent:
    def __init__(self, admin):
        self.admin = admin

    def is_admin(self, candidate):
        return candidate == self.admin

    def is_super_admin(self, candidate):
        return candidate == self.admin


async def _call(keys, method, path, *, signed_body=None, signed_headers=None):
    sent = {}

    async def send_json(body, status=200):
        sent.update(body=body, status=status)

    async def send_text(text, status=200):
        sent.update(body=text, status=status)

    async def read_body(receive):
        import json

        return json.dumps(signed_body).encode() if signed_body else b""

    def authenticate(data, mode):
        return extract_and_authenticate(data, mode)

    handlers = {
        "auth": authenticate,
        "trust_agent": _TrustAgent(keys["address"]),
        "admin_logs": lambda: {"content": "logs"},
        "admin_sessions": lambda: {"sessions": []},
        "admin_trust_promote": lambda client_id: {"promoted": client_id},
        "admin_trust_block": lambda client_id, reason: {"blocked": client_id},
        "admin_trust_level": lambda client_id: {"level": "contact"},
    }
    raw_headers = [
        (name.encode(), value.encode())
        for name, value in (signed_headers or {}).items()
    ]
    await http_admin.handle_admin_routes(
        method,
        path,
        {"headers": raw_headers},
        None,
        handlers,
        send_json=send_json,
        send_text=send_text,
        read_body=read_body,
    )
    return sent


@pytest.fixture(autouse=True)
def clean_replay_cache():
    from connectonion.network.host import auth

    auth._seen_signatures.clear()
    yield
    auth._seen_signatures.clear()


@pytest.mark.asyncio
async def test_route_bound_get_is_accepted():
    from connectonion.network.host.auth import sign_request

    keys = address.generate()
    headers = sign_request(keys, "GET", "/admin/logs")

    sent = await _call(keys, "GET", "/admin/logs", signed_headers=headers)

    assert sent["status"] == 200


@pytest.mark.asyncio
async def test_get_signature_cannot_be_moved_to_another_route():
    from connectonion.network.host.auth import sign_request

    keys = address.generate()
    headers = sign_request(keys, "GET", "/admin/logs")

    sent = await _call(keys, "GET", "/admin/sessions", signed_headers=headers)

    assert sent["status"] == 401


@pytest.mark.asyncio
async def test_route_bound_post_is_accepted():
    from connectonion.network.host.auth import sign_request_body

    keys = address.generate()
    body = sign_request_body(
        keys,
        "POST",
        "/admin/trust/promote",
        {"client_id": "0xclient"},
    )

    sent = await _call(keys, "POST", "/admin/trust/promote", signed_body=body)

    assert sent["status"] == 200


@pytest.mark.asyncio
async def test_post_signature_cannot_authorise_a_different_mutation():
    from connectonion.network.host.auth import sign_request_body

    keys = address.generate()
    body = sign_request_body(
        keys,
        "POST",
        "/admin/trust/promote",
        {"client_id": "0xclient"},
    )

    sent = await _call(keys, "POST", "/admin/trust/block", signed_body=body)

    assert sent["status"] == 401


@pytest.mark.asyncio
async def test_legacy_unbound_body_cannot_mutate_trust():
    import json
    import time

    keys = address.generate()
    payload = {"client_id": "0xclient", "timestamp": time.time()}
    signature = address.sign(
        keys,
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
    ).hex()
    body = {"payload": payload, "from": keys["address"], "signature": signature}

    sent = await _call(keys, "POST", "/admin/trust/block", signed_body=body)

    assert sent["status"] == 401
    assert "method" in sent["body"]["error"] or "route" in sent["body"]["error"]
