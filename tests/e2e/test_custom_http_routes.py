"""Run publisher routes through the complete raw-ASGI host stack (#772)."""

import asyncio
import json
from unittest.mock import MagicMock

from connectonion import address
from connectonion.network.trust import TrustAgent


class ASGIResponse:
    def __init__(self):
        self.status_code = 0
        self.headers = {}
        self.body = b""

    def json(self):
        return json.loads(self.body)


def request(app, method, target, *, body=b"", headers=None):
    path, _, query = target.partition("?")

    async def call():
        response = ASGIResponse()
        sent = False

        async def receive():
            nonlocal sent
            if sent:
                return {"type": "http.disconnect"}
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                response.status_code = message["status"]
                response.headers = {
                    key.decode().lower(): value.decode()
                    for key, value in message.get("headers", [])
                }
            elif message["type"] == "http.response.body":
                response.body += message.get("body", b"")

        scope = {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": query.encode(),
            "headers": [
                [key.lower().encode(), str(value).encode()]
                for key, value in (headers or {}).items()
            ],
        }
        await app(scope, receive, send)
        return response

    return asyncio.run(call())


def agent_factory():
    agent = MagicMock()
    agent.name = "route-test-agent"
    agent.tools.names.return_value = []
    agent.current_session = {"messages": [], "trace": [], "turn": 1}
    return agent


class FixedTrust(TrustAgent):
    trust = "careful"

    def __init__(self, levels=None, admins=None):
        self.levels = levels or {}
        self.admins = set(admins or [])

    def get_level(self, identity):
        return self.levels.get(identity, "stranger")

    def is_admin(self, identity):
        return identity in self.admins

    def get_self_address(self):
        return None


def make_app(tmp_path, monkeypatch, http, trust="open"):
    from connectonion.network.host import SessionStorage, create_app

    monkeypatch.chdir(tmp_path)
    storage = SessionStorage(tmp_path / ".co" / "sessions.jsonl")
    return create_app(agent_factory, storage=storage, trust=trust, http=http)


def test_public_calendar_feed_is_anonymous_and_keeps_its_media_type(tmp_path, monkeypatch):
    from connectonion import HTTPRequest, HTTPResponse, HTTPRouter

    http = HTTPRouter()

    @http.public.get("/feeds/{category}.ics")
    def feed(category: str, request: HTTPRequest):
        assert request.query == {"city": ["Sydney"]}
        return HTTPResponse(
            f"BEGIN:VCALENDAR\nX-WR-CALNAME:{category}\nEND:VCALENDAR\n",
            media_type="text/calendar; charset=utf-8",
            headers={"cache-control": "public, max-age=300"},
        )

    app = make_app(tmp_path, monkeypatch, http)
    response = request(app, "GET", "/public/feeds/ai.ics?city=Sydney")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/calendar; charset=utf-8"
    assert response.headers["cache-control"] == "public, max-age=300"
    assert response.headers["access-control-allow-origin"] == "*"
    assert b"X-WR-CALNAME:ai" in response.body


def test_public_post_receives_the_original_json_body(tmp_path, monkeypatch):
    from connectonion import HTTPRouter

    http = HTTPRouter()

    @http.public.post("/subscribe")
    def subscribe(request):
        return {"email": request.json()["email"], "path": request.path}

    app = make_app(tmp_path, monkeypatch, http)
    body = json.dumps({"email": "reader@example.com"}).encode()
    response = request(app, "POST", "/public/subscribe", body=body)

    assert response.status_code == 200
    assert response.json() == {
        "email": "reader@example.com",
        "path": "/public/subscribe",
    }


def test_contacts_route_requires_a_signed_contact_and_rejects_replay(tmp_path, monkeypatch):
    from connectonion import HTTPRouter
    from connectonion.network.host.auth import get_agent_address, sign_http_request

    caller = address.generate()
    stranger = address.generate()
    recipient = get_agent_address(agent_factory())
    trust = FixedTrust(levels={caller["address"]: "contact"})
    http = HTTPRouter()

    @http.contacts.post("/preferences")
    def preferences(request):
        return {"identity": request.identity, "data": request.json()}

    app = make_app(tmp_path, monkeypatch, http, trust=trust)
    body = b'{"topics":["ai"]}'

    unsigned = request(app, "POST", "/contacts/preferences", body=body)
    assert unsigned.status_code == 401

    stranger_headers = sign_http_request(
        stranger, "POST", "/contacts/preferences", body=body,
        recipient_address=recipient,
    )
    refused = request(
        app, "POST", "/contacts/preferences", body=body, headers=stranger_headers,
    )
    assert refused.status_code == 403

    headers = sign_http_request(
        caller, "POST", "/contacts/preferences", body=body,
        recipient_address=recipient,
    )
    accepted = request(app, "POST", "/contacts/preferences", body=body, headers=headers)
    assert accepted.status_code == 200
    assert accepted.json() == {
        "identity": caller["address"],
        "data": {"topics": ["ai"]},
    }

    replay = request(app, "POST", "/contacts/preferences", body=body, headers=headers)
    assert replay.status_code == 401
    assert "already used" in replay.json()["error"]


def test_admin_route_checks_admin_and_binds_query_and_body(tmp_path, monkeypatch):
    from connectonion import HTTPRouter
    from connectonion.network.host.auth import get_agent_address, sign_http_request

    caller = address.generate()
    recipient = get_agent_address(agent_factory())
    trust = FixedTrust(admins={caller["address"]})
    http = HTTPRouter()

    @http.admin.post("/refresh")
    async def refresh(request):
        return {
            "by": request.identity,
            "scope": request.query["scope"][0],
            "force": request.json()["force"],
        }

    app = make_app(tmp_path, monkeypatch, http, trust=trust)
    body = b'{"force":true}'
    headers = sign_http_request(
        caller, "POST", "/admin/refresh", query="scope=all", body=body,
        recipient_address=recipient,
    )
    response = request(
        app, "POST", "/admin/refresh?scope=all", body=body, headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == {
        "by": caller["address"],
        "scope": "all",
        "force": True,
    }

    reordered_headers = sign_http_request(
        caller, "POST", "/admin/refresh", query="scope=all&b=2&a=1", body=body,
        recipient_address=recipient,
    )
    reordered = request(
        app, "POST", "/admin/refresh?a=1&scope=all&b=2", body=body,
        headers=reordered_headers,
    )
    assert reordered.status_code == 200

    wrong_body = request(
        app, "POST", "/admin/refresh?scope=all", body=b'{"force":false}',
        headers=sign_http_request(
            caller, "POST", "/admin/refresh", query="scope=all", body=body,
            recipient_address=recipient,
        ),
    )
    assert wrong_body.status_code == 401

    wrong_query = request(
        app, "POST", "/admin/refresh?scope=one", body=body,
        headers=sign_http_request(
            caller, "POST", "/admin/refresh", query="scope=all", body=body,
            recipient_address=recipient,
        ),
    )
    assert wrong_query.status_code == 401


def test_malformed_or_incomplete_auth_headers_fail_closed(tmp_path, monkeypatch):
    from connectonion import HTTPRouter
    from connectonion.network.host.auth import get_agent_address, sign_http_request

    caller = address.generate()
    recipient = get_agent_address(agent_factory())
    trust = FixedTrust(levels={caller["address"]: "contact"})
    http = HTTPRouter()
    http.contacts.get("/profile")(lambda: {"ok": True})
    app = make_app(tmp_path, monkeypatch, http, trust=trust)

    malformed = sign_http_request(
        caller, "GET", "/contacts/profile", recipient_address=recipient,
    )
    malformed["x-co-timestamp"] = "tomorrow"
    response = request(app, "GET", "/contacts/profile", headers=malformed)
    assert response.status_code == 401

    incomplete = sign_http_request(
        caller, "GET", "/contacts/profile", recipient_address=recipient,
    )
    del incomplete["x-co-request-id"]
    response = request(app, "GET", "/contacts/profile", headers=incomplete)
    assert response.status_code == 401


def test_blocked_contact_is_not_restored_by_the_parameter_whitelist(tmp_path, monkeypatch):
    from connectonion import HTTPRouter
    from connectonion.network.host import SessionStorage, create_app
    from connectonion.network.host.auth import get_agent_address, sign_http_request

    caller = address.generate()
    recipient = get_agent_address(agent_factory())
    trust = FixedTrust(levels={caller["address"]: "blocked"})
    http = HTTPRouter()
    http.contacts.get("/profile")(lambda: {"ok": True})
    monkeypatch.chdir(tmp_path)
    app = create_app(
        agent_factory,
        storage=SessionStorage(tmp_path / ".co" / "sessions.jsonl"),
        trust=trust,
        whitelist=[caller["address"]],
        http=http,
    )
    headers = sign_http_request(
        caller, "GET", "/contacts/profile", recipient_address=recipient,
    )

    assert request(app, "GET", "/contacts/profile", headers=headers).status_code == 403


def test_parameter_whitelist_grants_a_signed_caller_contact_access(tmp_path, monkeypatch):
    from connectonion import HTTPRouter
    from connectonion.network.host import SessionStorage, create_app
    from connectonion.network.host.auth import get_agent_address, sign_http_request

    caller = address.generate()
    recipient = get_agent_address(agent_factory())
    http = HTTPRouter()
    http.contacts.get("/profile")(lambda request: {"identity": request.identity})
    monkeypatch.chdir(tmp_path)
    app = create_app(
        agent_factory,
        storage=SessionStorage(tmp_path / ".co" / "sessions.jsonl"),
        trust=FixedTrust(),
        whitelist=[caller["address"]],
        http=http,
    )
    headers = sign_http_request(
        caller, "GET", "/contacts/profile", recipient_address=recipient,
    )

    response = request(app, "GET", "/contacts/profile", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"identity": caller["address"]}


def test_existing_framework_routes_still_work_with_a_custom_router(tmp_path, monkeypatch):
    from connectonion import HTTPRouter

    app = make_app(tmp_path, monkeypatch, HTTPRouter())

    assert request(app, "GET", "/health").status_code == 200
    assert request(app, "GET", "/info").status_code == 200
    assert request(app, "GET", "/not-a-route").status_code == 404
